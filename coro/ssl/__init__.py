# -*- Mode: Python -*-

import coro
from coro.ssl import openssl

ssl_op_map = {
    "sslv2": openssl.SSL_OP.NO_SSLv3 | openssl.SSL_OP.NO_TLSv1,
    "sslv3": openssl.SSL_OP.NO_SSLv2 | openssl.SSL_OP.NO_TLSv1,
    "tlsv1": openssl.SSL_OP.NO_SSLv2 | openssl.SSL_OP.NO_SSLv3,
    "sslv2sslv3": openssl.SSL_OP.NO_TLSv1,
    "sslv3tlsv1": openssl.SSL_OP.NO_SSLv2,
    "sslv2sslv3tlsv1": 0
}

from openssl import x509, pkey, dh_param

def new_ctx (cert=None, chain=(), key=None, proto=None, ciphers=None, dhparam=None, next_protos=None):
    ctx = openssl.ssl_ctx()
    if cert:
        ctx.use_cert (cert, chain)
    if key:
        ctx.use_key (key)
    if proto:
        ctx.set_options (ctx.get_options() | ssl_op_map[proto])
    if ciphers:
        ctx.set_ciphers (ciphers)
    if dhparam:
        ctx.set_tmp_dh (dhparam)
    if next_protos:
        ctx.set_next_protos (next_protos)
    return ctx

class sock (coro.sock):

    def __init__ (self, ctx, fd=-1, verify=False, domain=coro.AF.INET):
        coro.sock.__init__ (self, fd=fd, domain=domain)
        self.ctx = ctx
        # Note: this uses SSLv23_method(), which allows it to accept V2 client hello
        #  (which are common), but still limit to V3 or TLS1 via the 'proto' arg.
        self.ssl = self.ctx.ssl()
        self.ssl.set_fd (self.fd)
        if verify:
            self.ssl.set_verify (openssl.SSL_VERIFY.PEER)

    def __repr__ (self):
        return '<openssl sock fd=%d ssl@%x @%x>' % (self.fd, id (self.ssl), id (self))

    def _non_blocking_retry (self, fun, *args):
        while 1:
            try:
                return fun (*args)
            except openssl.WantRead:
                self.wait_for_read()
            except openssl.WantWrite:
                self.wait_for_write()

    def accept (self):
        conn, addr = coro.sock.accept (self)
        try:
            # hand the fd off to a new ssl sock object...
            new = self.__class__ (self.ctx, domain=conn.domain, fd=conn.fd)
            # ...avoid having socket.pyx close the fd
            conn.fd = -1
            # using set_accept_state() makes NPN very difficult
            # new.ssl.set_accept_state()
            new.ssl_accept()
            return new, addr
        except:
            conn.close()
            raise

    def set_accept_state (self):
        return self.ssl.set_accept_state()

    def set_connect_state (self):
        return self.ssl.set_connect_state()

    def ssl_accept (self):
        self._non_blocking_retry (self.ssl.accept)

    def connect (self, addr):
        coro.sock.connect (self, addr)
        # using set_connect_state makes NPN very difficult
        # self.ssl.set_connect_state()
        return self.ssl_connect()

    def ssl_connect (self):
        self._non_blocking_retry (self.ssl.connect)

    def recv (self, block_size):
        return self._non_blocking_retry (self.ssl.read, block_size)

    read = recv

    def recv_exact (self, size):
        left = size
        r = []
        while left:
            block = self.recv (left)
            if not block:
                break
            else:
                r.append (block)
                left -= len (block)
        return ''.join (r)

    def recvfrom (self, block_size, timeout=30):
        raise SystemError("recvfrom not supported for SSL sockets")

    def send (self, data):
        return self._non_blocking_retry (self.ssl.write, data)

    write = send

    # SSL_write() makes this guarantee.
    sendall = send

    def sendto (self, data, addr):
        raise SystemError("sendto not supported for SSL sockets")

    def writev (self, list_of_data):
        _sum = 0
        for data in list_of_data:
            _sum += self._non_blocking_retry (self.ssl.write, data)
        return _sum

    def readv (self, _ignore):
        raise NotImplementedError

    def shutdown (self, how=None):
        try:
            return self._non_blocking_retry (self.ssl.shutdown)
        except OSError:
            # common with an impolite disconnect
            pass

    def close (self):
        try:
            self.shutdown()
        finally:
            coro.sock.close (self)

    def getCipher (self):
        return self.ssl.get_cipher()

    # The following are taken from #defines in /usr/include/openssl/*.h
    _protocol_str_map = {
        0x0002: 'SSLv2',  # SSL2_VERSION
        0x0300: 'SSLv3',  # SSL3_VERSION
        0x0301: 'TLSv1',  # TLS1_VERSION
    }

    def getProtocol (self):
        prot_id = self.ssl.get_protocol()
        try:
            return self._protocol_str_map[prot_id]
        except KeyError:
            return '(UNKNOWN:%x)' % (prot_id,)
