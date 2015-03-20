# -*- Mode: Python -*-

"""Unittest for socket.accept_many() call."""

import socket
import sys
import unittest

import coro
from coro.test import coro_unittest

do_sleeps = False

class TestServer:

    def serve (self, family, address):
        self.s = coro.make_socket (family, socket.SOCK_STREAM)
        self.s.bind ((address, 0))
        self.port = self.s.getsockname()[1]
        self.s.set_reuse_addr()
        self.s.listen (5)
        while True:
            try:
                coro.write_stderr ('accepting...\n')
                conns = self.s.accept_many (5)
                coro.write_stderr ('...after: conns=%r\n' % (conns,))
            except coro.Shutdown:
                break
            for s, addr in conns:
                session = TestSession (s, addr)
                coro.spawn (session.run)

class TestSession:

    def __init__ (self, s, addr):
        self.s = s
        self.addr = addr

    def run (self):
        self.s.send ('howdy!\r\n')
        self.s.close()

class Test (unittest.TestCase):

    def test_accept_many (self):
        global count
        server = TestServer()
        coro.spawn (server.serve, coro.AF.INET, '127.0.0.1')
        coro.yield_slice()

        def connect():
            s = coro.make_socket (coro.AF.INET, socket.SOCK_STREAM)
            coro.with_timeout (5, s.connect, ('127.0.0.1', server.port))
            howdy = coro.with_timeout (5, s.recv, 100)
            self.assertEqual (howdy, 'howdy!\r\n')
            count -= 1
            if count == 0:
                server_thread.raise_exception(coro.Shutdown)

        coro.spawn (connect)
        coro.spawn (connect)
        coro.spawn (connect)
        count = 3


if __name__ == '__main__':
    coro_unittest.run_tests()
