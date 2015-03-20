# -*- Mode: Python -*-

import struct
import coro
import sys

from coro.http import connection, tlslite_server, openssl_server, http_request
from coro.http.protocol import header_set, http_file
from coro.http.zspdy import inflator, deflator, unpack_control_frame, pack_control_frame
from coro.http.zspdy import pack_data_frame, pack_http_header, unpack_http_header

W = coro.write_stderr

from coro.log import Facility
LOG = Facility ('spdy')

# tricky bits:
#
# It's important to use one zlib compression object per connection,
#   the protocol assumes it and won't work if you try to create a
#   new context per request/stream
#
# The protocol looks like it supports a generic 'stream' facility, but it does not.
#   Each 'stream' is really a single request/reply, and the HTTP headers are part of
#   SYN_STREAM/SYN_REPLY.  In other words, SPDY is very HTTP-centric.

# When a reply is large (say >1MB) we still get a form of head-blocking behavior
#   unless we chop it up into bits.  Think about an architecture that would
#   automatically do that.  [i.e., a configurable max size for data frames]

class spdy_file (http_file):

    # override http_file's content generator (which is a 'pull' generator)
    #   with this coro.fifo-based 'push' generator.

    def get_content_gen (self, headers):
        self.content_fifo = coro.fifo()
        return self._gen_spdy()

    def _gen_spdy (self):
        while 1:
            block = self.content_fifo.pop()
            if block is None:
                # W ('gen_spdy: end of content\n')
                self.done_cv.wake_all()
                break
            else:
                yield block

FLAG_FIN = 0x01
FLAG_UNIDIRECTIONAL = 0x02

class spdy_server_request (http_request):

    def __init__ (self, flags, stream_id, client, headers):
        self.fin_sent = False
        self.flags = flags
        self.stream_id = stream_id
        self.pending_data_frame = None
        method = headers.get_one (':method')
        scheme = headers.get_one (':scheme')
        host   = headers.get_one (':host')
        path   = headers.get_one (':path')
        version = headers.get_one (':version')
        # left off by chrome now?
        headers['host'] = host
        # XXX proxy
        # url = '%s://%s/%s' % (scheme, host, path)
        url = path
        # XXX consider changing the api to take these as separate arguments
        request = '%s %s %s' % (method, url, version)
        # XXX consider removing method/url/version?
        http_request.__init__ (self, client, request, headers)

    def can_deflate (self):
        return True

    def has_body (self):
        return not (self.flags & FLAG_FIN)

    def make_content_file (self):
        # XXX probably untested...
        self.file = spdy_file (self.request_headers, self.client.stream)

    def push_syn_reply (self, has_data=False):
        reason = self.responses[self.reply_code]
        self.reply_headers[':status'] = '%d %s' % (self.reply_code, reason)
        self.reply_headers[':version'] = 'HTTP/1.1'
        self.client.push_syn_reply (self, has_data)
        self.sent_headers = True

    def push_data (self, data, last=False):
        # we hold back one frame in order to be able to set FLAG_FIN on the last one.
        if self.pending_data_frame is None:
            self.pending_data_frame = data
        else:
            self.pending_data_frame, data = data, self.pending_data_frame
            self.client.push_data_frame (self, data, last)

    def push (self, data, flush=False):
        "push output data for this request."
        if not self.sent_headers:
            self.push_syn_reply (has_data=data)
        if self.deflate:
            if data:
                data = self.deflate.compress (data)
        if data:
            self.push_data (data)

    def done (self):
        if not self.sent_headers:
            self.push_syn_reply (has_data=False)
        else:
            if self.deflate:
                self.push_data (self.deflate.flush())
            self.push_data (None, last=True)
        http_request.done (self)

# this is a mixin class used for both server and client.

class spdy_protocol:

    frame_types = {
        1: 'syn_stream',
        2: 'syn_reply',
        3: 'rst_stream',
        4: 'settings',
        # removed in draft3
        5: 'noop',
        6: 'ping',
        7: 'goaway',
        8: 'headers',
        9: 'window_update',
    }

    status_codes = {
        1: 'protocol_error',
        2: 'invalid_stream',
        3: 'refused_stream',
        4: 'unsupported_version',
        5: 'cancel',
        6: 'internal_error',
        7: 'flow_control_error',
    }

    protocol = 'spdy/3'

    def read_exact (self, size):
        try:
            return self.conn.read_exact (size)
        except AttributeError:
            left = size
            r = []
            while left:
                block = self.conn.recv (left)
                if not block:
                    break
                else:
                    r.append (block)
                    left -= len (block)
            return ''.join (r)

    def read_frames (self):
        while 1:
            head = self.read_exact (8)
            if not head:
                break
            elif ord(head[0]) & 0x80:
                self.read_control_frame (head)
            else:
                self.read_data_frame (head)

    def read_control_frame (self, head):
        fversion, ftype, flags, length = unpack_control_frame (head)
        data = self.read_exact (length)
        # W ('control: version=%d type=%d flags=%x length=%d\n' % (fversion, ftype, flags, length, ))
        assert (fversion == 3)
        method_name = 'frame_%s' % (self.frame_types.get (ftype, ''),)
        if method_name == 'frame_':
            self.log ('unknown SPDY frame type: %d\n' % (ftype,))
        else:
            method = getattr (self, method_name)
            method (flags, data)

    def read_data_frame (self, head):
        stream_id, flags, length = unpack_data_frame (head)
        data = self.read_exact (length)
        # W ('data: stream_id=%d flags=%x length=%d\n' % (stream_id, flags, length))
        self.handle_data_frame (stream_id, flags, data)

    spdy_version = 3

    def unpack_http_header (self, data):
        hs = header_set()
        hs.headers = unpack_http_header (self.inflate (data))
        return hs

    def pack_http_header (self, hset):
        return self.deflate (pack_http_header (hset.headers))

    def pack_control_frame (self, ftype, flags, data):
        return pack_control_frame (self.spdy_version, ftype, flags, data)

    def pack_data_frame (self, stream_id, flags, data):
        return pack_data_frame (self.spdy_version, stream_id, flags, data)

