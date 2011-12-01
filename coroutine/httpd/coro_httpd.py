# -*- Mode: Python; tab-width: 4 -*-

# Copyright 1999 by eGroups, Inc.
#
#                         All Rights Reserved
#
# Permission to use, copy, modify, and distribute this software and
# its documentation for any purpose and without fee is hereby
# granted, provided that the above copyright notice appear in all
# copies and that both that copyright notice and this permission
# notice appear in supporting documentation, and that the name of
# eGroups not be used in advertising or publicity pertaining to
# distribution of the software without specific, written prior
# permission.
#
# EGROUPS DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE,
# INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS, IN
# NO EVENT SHALL EGROUPS BE LIABLE FOR ANY SPECIAL, INDIRECT OR
# CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
# OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
# NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
# CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

VERSION_STRING = '$Id$'
__split_vers__ = VERSION_STRING.split()
__version__ = (len(__split_vers__) > 2) and __split_vers__[2] or '1.0'

#
# coro_ehttpd
#   This is an infrastructure for having a http server using coroutines.
#   There are three major classes defined here:
#   http_client
#     This is a descendent of coro.Thread.  It handles the connection
#     to the client, spawned by http_server.  Its run method goes through
#     the stages of reading the request, filling out a http_request and
#     finding the right handler, etc.
#   http_request
#     This object collects all of the data for a request.  It is initialized
#     from the http_client thread with the http request data, and is then
#     passed to the handler to receive data.  It attempts to enforce a valid
#     http protocol on the response
#   http_server
#     This is a thread which just sits accepting on a socket, and spawning
#     http_clients to handle incoming requests
#
#   Additionally, the server expects http handler classes which respond
#   to match and handle_request.  There is an example class,
#   http_file_handler, which is a basic handler to respond to GET requests
#   to a document root.  It'll return any file which exists.
#
#   To use, implement your own handler class which responds to match and
#   handle_request.  Then, create a server, add handlers to the server,
#   and start it.  You then need to call the event_loop yourself.
#   Something like:
#
#     server = http_server(args = (('0.0.0.0', 7001),))
#     file_handler = http_file_handler ('/home/htdocs/')
#     server.push_handler (file_handler)
#     server.start()
#     coro.event_loop(30.0)
#

# we would like to handle persistent connections correctly.
# Here's the control flow:
# <server> : <-- connection
#   create <client>
#     while get_request():  <-- request
#       create <request>
#         get_handler().process_request()
#
# The difficulty (compared to medusa) is that the handler
# actually sends all the data, including the header.  So
# the request object doesn't necessarily know what's going
# on.
#   1) we should force handlers to use an interface for setting headers. [i.e., CGI
#      won't call "send('Content-Type: text/html')", it will use a method on the
#      request object].
#   2) <request> should monitor changes to the headers.
#   3) a few standardized headers should have specific methods to improve performance.
#
# This still doesn't necessarily solve the difficult issue of persistence.
#   1) Will we pipeline?  Only if we buffer on read. [I think we do].
#   2) what about chunking?  We could just always use chunking. [no, that won't work
#      because then browsers won't know how big files are]
#
# Suggestion: how about a dynamic-inheritance feature for setting headers?
# For example, use __getattr__ to catch anything beginning with {set,get}_header_xxx.
# This would allow subclasses to override specific methods. [could/should we use an
# inheritance to handle http/1.0 vs http/1.1?]
#
# [...]
# Ok, most of that is now done, although a bit of a mess.  Who is reponsible for
# closing, in the event of http/1.0 and conn:close??
#
# some nastiness: important to understand exactly which coroutine each piece of code
#  needs to run in, and whether it runs parallel or as a subroutine of some other coroutine.
#
# coroutines:
#   1) server (accept loop)
#   2) client (request loop)
#   3) session (request loop)
#
# For example, i'm pretty sure that the 'session' coroutine needs to execute as
# 'subroutine' of the 'client' coroutine; i.e. when the session yields(), it does
# so back to the client coroutine, not to main.

import coro
import coro_ssl
import errno
import http_date
import mime_type_table
import os
import re
import read_stream
import socket
import sslip
import stat
import sys
import time

try:
    import qlog

