# -*- Mode: Python -*-
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

# Coroutine wrapper for SSL sockets.

import coro
import datafile
import socket
import sslip

init_defaults = 1
try:
    CERT = datafile.get_file('coro_ssl_data', 'demo-cert.txt')
    KEY = datafile.get_file('coro_ssl_data', 'demo-key.txt')
    KEY_PASS = datafile.get_file('coro_ssl_data', 'demo-pass.txt').strip()
    DH_PARAM_512 = datafile.get_file('coro_ssl_data', 'dh_512.pem')
    DH_PARAM_1024 = datafile.get_file('coro_ssl_data', 'dh_1024.pem')
except IOError:
    # ignore IOErrors here ... they SHOULD only occur when building a
    # frozen upgrade binary
    init_defaults = 0
    pass


if init_defaults:
    default_cert = sslip.read_pem_cert (CERT)
    default_key = sslip.read_pem_key (KEY, KEY_PASS)

    default_ctx = sslip.ssl_ctx (sslip.SSLV23_METHOD)
    default_ctx.use_cert (default_cert)
    default_ctx.use_key  (default_key)
    # diffie-hellman parameters
    default_ctx.set_tmp_dh (DH_PARAM_512)
    default_ctx.set_options (default_ctx.get_options() | sslip.SSL_OP_SINGLE_DH_USE)
    # put these two RC4 ciphers up front, they use much less CPU than 3DES
    # default_ctx.set_ciphers ('RC4-SHA:RC4-MD5:ALL')
else:
    default_cert = None
    default_key = None
    default_ctx = None

# Helper code
ssl_default_op = sslip.SSL_OP_SINGLE_DH_USE
ssl_op_map = {
    "sslv2": ssl_default_op | sslip.SSL_OP_NO_SSLv3 | sslip.SSL_OP_NO_TLSv1,
    "sslv3": ssl_default_op | sslip.SSL_OP_NO_SSLv2 | sslip.SSL_OP_NO_TLSv1,
    "tlsv1": ssl_default_op | sslip.SSL_OP_NO_SSLv2 | sslip.SSL_OP_NO_SSLv3,
    "sslv2sslv3": ssl_default_op | sslip.SSL_OP_NO_TLSv1,
    "sslv3tlsv1": ssl_default_op | sslip.SSL_OP_NO_SSLv2,
    "sslv2sslv3tlsv1": ssl_default_op,
}

def new_ssl_ctx(protocol, method, ciphers):
    new_ctx = ssl_ctx(protocol)
    new_ctx.set_options (ssl_op_map[method])
    new_ctx.set_ciphers(ciphers)
    new_ctx.set_tmp_dh (DH_PARAM_1024)
    return new_ctx

# this is a candidate for using an SSL_CTX
def check_key (cert, key, passwd='', chain=()):
    """check_key() -> cert key
    Returns 1 if key can sign certificate.
    """
    try:
        ctx = sslip.ssl_ctx (sslip.TLSV1_CLIENT_METHOD)

        cert_obj = sslip.read_pem_cert(cert)

        # Convert chain certs to cert objects
        cert_chain = []
        for c in chain:
            cert_chain.append(sslip.read_pem_cert(c))

        ctx.use_cert(cert_obj, tuple(cert_chain))

        key_obj = sslip.read_pem_key(key, passwd)
        ctx.use_key(key_obj)

        if ctx.check_key():
            return 1
        else:
            return 0
    except:
        return 0

ssl_ctx = sslip.ssl_ctx