# --------------------------------------------------------------------------------
#                             spdy server
# --------------------------------------------------------------------------------

# XXX not a fan of multiple inheritance, but this seems to be the cleanest way to share
# XXX the code between server and client...

class spdy_connection (spdy_protocol, connection):

    protocol = 'spdy'

    # default to 400K buffered output
    output_buffer_size = 400 * 1024

    def run (self):
        self.streams = {}
        self.deflate = deflator()
        self.inflate = inflator()
        self.ofifo = coro.fifo()
        self.obuf = coro.semaphore (self.output_buffer_size)
        coro.spawn (self.send_thread)
        try:
            self.read_frames()
        finally:
            self.ofifo.push (None)

    def close (self):
        self.ofifo.push (None)
        self.conn.close()

    def send_thread (self):
        while 1:
            block = self.ofifo.pop()
            if block is None:
                break
            else:
                self.conn.send (block)
                self.obuf.release (len(block))

    def send_frame (self, frame):
        # self.conn.send (frame)
        self.obuf.acquire (len(frame))
        self.ofifo.push (frame)

    def push_data_frame (self, req, data, last):
        if last:
            flags = FLAG_FIN
        else:
            flags = 0
        # it'd be nice to use writev here, but the layers of either tlslite or openssl
        #  preclude it...
        frame = self.pack_data_frame (req.stream_id, flags, data)
        self.send_frame (frame)
        req.output.sent += len (frame)

    def push_syn_reply (self, req, has_data):
        if not has_data:
            flags = 0x01
        else:
            flags = 0x00
        # W ('req.reply_headers=%r\n' % (str(req.reply_headers),))
        name_vals = self.pack_http_header (req.reply_headers)
        # W ('compressed name_vals=%r\n' % (name_vals,))
        frame = self.pack_control_frame (
            0x02, flags,
            ''.join ([struct.pack ('>L', req.stream_id), name_vals])
        )
        self.send_frame (frame)
        req.output.sent += len (frame)

    def frame_syn_stream (self, flags, data):
        sid, asid, pri = struct.unpack ('>LLH', data[:10])
        # XXX do something with priority
        sid  &= 0x7fffffff
        asid &= 0x7fffffff
        # W ('syn_stream: sid=%d asid=%d pri=%x ' % (sid, asid, pri))
        headers = self.unpack_http_header (data[10:])
        req = spdy_server_request (flags, sid, self, headers)
        # W ('%s\n' % req.request,)
        self.streams[sid] = req
        coro.spawn (self.handle_request, req)

    def handle_data_frame (self, stream_id, flags, data):
        probe = self.streams.get (stream_id, None)
        if probe is not None:
            probe.file.content_fifo.push (data)
            if flags & FLAG_FIN:
                probe.file.content_fifo.push (None)
                del self.streams[stream_id]
        else:
            self.log ('orphaned data frame [%d bytes] for stream %d\n' % (length, stream_id))

    def handle_request (self, req):
        try:
            handler = self.pick_handler (req)
            if handler:
                # XXX with_timeout()
                handler.handle_request (req)
            else:
                req.error (404)
        except:
            tb = coro.compact_traceback()
            req.error (500, tb)
            self.log ('error: %r request=%r tb=%r' % (self.peer, req, tb))

    def frame_rst_stream (self, flags, data):
        stream_id, status_code = struct.unpack ('>LL', data)
        # W ('reset: %x status=%d %s\n' % (stream_id, status_code, self.status_codes.get (status_code, 'unknown')))
        del self.streams[stream_id]

    def frame_goaway (self, flags, data):
        last_stream_id, = struct.unpack ('>L', data)
        # W ('goaway last_stream_id=%d\n' % (last_stream_id,))
        # XXX arrange for the connection to close
        self.close()

    def frame_ping (self, flags, data):
        ping_id, = struct.unpack ('>L', data)
        # W ('ping_id=%x\n' % (ping_id,))
        self.send_frame (self.pack_control_frame (6, 0, data))

    def frame_settings (self, flags, data):
        # self.log ('SPDY settings frame received [ignored]')
        pass

    def frame_headers (self, flags, data):
        # self.log ('SPDY headers frame received [ignored]')
        pass

    def frame_window_update (self, flags, data):
        # self.log ('SPDY window_update frame received [ignored]')
        stream_id, delta_window_size = struct.unpack ('>LL', data)
        self.log ('spdy window update', stream_id, delta_window_size)

