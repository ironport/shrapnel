# -*- Mode: Cython -*-

from cys2n.cys2n cimport *
from coro._coro cimport sock

# here we override the default behavior of cys2n (to raise WantRead/WantWrite upon EAGAIN),
#  hooking into shrapnel's event mechanism instead.

cdef class NonBlockingConnection (Connection):

    cdef sock coro_sock

    def __init__ (self, s2n_mode mode, sock s):
        Connection.__init__ (self, mode)
        self.coro_sock = s

    cdef want_read (self):
        self.coro_sock._wait_for_read()

    cdef want_write (self):
        self.coro_sock._wait_for_write()
