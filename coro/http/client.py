# -*- Mode: Python -*-

import re
import coro
import coro.read_stream
from protocol import http_file, header_set, latch

W = coro.write_stderr

class HTTP_Protocol_Error (Exception):
    pass

class Bad_Response (HTTP_Protocol_Error):
    pass

# viewed at its core, HTTP is a two-way exchange of messages,
#   some of which may have content associated with them.

# two different usage patterns for pipelined requests:
# 1) requests are made by different threads
# 2) requests are made by a single thread
#
# we accommodate both patterns here.
# for #2, use the lower-level send_request() method, for #1,
#   use GET, PUT, etc...

class request:

    def __init__ (self, method, uri, headers, content=None, force=True):
        self.method = method
        self.uri = uri
        self.qheaders = headers
        self.latch = latch()
        self.force = force
        self.qcontent = content
        self.content = None
        self.response = None
        self.rheader = None
        self.rfile = None

    def wake (self):
        "signal that a reply to this request has been received"
        if self.rfile and self.force:
            self.content = self.rfile.read()
        self.latch.wake_all()
        if self.rfile and not self.force:
            self.rfile.wait()

    def wait (self):
        "wait for the reply to be recieved. (if force=True wait for content as well)"
        return self.latch.wait()

    def abort (self):
        "abort this client request"
        self.latch.wake_all()
        if self.rfile:
            self.rfile.abort()

    def has_body (self):
        # XXX duplicates logic from server.py:http_request
        h = self.rheader
        if h.has_key ('transfer-encoding'):
            return True
        else:
            probe = h.get_one ('content-length')
            if probe:
                try:
                    size = int (probe)
                    if size == 0:
                        return False
                    elif size > 0:
                        return True
                    else:
                        return False
                except ValueError:
                    return False
            elif h.test ('connection', 'close') and self.method == 'GET':
                # XXX unless 204
                return True
            else:
                return False

class client:

    def __init__ (self, host, port=80, conn=None, inflight=100):
        self.host = host
        self.inflight = coro.semaphore (inflight)
        if conn is None:
            self.conn = coro.tcp_sock()
            self.conn.connect ((host, port))
        else:
            self.conn = conn
        self.stream = coro.read_stream.sock_stream (self.conn)
        self.pending = coro.fifo()
        coro.spawn (self.read_thread)

    def read_thread (self):
        while 1:
            req = self.pending.pop()
            if req is None:
                break
            else:
                self._read_message (req)
                if not req.response:
                    break
                else:
                    req.wake()

    def close (self):
        self.pending.push (None)
        self.conn.close()

    response_re = re.compile ('([^ ]+) ([0-9][0-9][0-9]) (.+)')

    def _read_message (self, req):
        line = self.stream.read_line()
        if not line:
            raise HTTP_Protocol_Error ('unexpected close')
        req.response = line[:-2]
        m = self.response_re.match (req.response)
        if not m:
            raise Bad_Response (req.response)
        else:
            req.version, req.reply_code, req.reason = m.groups()
        lines = []
        while 1:
            line = self.stream.read_line()
            if not line:
                raise HTTP_Protocol_Error ('unexpected close')
            elif line == '\r\n':
                break
            else:
                lines.append (line[:-2])
        req.rheader = h = header_set (lines)
        if req.has_body():
            req.rfile = http_file (h, self.stream)

    def send_request (self, method, uri, headers, content=None, force=False):
        try:
            self.inflight.acquire (1)
            req = request (method, uri, headers, content, force)
            self._send_request (method, uri, headers, content)
            self.pending.push (req)
            return req
        finally:
            self.inflight.release (1)

    def _send_request (self, method, uri, headers, content):
        if not headers.has_key ('host'):
            headers['host'] = self.host
        if content:
            if type(content) is str:
                headers['content-length'] = len(content)
            elif not headers.has_key ('content-length'):
                headers['transfer-encoding'] = 'chunked'
        req = (
            '%s %s HTTP/1.1\r\n'
            '%s\r\n' % (method, uri, headers)
        )
        self.conn.send (req)
        # XXX 100 continue
        if content:
            if type(content) is str:
                self.conn.send (content)
            elif headers.has_key ('content-length'):
                clen = int (headers.get_one ('content-length'))
                slen = 0
                for block in content:
                    self.conn.send (block)
                    slen += len(block)
                    if slen > clen:
                        raise HTTP_Protocol_Error ("content larger than declared length", clen, slen)
                else:
                    if slen != clen:
                        raise HTTP_Protocol_Error ("content smaller than declared length", clen, slen)
            else:
                # chunked encoding
                for block in content:
                    if block:
                        self.conn.writev (['%x\r\n' % (len (block),), block])
                self.conn.send ('0\r\n')

    def GET (self, uri, **headers):
        headers = header_set().from_keywords (headers)
        req = self.send_request ('GET', uri, headers, force=True)
        req.wait()
        return req

    def GET_file (self, uri, **headers):
        headers = header_set().from_keywords (headers)
        req = self.send_request ('GET', uri, headers, force=False)
        req.wait()
        return req

    def PUT (self, uri, content, **headers):
        headers = header_set().from_keywords (headers)
        req = self.send_request ('PUT', uri, headers, content, force=True)
        req.wait()
        return req

    def POST (self, uri, content, **headers):
        headers = header_set().from_keywords (headers)
        req = self.send_request ('POST', uri, headers, content, force=True)
        req.wait()
        return req