class ssl_sock (object):

    cert = default_cert
    priv = default_key
    ctx  = default_ctx

    def __init__ (self, ctx=default_ctx):
        self.debug = 0
        self.thread_id = 0
        self.ctx = ctx

    def create (self, sock=None, verify=None):
        self.ssl = self.ctx.ssl()

        if sock is None:
            self.sock = coro.make_socket (socket.AF_INET, socket.SOCK_STREAM)
        else:
            self.sock = sock

        if verify:
            self.ssl.set_verify (sslip.SSL_VERIFY_PEER)

        self.ssl.set_fd (self.sock.fileno())

    def _non_blocking_retry (self, fun, *args):
        while True:
            try:
                return fun (*args)
            except sslip.WantRead:
                self.sock.wait_for_read()
            except sslip.WantWrite:
                self.sock.wait_for_write()
        # mollify pychecker, ugh.
        return None

    def set_reuse_addr (self):
        self.sock.set_reuse_addr()

    def bind (self, addr):
        self.sock.set_reuse_addr()
        return self.sock.bind (addr)

    def listen (self, backlog):
        self.ssl.set_accept_state()
        return self.sock.listen (backlog)

    def accept (self, verify=None):
        """ ssl_sock -> ssl_sock, addr

        Protocol, unspecified, is inherited from the accepting socket's
        protocol field.  Otherwise, the supplied protocol is used for
        the new connection.
        """
        conn, addr = self.sock.accept()

        try:
            new = self.__class__(self.ctx)
            new.create (sock=conn, verify=verify)
            new.ssl.set_accept_state()
            return new, addr
        except:
            # close connection
            conn.close()
            raise

    def set_accept_state (self):
        return self.ssl.set_accept_state()

    def set_connect_state (self):
        return self.ssl.set_connect_state()

    def ssl_accept (self):
        self._non_blocking_retry (self.ssl.accept)

    def connect (self, addr):
        self.sock.connect (addr)
        self.ssl.set_connect_state()

    def ssl_connect (self):
        self._non_blocking_retry (self.ssl.connect)

    def recv (self, block_size):
        return self._non_blocking_retry (self.ssl.read, block_size)

    def recvfrom (self, block_size, timeout=30):
        raise SystemError("recvfrom not supported for SSL sockets")

    def send (self, data):
        return self._non_blocking_retry (self.ssl.write, data)

    # SSL_write() makes this guarantee.
    sendall = send

    def sendto (self, data, addr):
        raise SystemError("sendto not supported for SSL sockets")

    def writev (self, list_of_data):
        _sum = 0
        for data in list_of_data:
            _sum += self._non_blocking_retry (self.ssl.write, data)
        return _sum

    def shutdown (self):
        # TODO: this should be changed to have a 'how' argument to
        # match non-SSL sockets.
        return self._non_blocking_retry (self.ssl.shutdown)

    def close (self):
        try:
            try:
                self.shutdown()
            except coro.TimeoutError:
                pass
        finally:
            self.sock.close()

    def getCipher (self):
        return self.ssl.get_cipher()

    # The following are taken from #defines in /usr/include/openssl/*.h
    _protocol_str_map = {0x0002: 'SSLv2',  # SSL2_VERSION
                         0x0300: 'SSLv3',  # SSL3_VERSION
                         0x0301: 'TLSv1',  # TLS1_VERSION
                         }

    def getProtocol (self):
        prot_id = self.ssl.get_protocol()
        try:
            return self._protocol_str_map[prot_id]
        except KeyError:
            return '(UNKNOWN:%x)' % (prot_id,)

    # forward these other methods to the ssl socket
    def getpeername (self, *args):
        return self.sock.getpeername (*args)

    def getsockname (self, *args):
        return self.sock.getsockname (*args)

    def getsockopt (self, *args):
        return self.sock.getsockopt (*args)

    def setsockopt (self, *args):
        return self.sock.setsockopt (*args)

    def setblocking (self, flag):
        if flag:
            raise SystemError("cannot set coro socket to blocking-mode")
        else:
            # coro sockets are always in non-blocking mode.
            pass

    def settimeout (self, value):
        raise SystemError("use coro.with_timeout() rather than sock.settimeout()")

    def gettimeout (self):
        return None

    def makefile(self, mode='r', bufsize=-1):
        return socket._fileobject(self, mode, bufsize)
