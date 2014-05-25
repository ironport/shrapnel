# Copyright (c) 2002-2011 IronPort Systems and Cisco Systems
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# $Header: //prod/main/ap/shrapnel/coro/emulation/socket.py#1 $

"""Emulation of Python's socket module in a coro app.

See Python's documentation for the socket module for details.
"""

from __future__ import absolute_import

import os
import socket as _socketmodule

import coro

##############################################################################
# Exceptions
##############################################################################
error = _socketmodule.error
herror = _socketmodule.herror
gaierror = _socketmodule.gaierror
timeout = _socketmodule.timeout

##############################################################################
# Constants
##############################################################################
g = globals()
for name in _socketmodule.__all__:
    value = getattr(_socketmodule, name)
    if isinstance(value, (int, long)):
        g[name] = value
del g, name, value

try:
    BDADDR_ANY = _socketmodule.BDADDR_ANY
    BDADDR_LOCAL = _socketmodule.BDADDR_LOCAL
except AttributeError:
    pass

##############################################################################
# Timeout.
##############################################################################
_defaulttimeout = None

def getdefaulttimeout():
    return _defaulttimeout

def setdefaulttimeout(timeout):
    global _defaulttimeout
    if timeout is not None and timeout < 0:
        raise ValueError('Invalid timeout')
    _defaulttimeout = timeout

##############################################################################
# Things not currently emulated.
##############################################################################

getfqdn = _socketmodule.getfqdn
gethostbyname = _socketmodule.gethostbyname
gethostbyname_ex = _socketmodule.gethostbyname_ex
gethostbyaddr = _socketmodule.gethostbyaddr
getaddrinfo = _socketmodule.getaddrinfo
getnameinfo = _socketmodule.getnameinfo

##############################################################################
# Things that don't need emulation.
##############################################################################
getservbyname = _socketmodule.getservbyname
getservbyport = _socketmodule.getservbyport
getprotobyname = _socketmodule.getprotobyname
gethostname = _socketmodule.gethostname
ntohs = _socketmodule.ntohs
ntohl = _socketmodule.ntohl
htons = _socketmodule.htons
htonl = _socketmodule.htonl
inet_aton = _socketmodule.inet_aton
inet_ntoa = _socketmodule.inet_ntoa
inet_pton = _socketmodule.inet_pton
inet_ntop = _socketmodule.inet_ntop

##############################################################################
# Socket object.
##############################################################################
class _ErrorConverter(object):

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, exc_tb):
        if exc_value is not None:
            if isinstance(exc_value, OSError):
                raise error(exc_value.errno, exc_value.strerror)
            # Otherwise, raise original exception.

_error_converter = _ErrorConverter()

class socket(object):

    def __init__(self, family=AF_INET, type=SOCK_STREAM, proto=0, _sock=None):
        if _sock is None:
            self._sock = coro.sock(family, type, proto)
        else:
            self._sock = _sock
        self.family = family
        self.type = type
        self.proto = proto
        self.timeout = _defaulttimeout

    def _with_timeout(self, func, *args, **kwargs):
        if self.timeout:
            try:
                return coro.with_timeout(self.timeout, func, *args, **kwargs)
            except coro.TimeoutError:
                raise timeout('Timed out')
        else:
            return func(*args, **kwargs)

    def accept(self):
        with _error_converter:
            sock, addr = self._with_timeout(self._sock.accept)
            return socket(sock.domain, sock.stype, 0, _sock=sock), addr

    def bind(self, address):
        with _error_converter:
            self._sock.bind(address)

    def close(self):
        with _error_converter:
            self._sock.close()

    def connect(self, address):
        with _error_converter:
            self._with_timeout(self._sock.connect, address)

    def connect_ex(self, address):
        try:
            self._with_timeout(self._sock.connect, address)
        except OSError, e:
            return e.errno
        else:
            return 0

    def dup(self):
        return socket(self.family, self.type, self.proto, self._sock)

    def fileno(self):
        return self._sock.fileno()

    def getpeername(self):
        with _error_converter:
            return self._sock.getpeername()

    def getsockname(self):
        with _error_converter:
            return self._sock.getsockname()

    def getsockopt(self, level, optname, buflen=0):
        with _error_converter:
            return self._sock.getsockopt(level, optname, buflen)

    def listen(self, backlog):
        with _error_converter:
            return self._sock.listen(backlog)

    def makefile(self, mode='r', bufsize=-1):
        # We use dup() here because we don't use the dummy socket concept
        # to handle file descriptor reference counting (which Python uses as
        # a cross-platform issue).
        return _socketmodule._fileobject(self.dup(), mode, bufsize, True)

    def recv(self, bufsize, flags=0):
        if flags != 0:
            raise AssertionError('Setting flags not yet supported.')
        with _error_converter:
            return self._with_timeout(self._sock.recv, bufsize)

    def recv_into(self, buffer, nbytes=0, flags=0):
        return self._sock.recv_into(buffer, nbytes, flags)

    def recvfrom(self, bufsize, flags=0):
        with _error_converter:
            return self._with_timeout(self._sock.recvfrom, bufsize, flags)

    def recvfrom_into(self, buffer, nbytes=0, flags=0):
        return self._sock.recvfrom_into(buffer, nbytes, flags)

    def send(self, data, flags=0):
        # XXX: Difference: this will call send again if not all data was sent.
        if flags != 0:
            raise AssertionError('Setting flags not yet supported.')
        with _error_converter:
            return self._with_timeout(self._sock.send, data)

    def sendall(self, data, flags=0):
        if flags != 0:
            raise AssertionError('Setting flags not yet supported.')
        with _error_converter:
            return self._with_timeout(self._sock.sendall, data)

    def sendto(self, data, flags_or_address, maybe_address=None):
        # Dumb API
        if maybe_address is None:
            address = flags_or_address
            flags = 0
        else:
            address = maybe_address
            flags = flags_or_address
        with _error_converter:
            return self._with_timeout(self._sock.sendto, data, address, flags)

    def setblocking(self, flag):
        if flag:
            # blocking
            pass
        else:
            # non-blocking
            # self.timeout = 0
            raise AssertionError('Non-blocking mode not yet supported.')

    def settimeout(self, value):
        # XXX: check value for 0 or None when we support non-blocking sockets.
        self.timeout = value

    def gettimeout(self):
        return self.timeout

    def setsockopt(self, level, optname, value):
        with _error_converter:
            self._sock.setsockopt(level, optname, value)

    def shutdown(self, how):
        with _error_converter:
            self._sock.shutdown(how)

SocketType = socket


##############################################################################
# Module-level functions.
##############################################################################

_GLOBAL_DEFAULT_TIMEOUT = object()

def create_connection(address, timeout=_GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    # This is copied directly from Python's implementation.
    msg = "getaddrinfo returns an empty list"
    host, port = address
    for res in getaddrinfo(host, port, 0, SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        sock = None
        try:
            sock = socket(af, socktype, proto)
            if timeout is not _GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sa)
            return sock

        except error, msg:
            if sock is not None:
                sock.close()

    raise error(msg)

def fromfd(fd, family, type, proto=0):
    with _error_converter:
        fd = os.dup(fd)
        sock = coro.sock(family, type, proto, fd=fd)
    return socket(family, type, proto, _sock=sock)

def socketpair(family=0, type=0, proto=0):
    with _error_converter:
        s1, s2 = coro.socketpair(family, type, proto)
    s1s = socket(family, type, proto, _sock=s1)
    s2s = socket(family, type, proto, _sock=s2)
    return (s1s, s2s)

# Some naughty code (urllib2 for example) use this directly.
_fileobject = _socketmodule._fileobject
