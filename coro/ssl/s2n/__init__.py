# -*- Mode: Python -*-

import coro
from cys2n import MODE, PROTOCOL, Config, Error as S2NError
from ._s2n import *

from coro.log import Facility

LOG = Facility ('s2n')

# Note: the plan is to push this class into _s2n.pyx as well.

class S2NSocket (coro.sock):

    def __init__ (self, cfg, fd=-1, verify=False, mode=MODE.SERVER):
        coro.sock.__init__ (self, fd=fd)
        self.cfg = cfg
        self.s2n_conn = NonBlockingConnection (mode, self)
        self.s2n_conn.set_config (cfg)
        self.s2n_conn.set_fd (fd)
        self.negotiated = False
        # XXX verify

    def __repr__ (self):
        return '<s2n sock fd=%d @%x>' % (self.fd, id (self))

    def _check_negotiated (self):
        if not self.negotiated:
            self.negotiate()

    def negotiate (self):
        self.s2n_conn.negotiate()
        self.negotiated = True

    def accept (self):
        conn, addr = coro.sock.accept (self)
        try:
            new = self.__class__ (self.cfg, fd=conn.fd, mode=MODE.SERVER)
            # ...avoid having socket.pyx close the fd
            conn.fd = -1
            return new, addr
        except:
            conn.close()
            raise

    def connect (self, addr):
        coro.sock.connect (self, addr)
        self.negotiate()

    def recv (self, block_size):
        self._check_negotiated()
        r = []
        left = block_size
        while left:
            b, more = self.s2n_conn.recv (left)
            r.append (b)
            if not more:
                break
            else:
                left -= len(b)
        return ''.join (r)

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

    def send (self, data):
        self._check_negotiated()
        pos = 0
        left = len(data)
        while left:
            n, more = self.s2n_conn.send (data, pos)
            #LOG ('send', data, pos, n, more)
            pos += n
            if not more:
                break
            left -= n
        return pos

    write = send

    # XXX verify this
    sendall = send

    def writev (self, list_of_data):
        _sum = 0
        for data in list_of_data:
            _sum += self.send (data)
        return _sum

    def readv (self, _ignore):
        raise NotImplementedError

    def shutdown (self, how=None):
        try:
            self.s2n_conn.shutdown()
        except S2NError:
            pass

    def close (self):
        if self.fd != -1:
            # another thread closed us already.
            return
        else:
            try:
                coro.with_timeout (1, self.shutdown)
            except coro.TimeoutError:
                pass
            finally:
                LOG ('coro.sock.close', self.orig_fd)
                coro.sock.close (self)
