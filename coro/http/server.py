# -*- Mode: Python -*-

# history: this code traces all the way back to medusa, through egroups, then ironport, and into shrapnel.
#  Very Rewritten in Feb 2012.

import coro
import errno
import http_date
import mimetypes
import os
import re
from coro import read_stream
import socket
import stat
import sys
import time
import zlib

from protocol import latch, http_file, header_set, HTTP_Upgrade

from coro.log import Facility

LOG = Facility ('http')

W = sys.stderr.write

__version__ = '0.1'

class request_stream:

    def __init__ (self, conn, stream):
        self.timeout = conn.server.client_timeout
        self.conn = conn
        self.stream = stream

    def get_request (self):
        request_line = self.stream.read_line()
        if not request_line:
            raise StopIteration
        else:
            # read header
            lines = []
            while 1:
                line = self.stream.read_line()
                # XXX handle continuation lines
                if line == '':
                    raise StopIteration
                elif line == '\r\n':
                    break
                else:
                    lines.append (line[:-2])
        return http_request (self.conn, request_line[:-2], header_set (lines))

    def gen_requests (self):
        # read HTTP requests on this stream
        while 1:
            try:
                request = coro.with_timeout (self.timeout, self.get_request)
            except coro.TimeoutError:
                return
            else:
                yield request
                # can't read another request until we finish reading this one
                # [it might have a body]
                request.wait_until_read()

class connection:

    protocol = 'http'

    def __init__ (self, server, conn, addr):
        self.server = server
        self.stream = None
        self.conn = conn
        self.peer = addr

    def run (self):
        self.stream = read_stream.sock_stream (self.conn)
        upgrade = False
        try:
            try:
                for request in request_stream (self, self.stream).gen_requests():
                    if request.bad:
                        # bad request
                        request.error (400)
                    else:
                        try:
                            handler = self.pick_handler (request)
                            if handler:
                                # XXX with_timeout() ?
                                handler.handle_request (request)
                            else:
                                request.error (404)
                            request.wait_until_done()
                        except (coro.TimeoutError, coro.Interrupted):
                            raise
                        except HTTP_Upgrade:
                            upgrade = True
                            break
                        except Exception:
                            tb = coro.traceback_data()
                            self.server.log ('error', repr(request), tb)
                            request.error (500, tb)
            except (OSError, coro.TimeoutError, coro.ClosedError):
                pass
        finally:
            if not upgrade:
                self.conn.close()

    def log (self, *data):
        self.server.log (*data)

    def pick_handler (self, request):
        for handler in self.server.handlers:
            if handler.match (request):
                return handler
        return None

    def send (self, data):
        return self.conn.send (data)

    def close (self):
        self.conn.close()