class spdy_tlslite_server (tlslite_server):

    protocol = 'spdy'

    def __init__ (self, addr, cert_path, key_path, settings=None):
        tlslite_server.__init__ (self, addr, cert_path, key_path, nextProtos=['spdy/3', 'http/1.1'], settings=settings)

    def create_connection (self, conn, addr):
        if conn.next_proto == b'spdy/3':
            return spdy_connection (self, conn, addr)
        else:
            return connection (self, conn, addr)

class spdy_openssl_server (openssl_server):

    protocol = 'spdy'

    def create_connection (self, conn, addr):
        # ensure that negotiation finishes...
        if conn.ssl.get_next_protos_negotiated() == b'spdy/3.1':
            return spdy_connection (self, conn, addr)
        else:
            return connection (self, conn, addr)

# --------------------------------------------------------------------------------
#                             spdy client
# --------------------------------------------------------------------------------

from coro.http import client as http_client

class spdy_client_request (http_client.request):

    _has_body = False

    def wake (self):
        if self.rfile and self.force:
            self.content = self.rfile.read()
        self.latch.wake_all()
        if self.rfile and not self.force:
            self.rfile.wait()

    def wait (self):
        pass

    def has_body (self):
        return self._has_body

class spdy_client (spdy_protocol, http_client.client):

    def __init__ (self, host, port=443, conn=None, inflight=100):
        self.counter = 1
        self.deflate = deflator()
        self.inflate = inflator()
        self.send_mutex = coro.mutex()
        http_client.client.__init__ (self, host, port, conn, inflight)
        # replace the fifo with a dictionary (spdy is not serialized)
        self.pending = {}

    def read_thread (self):
        try:
            self.read_frames()
        except coro.ClosedError as err:
            for sid, req in self.pending.iteritems():
                req.set_error (err)

    def close (self):
        self.conn.close()

    def push_syn_stream (self, headers, has_data):
        sid = self.counter
        self.counter += 1
        if not has_data:
            flags = 0x01
        else:
            flags = 0x00
        asid, pri = 0, 0
        name_vals = self.pack_http_header (headers)
        frame = self.pack_control_frame (
            0x01, flags,
            ''.join ([struct.pack ('>LLH', sid, asid, pri), name_vals])
        )
        with self.send_mutex:
            self.send_frame (frame)
        return sid

    def send_frame (self, frame):
        with self.send_mutex:
            return self.conn.send (frame)

    def push_data_frame (self, stream_id, data, last):
        if last:
            flags = FLAG_FIN
        else:
            flags = 0
        self.send_frame (self.pack_data_frame (stream_id, flags, data))

    def frame_syn_reply (self, flags, data):
        sid, _ = struct.unpack ('>LH', data[:6])
        hs = self.unpack_http_header (data[6:])
        req = self.pending.get (sid, None)
        if req is None:
            self.log ('orphaned syn_reply, sid=%r' % (sid,))
        else:
            req.version = hs.get_one ('version')
            req.reply_code, req.reason = hs.get_one ('status').split(' ', 1)
            req.rheader = hs
            if not flags & FLAG_FIN:
                # we have content...
                req.rfile = spdy_file (hs, None)
                req._has_body = True
            else:
                del self.pending[sid]
                req._has_body = False

    def handle_data_frame (self, sid, flags, data):
        req = self.pending.get (sid, None)
        if req is None:
            self.log ('orphaned data frame sid=%r' % (sid,))
        else:
            req.rfile.content_fifo.push (data)
            if flags & FLAG_FIN:
                req.rfile.content_fifo.push (None)
                del self.pending[sid]

    def send_request (self, method, uri, headers, content=None, force=False):
        try:
            self.inflight.acquire (1)
            req = spdy_client_request (method.upper(), uri, headers, content, force)
            sid = self._send_request (method, uri, headers, content)
            self.pending[sid] = req
            return req
        finally:
            self.inflight.release (1)

    def _send_request (self, method, uri, headers, content):
        if not headers.has_key ('host'):
            headers['host'] = self.host
        if content:
            has_data = True
        else:
            has_data = False
        headers.set_one (':method', method)
        headers.set_one (':scheme', 'https')
        headers.set_one (':path', uri)
        headers.set_one (':version', 'HTTP/1.1')
        sid = self.push_syn_stream (headers, has_data)
        if content:
            # tricky, hold one block back
            last = None
            for block in content:
                if last:
                    self.push_data_frame (sid, block, False)
                last = block
            self.push_data_frame (sid, last, True)
        return sid
