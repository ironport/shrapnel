# -*- Mode: Python -*-

import coro

from ._s2n import Config, Connection, S2N, MODE

Config = _s2n.Config

class sock (coro.sock):

    # XXX maybe delay creating connection object until either accept or connect in order to
    #   set mode automatically?
    def __init__ (self, cfg, fd=-1, verify=False, domain=coro.AF.INET, mode=MODE.SERVER):
        coro.sock.__init__ (self, fd=fd, domain=domain)
        self.cfg = cfg
        self.conn_ob = _s2n.Connection(mode)
        self.conn_ob.set_config (cfg)
        self.conn_ob.set_fd (fd)
        # XXX verify

    def __repr__ (self):
        return '<s2n sock fd=%d @%x>' % (self.fd, id (self))

    def accept (self):
        conn, addr = coro.sock.accept (self)
        try:
            new = self.__class__ (self.cfg, domain=conn.domain, fd=conn.fd, mode=MODE.SERVER)
            # ...avoid having socket.pyx close the fd
            conn.fd = -1
            while 1:
                more = new.conn_ob.negotiate()
                if not more:
                    break
            return new, addr
        except:
            conn.close()
            raise

    def connect (self, addr):
        coro.sock.connect (self, addr)
        while 1:
            more = new.conn_ob.negotiate()
            if not more:
                break

    def recv (self, block_size):
        r = []
        left = block_size
        while left:
            b, more = self.conn_ob.recv (left)
            r.append (b)
            if not more:
                break
            else:
                left -= len(b)
                self.wait_for_read()
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
        pos = 0
        left = len(data)
        while left:
            n, more = self.conn_ob.send (data, pos)
            pos += n
            if not more:
                break
            else:
                self.wait_for_write()
            left -= n
        return pos

    write = send

    # XXX verify this
    sendall = send

    # XXX writev

    def readv (self, _ignore):
        raise NotImplementedError

    def shutdown (self, how=None):
        more = 1
        while more:
            more = self.conn_ob.shutdown()

    def close (self):
        try:
            coro.with_timeout (1, self.shutdown)
        except coro.TimeoutError:
            pass
        finally:
            coro.sock.close (self)