class http_request:
    request_count = 0
    # <path>;<params>?<query>#<fragment>
    path_re = re.compile ('(/[^;?#]*)(;[^?#]*)?(\?[^#]*)?(#.*)?')
    # <method> <uri> HTTP/<version>
    request_re = re.compile ('([^ ]+) ([^ ]+) *(HTTP/([0-9.]+))?')
    # shadowed instance variables
    chunking     = False
    close        = False
    is_done      = False
    sent_headers = False
    bad          = False
    body_done    = False
    file         = None

    def __init__ (self, client, request, headers):
        self.reply_headers = header_set()
        self.reply_code = 200
        http_request.request_count = http_request.request_count + 1
        self.request_number = http_request.request_count
        self.request = request
        self.request_headers = headers
        self.client = client
        self.server = client.server
        self.tstart = time.time()  # XXX use coro.now
        self.peer = client.peer
        self.output = buffered_output (self.client.conn)
        self.done_cv = latch()
        self.deflate = None
        m = http_request.request_re.match (request)
        if m:
            (self.method, self.uri, ver, self.version) = m.groups()
            self.method = self.method.lower()
            if not self.version:
                self.version = "0.9"
            m = http_request.path_re.match (self.uri)
            if m:
                (self.path, self.params, self.query, self.frag) = m.groups()
            else:
                self.bad = True
        else:
            self.version = "1.0"
            self.bad = True
        if self.has_body():
            self.file = http_file (headers, client.stream)

    def __repr__ (self):
        return '<http request from %r : %r>' % (self.peer, self.request,)

    def wait_until_read (self):
        "wait until this entire request body has been read"
        if self.file:
            self.file.done_cv.wait()

    def wait_until_done (self):
        "wait until this request is done (i.e, the response has been sent)"
        if not self.is_done:
            self.done_cv.wait()

    def has_body (self):
        if self.request_headers.has_key ('transfer-encoding'):
            # 4.4 ignore any content-length
            return True
        else:
            probe = self.request_headers.get_one ('content-length')
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

    def can_deflate (self):
        acc_enc = self.request_headers.get_one ('accept-encoding')
        if acc_enc:
            for kind in acc_enc.split (','):
                if kind.strip().lower() == 'deflate':
                    return True
        return False

    def set_deflate (self):
        "set this request for on-the-fly compression (via zlib DEFLATE)"
        if self.can_deflate():
            self.deflate = zlib.compressobj()
            self['content-encoding'] = 'deflate'
            # http://zoompf.com/blog/2012/02/lose-the-wait-http-compression
            # Note: chrome,firefox,safari,opera all handle the header.  Not MSIE, sigh.  Discard it.
            assert (self.deflate.compress ('') == '\x78\x9c')
            return self.deflate

    def push (self, data, flush=False):
        "push output data for this request.  buffered, maybe chunked, maybe compressed"
        if not self.sent_headers:
            self.sent_headers = 1
            self.output.write (self.get_headers())
            if self.chunking:
                self.output.set_chunk()
        if self.deflate:
            if data:
                data = self.deflate.compress (data)
            if flush:
                data += self.deflate.flush()
        if data:
            self.output.write (data)

    def done (self):
        if self.is_done:
            W ('done called twice?\n')
            return
        if not self.sent_headers:
            self.push ('')
        if self.deflate:
            self.push ('', flush=True)
        self.output.flush()
        if self.close:
            self.client.close()
        self.is_done = True
        self.client.server.log (*self.log_line())
        self.done_cv.wake_all()

    # note: the difference of meaning between getitem/setitem
    def __getitem__ (self, key):
        # fetch a request header
        # use this only when you expect at most one of this header.
        return self.request_headers.get_one (key)

    def __setitem__ (self, key, val):
        # set a reply header
        self.reply_headers[key] = val

    def get_headers (self):
        chunked = False
        # here is were we decide things like keep-alive, 1.0 vs 1.1, chunking, etc.
        hi = self.request_headers
        ho = self.reply_headers
        connection = hi.get_one('connection')
        if connection:
            connection_tokens = [x.strip() for x in connection.split(',')]
        else:
            connection_tokens = ()
        close_it = False
        if self.version == '1.1':
            if 'close' in connection_tokens:
                close_it = True
            elif not ho.get_one ('content-length'):
                ho['transfer-encoding'] = 'chunked'
                chunked = True
        elif self.version == '1.0':
            if 'keep-alive' in connection_tokens:
                if not ho.get_one ('content-length'):
                    close_it = True
                else:
                    ho['connection'] = 'keep-alive'
            else:
                close_it = True
        elif self.version == '0.9':
            close_it = True

        if close_it:
            ho['connection'] = 'close'

        self.chunking = chunked
        self.close = close_it

        ho['server'] = 'shrapnel httpd/%s' % __version__
        ho['date'] = http_date.build_http_date (coro.now_usec / coro.microseconds)

        return self.response (self.reply_code) + '\r\n' + str (self.reply_headers) + '\r\n'

    def response (self, code=200):
        message = self.responses[code]
        self.reply_code = code
        return 'HTTP/%s %d %s' % (self.version, code, message)

    def error (self, code, reason=None):
        self.reply_code = code
        message = self.responses[code]
        s = self.DEFAULT_ERROR_MESSAGE % {
            'code': code, 'message': message, 'reason': reason
        }
        self['content-length'] = str(len(s))
        self['content-type'] = 'text/html'
        self.push (s, flush=True)
        self.done()

    def log_line (self):
        return (
            self.client.protocol,
            self.peer, self.request, self.reply_code,
            self.output.sent,
            '%.4f' % (time.time() - self.tstart),
        )

    responses = {
        100: "Continue",
        101: "Switching Protocols",
        200: "OK",
        201: "Created",
        202: "Accepted",
        203: "Non-Authoritative Information",
        204: "No Content",
        205: "Reset Content",
        206: "Partial Content",
        300: "Multiple Choices",
        301: "Moved Permanently",
        302: "Moved Temporarily",
        303: "See Other",
        304: "Not Modified",
        305: "Use Proxy",
        400: "Bad Request",
        401: "Unauthorized",
        402: "Payment Required",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        406: "Not Acceptable",
        407: "Proxy Authentication Required",
        408: "Request Time-out",
        409: "Conflict",
        410: "Gone",
        411: "Length Required",
        412: "Precondition Failed",
        413: "Request Entity Too Large",
        414: "Request-URI Too Large",
        415: "Unsupported Media Type",
        500: "Internal Server Error",
        501: "Not Implemented",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Time-out",
        505: "HTTP Version not supported"
    }

    # Default error message
    DEFAULT_ERROR_MESSAGE = '\r\n'.join ([
        '<html>',
        '<head>',
        '<title>Error response</title>',
        '</head>',
        '<body>',
        '<h1>Error response</h1>',
        '<p>Error code %(code)d.',
        '<p>Message: %(message)s.',
        '<p>Reason: %(reason)s.',
        '</body>',
        '</html>',
        ''
    ])