except:
    class Qlog:
        def __call__(self, *args, **kw):
            # print "Calling", self.name
            return None

        def __getattr__(self, name):
            self.name = name
            return self

        def __repr__(self):
            return 'null log daemon'

    qlog = Qlog()


ssl_ctx = None

def init_ssl(protocol=sslip.SSLV23_SERVER_METHOD):
    global ssl_ctx

    if not ssl_ctx:
       ssl_ctx = coro_ssl.ssl_ctx(protocol)
       ssl_ctx.set_ciphers ('RC4-SHA:RC4-MD5:ALL')

def update_cert_key(cert, key, passwd='', chain=()):
    global ssl_ctx

    if cert and key:
       cert_obj = sslip.read_pem_cert(cert)
       ssl_ctx.use_cert(cert_obj, chain)

       key_obj = sslip.read_pem_key(key, passwd)
       ssl_ctx.use_key(key_obj)

class http_client:

    def __init__ (self, group=None, target=None, name=None, logfp=sys.stderr, args=(), kwargs={}):
        self.stream = None
        self.buffer = ''
        self._bytes = 0
        self.logfp = logfp

    def run (self, conn, peer, server_obj, handlers):
        self.conn = conn
        self.server = server_obj
        self.peer = peer
        # Note that peer could be a fake address, and server_obj can be None.
        # These indicate a "backdoor" request from the gui.

        try:
            try:
                count = 0

                qlog.write('WEBUI.CONN_INIT', 'http', id(self), peer[0], peer[1])

                while 1:
                    if self.server and self.server.shutdown_flag:
                        break
                    try:
                        # We use self.stream to read the header line-by-line
                        # and then switch to reading directly from the socket
                        # for the body (if needed).  Reuse the previous
                        # instance if it exists, to support HTTP pipelining.
                        if not self.stream:
                           self.stream = read_stream.stream_reader(self.conn.recv)
                        request_line = self.read_line()
                        if not request_line:
                            break
                    except socket.error:
                        qlog.write('WEBUI.CONN_ERROR', 'http', id(self), 'socket error')
                        break

                    count = count + 1
                    headers = self.read_header()
                    #print '\n'.join (headers) + '\n\n'
                    request = http_request (self, request_line, headers)
                    request.read_body()
                    if request._error:
                        # Bad Request
                        request.error (400)
                        return
                    else:
                        try:
                            try:
                                handler = self.pick_handler (handlers, request)

                                if handler:
                                    handler.handle_request (request)
                                else:
                                    self.not_found (request)

                                if not request._done:
                                    request.done()
                            except OSError, err:
                                if err[0] == errno.EPIPE:
                                    pass # ignore broken pipe error
                                else:
                                    raise # process exception in outer try
                        # These exceptions are used inside the coro
                        # stuff and shouldn't be thrown away
                        except (coro.TimeoutError, coro.Interrupted):
                            raise
                        except:
                            tb = coro.compact_traceback()
                            ## sys.stderr.write (repr(tb))
                            request.error (500, tb)
                            qlog.write('COMMON.APP_FAILURE',
                                       tb + ' request: ' + `request`)
                            tb = None

                        if request._close:
                            # ok, this gets interesting.    the connection needs to close
                            # here. the finally clause below isn't getting hit because
                            # the session and client are running in the same coroutine.
                            # that's bad, I think.
                            conn.close()
                            break

                    # this should be a policy decision of the owner of logfp
                    # self.logfp.flush()
            except read_stream.BufferOverflow:
                # Indicates a request header that exceeded the line
                # buffer, which may indicate an attack on the server.
                # We just close the connection without a response.
                # TODO:lrosenstein - log this since it may be an attack?
                qlog.write('WEBUI.CONN_ERROR', 'http',
                                                 id(self), 'line buffer limit exceeded')
                pass
            except sslip.Error, why:
                # Most likely a problem with SSL negotiation
                qlog.write('WEBUI.CONN_ERROR',
                           'https',
                            id(self),
                            why[1])
                pass
            except OSError, err:
                # We got some kind of I/O error that wasn't handled
                # elsewhere.  Since this seem to happen because the
                # client closed the connection, it is safe to ignore
                # the exception.
                qlog.write('WEBUI.CONN_ERROR',
                    'http', id(self), 'OS error %s' % str(err[1]))
                pass
            except coro.TimeoutError:
                # Either a timeout from coro_ssl or a timeout
                # on a backdoor GUI request (see gui.py)
                pass
        finally:
            conn.close()

    def not_found (self, request):
        request.error (404)

    def pick_handler (self, handlers, request):
        for handler in handlers:
            if handler.match (request):
                return handler

        return None

    # This is for handlers that process PUT/POST themselves.    This whole
    # thing needs to be redone with a file-like interface to 'stdin' for
    # requests, and we need to think about HTTP/1.1 and pipelining,
    # etc...

    def read (self, size):
        if self.stream:
            self.buffer = self.stream.drain_buffer()
            self.stream = None

        while len(self.buffer) < size:
            result = self.conn.recv(size-len(self.buffer))
            if result:
                self.buffer = self.buffer + result
            else:
                break # connection closed

        result = self.buffer[:size]
        self.buffer = self.buffer[size:]
        return result

    def read_line (self):
        try:
            return coro.with_timeout(300, self._read_line)
        except coro.TimeoutError:
            return '' # EOF

    def _read_line (self):
        """Read a line of input.  Return '' on EOF or error.

        TODO:lrosenstein - we should probably distinguish EOF/error
        from blank lines.  This would affect read_header(), which
        could return an incomplete set of headers if the connection
        closed prematurely."""

        while 1:
            try:
                (ln, eof) = self.stream.read_line()
                if eof:
                    return '' # throw away incomplete lines
                else:
                    return ln
            except coro.TimeoutError: # ssl sockets timeout
                # Ignored to fix bug 3185.  The problem was that httpd
                # was closing the connection after 30 sec, but IE/Win
                # would try to use the connection and fail with a wierd
                # error.  Now, we have a 5 min timeout in read_line
                # above, which applies to SSL and non-SSL connections
                # to prevent clients from tying up server resources
                # indefinitely.
                continue

            except OSError, why:
                if why[0] == errno.ECONNRESET:
                    return '' # signal an eof to the caller
                else:
                    raise

    def read_header (self):
        header = []
        while 1:
            l = self.read_line()
            if not l:
                break
            else:
                header.append (l)
        return header

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

    # shadowed instance variable
    _chunking = 0
    _close = 0
    _done = 0
    _sent_headers = 0
    _error = 0
    _user_id = '-'
    _session_id = '-'

    def __init__ (self, client, request, headers):
        self._reply_headers = {}
        self._reply_cookies = ()
        self._reply_code = 200
        http_request.request_count = http_request.request_count + 1
        self._request_number = http_request.request_count
        self._request = request
        self._request_headers = headers
        self._client = client
        self._server = client.server
        self._tstart = time.time()
        self._sent_bytes = 0
        self._whom = client.conn.getpeername()
        m = http_request.request_re.match (request)
        if m:
            (self._method, self._uri, ver, self._version) = m.groups()
            self._method = self._method.lower()
            if not self._version:
                self._version = "0.9"
            m = http_request.path_re.match (self._uri)
            if m:
                (self._path, self._params, self._query, self._frag) = m.groups()
                if self._query and self._query[0] == '?':
                    self._query = self._query[1:]
            else:
                self._error = 1
        else:
            self._version = "1.0"
            self._error = 1

    def read_body(self):
        """Read the message body, if any, so that it's cleared from
        the input stream.  This avoids problems with keep-alives if
        the request handler doesn't read the body itself.

        This used to be  done in the __init__method, but that can
        lead to a fatal error in the Python interpreter (see bug 3367).

        The ultimate solution is to fix the way connections are handled
        to ensure that we don't reuse the connection if the body wasn't
        fully read by the request handler."""

        self._body = ''
        clen = self.get_request_header('Content-Length')
        if clen:
            try:
                clen = int(clen)
                self._body = coro.with_timeout(
                    60,
                    self._client.read,
                    clen)
                if len(self._body) < clen:
                    qlog.write('WEBUI.CONN_ERROR',
                               'http', id(self),
                                'Truncated body (%d<%d) (req:%s)' % \
                                (len(self._body), clen, self._request))
                    self._error = 1 # didn't get the body we were promised
            except coro.TimeoutError:
                qlog.write('WEBUI.CONN_ERROR',
                           'http', id(self),
                            'Body read timeout (req:%s)' % self._request)
                self._error = 1
            except ValueError:
                qlog.write('WEBUI.CONN_ERROR',
                           'http', id(self),
                            'Invalid Content-Length (%s) (req:%s)' % \
                            (clen, self._request)
                            )
                self._error = 1

    def is_secure(self):
       return self._client.server and self._client.server.is_secure()

    # --------------------------------------------------
    # request header management
    # --------------------------------------------------

    _header_re = re.compile (r'([^: ]+): (.*)')

    def get_request_header (self, header):
        header = header.lower()
        for h in self._request_headers:
            m = self._header_re.match (h)
            if m:
                name, value = m.groups()
                if name.lower() == header:
                    return value
        return ''

    # --------------------------------------------------
    # reply header management
    # --------------------------------------------------

    # header names are case-insensitive, and we need to be
    # able to reliably query a request for certain headers,
    # thus the sprinkling of key.lower() calls.

    def __setitem__ (self, key, value):
        self._reply_headers[key.lower()] = value

    def __getitem__ (self, key):
        return self._reply_headers[key.lower()]

    def has_key (self, key):
        return self._reply_headers.has_key (key.lower())

    # TODO:lrosenstein - it's legal and necessary to have multiple
    # TODO:lrosenstein - Set-Cookie headers.  Handle these as a special case.
    def set_reply_cookies(self, cookies):
        """Set sequence of cookies to be used in the response."""

        self._reply_cookies = cookies

    # --------------------------------------------------
    # reading request
    # --------------------------------------------------

    def read (self, size):
       data = self._body[:size]
       self._body = self._body[size:]
       return data


    # --------------------------------------------------
    # sending response
    # --------------------------------------------------

    def send (self, data):
        self._sent_bytes = self._sent_bytes + len(data)
        return self._client.send (data)

    # chunking works thus:
    #    <data>
    # becomes:
    #    <hex-length><CRLF>
    #    <data><CRLF>
    # when done, signal with
    #    0<CRLF><CRLF>

    # ok, I admit this is now something of a mess.
    # this could maybe be better if we could:
    # 1) distinguish replies that have content
    #    [we could even detect it automatically?]
    # 2) be more explicit about buffering the header

    def push (self, data):
        if not self._sent_headers:
            self._sent_headers = 1
            headers = self.get_headers()
        else:
            headers = ''
        if data:
            if self._chunking:
                self.send (headers + '%x\r\n%s\r\n' % (len(data), data))
            else:
                self.send (headers + data)
        else:
            self.send (headers)

    def done (self, with_body=1):
        if not self._sent_headers:
            self.send_headers()
        if with_body and self._chunking:
            # note: there's an invisible 'footer' between the pair of CRLF's.
            #  it can be used to send certain additional types of headers.
            self.send ('0\r\n\r\n')
        if self._close:
            self._client.close ()
        self._done = 1
        qlog.write('WEBUI.HTTP_REQUEST',
                   self._client.peer[0],
                    self._user_id,
                    self._session_id,
                    self._reply_code,
                    self._request,
                    '' # XXX: User agent
                    )
        #self._client.logfp.write (self.log())

    def get_headers (self):
        chunking = 0
        # here is were we decide things like keep-alive, 1.0 vs 1.1, chunking, etc.
        connection = self.get_request_header('connection').lower()
        connection_tokens = [ x.strip() for x in connection.split(',')]
        close_it = 0
        if self._version == '1.0':
            if 'keep-alive' in connection_tokens:
                if not self.has_key ('content-length'):
                    close_it = 1
                else:
                    self['Connection'] = 'Keep-Alive'
            else:
                close_it = 1
        elif self._version == '1.1':
            if 'close' in connection_tokens:
                close_it = 1
            elif not self.has_key ('content-length'):
                if self.has_key ('transfer-encoding'):
                    if self['Transfer-Encoding'] == 'chunked':
                        chunking = 1
                    else:
                        close_it = 1
                else:
                    self['Transfer-Encoding'] = 'chunked'
                    chunking = 1
        elif self._version == '0.9':
            close_it = 1

        if close_it:
            self['Connection'] = 'close'
            self._close = 1

        self._chunking = chunking

        self['Server'] = 'IronPort httpd/%s' % __version__
        self['Date'] = http_date.build_http_date (coro.now_usec / coro.microseconds)

        headers = [self.response (self._reply_code)] + [
            ('%s: %s' % x) for x in self._reply_headers.items()
            ] + [
            (x.output()) for x in self._reply_cookies
            ] + ['\r\n']
        #print '\n'.join (headers) + '\n\n'
        return '\r\n'.join (headers)

    def send_headers (self):
        # this will force the headers to be sent...
        self.push ('')

    def response (self, code=200):
        message = self.responses[code]
        self._reply_code = code
        return 'HTTP/%s %d %s' % (self._version, code, message)

    def error (self, code, reason=None, with_body=1):
        self._reply_code = code
        if with_body:
            message = self.responses[code]
            s = self.DEFAULT_ERROR_MESSAGE % {
                'code': code, 'message': message, 'reason': reason
            }
            self['Content-Length'] = len(s)
            self['Content-Type'] = 'text/html'
            self.push (s)
            self.done (with_body)
        else:
            self.done (with_body)
        self._error = 1

    def set_user_id(self, user_id, session_id=None):
       self._user_id = user_id or '-'
       self._session_id = session_id or '-'

    def log_date_string (self, when):
        return time.strftime (
                        '%d/%b/%Y:%H:%M:%S ',
                        time.gmtime(when)
                        ) + tz_for_log

    def log (self):
        tend = time.time()
        whom = '%s:%d ' % self._whom
        return '%s - - [%s] "%s" %d %d %0.2f\n' % (
            whom,
            self.log_date_string (tend),
            self._request,
            self._reply_code,
            self._sent_bytes,
            tend - self._tstart
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

import pprint
class coro_status_handler:

    def match (self, request):
        return request._path.split ('/')[1] == 'status'

    def clean (self, s):
        s = s.replace ('<','&lt;')
        s = s.replace ('>','&gt;')
        return s

    def handle_request (self, request):
        request['Content-Type'] = 'text/html'
        request.push ('<p>Listening on\r\n')
        request.push ( repr(request._server.addr) )
        request.push ('</p>\r\n')
        request.push ('<p>Request dump</p><PRE>\r\n')
        request.push ( pprint.pformat(request) )
        request.push ('</PRE>\r\n')
        request.push ('<ul>\r\n')
        all_threads = map(lambda x: (x[1], coro.where(x[1])), coro.all_threads.items())
        for thread, traceback in all_threads:
            request.push ('<li>%s\r\n' % self.clean (repr(thread)))
            request.push ('<pre>\r\n')
            for level in traceback[1:-1].split ('|'):
                [file, fun, line] = level.split(':')
                request.push ('<b>%20s</b>:%03d %s\r\n' % (fun,int(line),file))
            request.push ('</pre>')
        request.push ('</ul>\r\n')
        request.done()

class http_file_handler:
    def __init__ (self, doc_root):
        self.doc_root = doc_root
        self.logfp = sys.stderr

    def match (self, request):
        path = request._path
        filename = os.path.join (self.doc_root, path[1:])
        if os.path.exists (filename):
            return 1
        return 0

    crack_if_modified_since = re.compile ('([^;]+)(; length=([0-9]+))?$', re.IGNORECASE)

    def handle_request (self, request):
        path = request._path
        filename = os.path.join (self.doc_root, path[1:])

        if request._method not in ('get', 'head'):
            request.error (405)
            return

        if os.path.isdir (filename):
            filename = os.path.join (filename, 'index.html')

        if not os.path.isfile (filename):
            request.error (404)
        else:
            stat_info = os.stat (filename)
            mtime = stat_info[stat.ST_MTIME]
            file_length = stat_info[stat.ST_SIZE]

            ims = request.get_request_header ('if-modified-since')
            if ims:
                length_match = 1
                m = self.crack_if_modified_since.match (ims)
                if m:
                    length = m.group (3)
                    if length:
                        if int(length) != file_length:
                            length_match = 0

                ims_date = http_date.parse_http_date (m.group(1))

                if length_match and ims_date:
                    if mtime <= ims_date:
                        request.error (304, with_body=0)
                        return

            base, ext = os.path.splitext (filename)
            ext = ext[1:].lower()
            request['Content-Type'] = mime_type_table.content_type_map.get (ext, 'text/plain')
            request['Last-Modified'] = http_date.build_http_date (mtime)

            if request._method == 'get':
                f = open (filename, 'rb')

                block = f.read (32768)
                if not block:
                    request.error (204) # no content
                else:
                    while 1:
                        request.push (block)
                        block = f.read (32768)
                        if not block:
                            break
            elif request._method == 'head':
                pass
            else:
                # should be impossible
                request.error (405)

class http_server:

    def __init__ (self):
        self._handlers = []
        self.shutdown_flag = 0
        self.thread_id = None
        self.addr = ()
        self.config = {}
        self._qlog_code = 'http'

    def set_config (self, name, value):
        self.config[name] = value

    def get_config (self, name):
        return self.config.get(name, None)

    def is_secure(self):
        return hasattr(self, 'cert')

    def push_handler (self, handler):
        self._handlers.append (handler)

    def _make_socket(self):
        server_s = coro.make_socket (socket.AF_INET, socket.SOCK_STREAM)
        server_s.set_reuse_addr()
        return server_s

    def start (self, addr, retries=5):
        """Start the web server listening on addr in a new coroutine.

        Try up to retries time to bind to that address.
        Raises an exception if the bind fails."""

        server_s = self._make_socket()
        done = 0
        save_errno = 0
        self.addr = addr
        while not done:
            for x in xrange (retries):
                try:
                    was_eaddrinuse = 0
                    server_s.bind (addr)
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
                coro.sleep_relative(1) # ... and retry
            else:
                coro.print_stderr ("cannot bind to %s:%d after 5 attempts, errno = %d\n" % (addr[0], addr[1], save_errno))
                if was_eaddrinuse:
                    qlog.write('WEBUI.PORT_IN_USE',
                               addr[0], str(addr[1]))
                coro.sleep_relative(15)

        server_s.listen (1024)
        c = coro.spawn(self._run, server_s)
        c.set_name('http_server (%s:%d)' % addr)
        return 1 # in case the caller is expecting TRUE on success

    def _run (self, server_s):
        secure = self.is_secure()

        self.thread_id = coro.current().thread_id()
        while not self.shutdown_flag:
            try:
               conn, addr = server_s.accept()
               client = http_client()
               coro.spawn (client.run, conn, addr, self, self._handlers)
            except coro.Shutdown:
                # server-shutdown
                break
            except:
                qlog.write('COMMON.APP_FAILURE',
                           ('%s accept handler error %s' %
                             (self.__class__.__name__, coro.compact_traceback())))
                coro.sleep_relative(0.25)
                continue

        server_s.close()
        return None

    def shutdown(self):
        self.shutdown_flag = 1
        try:
            thread = coro.get_thread_by_id(self.thread_id)
            thread.shutdown()
        except KeyError:
            return # already exited

class https_server (http_server):
    def __init__ (self):
        http_server.__init__(self)
        self._qlog_code = 'https'

    def _make_socket (self):
        global ssl_ctx

        ssl_sock = coro_ssl.ssl_sock(ssl_ctx)
        ssl_sock.create()
        return ssl_sock

# Copied from medusa/http_server.py
def compute_timezone_for_log ():
    if time.daylight:
        tz = time.altzone
    else:
        tz = time.timezone
    if tz > 0:
        neg = 1
    else:
        neg = 0
        tz = -tz
    h, rem = divmod (tz, 3600)
    m, rem = divmod (rem, 60)
    if neg:
        return '-%02d%02d' % (h, m)
    else:
        return '+%02d%02d' % (h, m)

# if you run this program over a TZ change boundary, this will be invalid.
tz_for_log = compute_timezone_for_log()

if __name__ == '__main__':
    import backdoor, grp, os
    if len (sys.argv) > 1:
        doc_root = sys.argv[1]
    else:
        doc_root = '.'

    import coro_httpd
    init_ssl()
    update_cert_key(coro_ssl.CERT, coro_ssl.KEY)
    coro_httpd.init_ssl()
    coro_httpd.update_cert_key(coro_ssl.CERT, coro_ssl.KEY)

    # server = https_server()
    server = http_server()
    file_handler = http_file_handler (doc_root)
    server.push_handler (coro_status_handler())
    server.push_handler (file_handler)
    #coro.spawn (server._run, (('0.0.0.0', 9001)))
    coro.spawn(server.start, ('0.0.0.0', 9001))
    # server.start((('0.0.0.0', 9001)))
    coro.spawn (backdoor.serve)
    coro.event_loop (30.0)