# chunking works thus:
#    <data>
# becomes:
#    <hex-length><CRLF>
#    <data><CRLF>
# when done, signal with
#    0<CRLF><CRLF>

class buffered_output:

    "Buffer HTTP output data; handle the 'chunked' transfer-encoding"

    def __init__ (self, conn, size=8000):
        self.conn = conn
        self.size = size
        self.buffer = []
        self.len = 0
        self.sent = 0
        self.chunk_index = -1
        self.chunk_len = 0

    # at this point *exactly*, we want to start chunking the output.
    # this is called immediately after the headers are pushed.
    def set_chunk (self):
        "start chunking here, exactly."
        self.chunk_index = len (self.buffer)

    def get_data (self):
        "get data to send. may chunk."
        data, self.buffer = self.buffer, []
        if self.chunk_index >= 0:
            # chunkify (the post-header portion of) our output list
            data.insert (self.chunk_index, '%x\r\n' % (self.chunk_len,))
            data.append ('\r\n')
            self.chunk_len = 0
            self.chunk_index = 0
        self.len = 0
        return data

    def write (self, data):
        "Push data to the buffer. If the accumulated data goes over the buffer size, send it."
        self.buffer.append (data)
        self.len += len (data)
        if self.chunk_index >= 0:
            self.chunk_len += len (data)
        if self.len >= self.size:
            self.send (self.get_data())

    def flush (self):
        "Flush the data from this buffer."
        data = self.get_data()
        if self.chunk_index >= 0:
            data.append ('0\r\n\r\n')
        self.send (data)

    def send (self, data):
        try:
            self.sent += self.conn.writev (data)
        except AttributeError:
            # underlying socket may not support writev (e.g., tlslite)
            self.sent += self.conn.send (''.join (data))

class server:

    client_timeout = 30

    def __init__ (self):
        self.handlers = []
        self.shutdown_flag = 0
        self.thread_id = None
        self.addr = ()
        self.sock = None

    def log (self, *data):
        LOG (self.addr[0], self.addr[1], *data)

    def push_handler (self, handler):
        self.handlers.append (handler)

    def start (self, addr, retries=5):
        """Start the web server listening on addr in a new coroutine.

        Try up to <retries> time to bind to that address.
        Raises an exception if the bind fails."""

        self.addr = addr
        self.sock = self.create_sock()
        self.sock.set_reuse_addr()
        done = 0
        save_errno = 0
        while not done:
            for x in xrange (retries):
                try:
                    self.sock.bind (addr)
                except OSError, why:
                    if why.errno not in (errno.EADDRNOTAVAIL, errno.EADDRINUSE):
                        raise
                    else:
                        save_errno = 0
                        if why.errno == errno.EADDRINUSE:
                            was_eaddrinuse = 1
                else:
                    done = 1
                    break
                coro.sleep_relative (1)
            else:
                self.log ('cannot bind to %s:%d after 5 attempts, errno = %d' % (addr[0], addr[1], save_errno))
                coro.sleep_relative (15)

        self.sock.listen (1024)
        c = coro.spawn (self.run)
        c.set_name ('%s (%s:%d)' % (self.__class__.__name__, addr[0], addr[1]))

    def run (self):
        self.thread_id = coro.current().thread_id()
        while not self.shutdown_flag:
            try:
                conn, addr = self.accept()
                client = self.create_connection (conn, addr)
                c = coro.spawn (client.run)
                c.set_name ('%s connection on %r' % (self.__class__.__name__, addr,))
            except coro.Shutdown:
                break
            except:
                LOG.exc()
                coro.sleep_relative (0.25)
                continue
        self.sock.close()

    def accept (self):
        return self.sock.accept()

    def create_sock (self):
        # the assumption here is that you would never run an HTTP server
        #   on a unix socket, if you need that then override this method.
        if ':' in self.addr[0]:
            return coro.tcp6_sock()
        else:
            return coro.tcp_sock()

    def create_connection (self, conn, addr):
        return connection (self, conn, addr)

    def shutdown (self):
        self.shutdown_flag = 1
        try:
            # XXX SMR is this really necessary?
            thread = coro.get_thread_by_id (self.thread_id)
            thread.shutdown()
        except KeyError:
            return  # already exited

class tlslite_server (server):

    "https server using the tlslite package"

    def __init__ (self, cert_path, key_path, **handshake_args):
        server.__init__ (self)
        self.handshake_args = handshake_args
        self.cert_path = cert_path
        self.key_path = key_path
        self.read_chain()
        self.read_private()

    def accept (self):
        import tlslite
        while 1:
            conn0, addr = server.accept (self)
            conn = tlslite.TLSConnection (conn0)
            conn.ignoreAbruptClose = True
            conn.handshakeServer (certChain=self.chain, privateKey=self.private, **self.handshake_args)
            return conn, addr

    def read_chain (self):
        "cert chain is all in one file, in LEAF -> ROOT order"
        import tlslite
        delim = '-----END CERTIFICATE-----\n'
        data = open (self.cert_path).read()
        certs = data.split (delim)
        chain = []
        for cert in certs:
            if cert:
                x = tlslite.X509()
                x.parse (cert + delim)
                chain.append (x)
        self.chain = tlslite.X509CertChain (chain)

    def read_private (self):
        import tlslite
        self.private = tlslite.parsePEMKey (
            open (self.key_path).read(),
            private=True
        )

class openssl_server (server):

    def __init__ (self, ctx, verify=False):
        self.ctx = ctx
        # XXX do something with verify
        self.verify = verify
        server.__init__ (self)

    def create_sock (self):
        import coro.ssl
        import socket
        if ':' in self.addr[0]:
            domain = socket.AF_INET6
        else:
            domain = socket.AF_INET
        return coro.ssl.sock (self.ctx, domain=domain)
