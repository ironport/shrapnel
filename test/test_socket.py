# $Header: //prod/main/ap/shrapnel/test/test_socket.py#2 $
# Copyright (c) 2006 IronPort Systems, Inc.
# All rights reserved.
# Unauthorized redistribution prohibited.

"""Basic unittests for sockets including IPv6."""

__version__ = '$Revision: #2 $'

import socket
import sys
import unittest

import coro
import coro_unittest

class TestServer:

    accepted_from = None

    def serve(self, address):
        self.s = coro.make_socket_for_ip(address, socket.SOCK_STREAM)
        self.s.bind((address, 0))
        self.bound_ip, self.port = self.s.getsockname()
        self.s.set_reuse_addr()
        self.s.listen(5)

        s, addr = self.s.accept()
        session = TestSession(s, addr)
        coro.spawn(session.run)
        self.accepted_from = s.getsockname()[0]

class TestSession:

    def __init__(self, s, addr):
        self.s = s
        self.addr = addr

    def run(self):
        current_buffer = ''
        while 1:
            block = self.s.recv(1024)
            if not block:
                break
            current_buffer = current_buffer + block

        self.s.send(current_buffer)
        self.s.close()

class Test(unittest.TestCase):
    """Test aims to make sure that the changes to parse_address and
    unparse_address in socket.pyx didn't break anything. The tests are
    far from exhaustive but they are a nice smoke test."""

    test_string = 'Hello world'

    def do_work(self, connected_sock):
        connected_sock.send(self.test_string)
        connected_sock.shutdown(socket.SHUT_WR)
        reply = connected_sock.recv(len(self.test_string) + 1)
        self.assertEqual(reply, self.test_string)

    def _test(self, address):
        server = TestServer()
        server_thread = coro.spawn(server.serve, address)
        # Give the server a chance to start.
        coro.yield_slice()
        self.assertEqual(server.bound_ip, address)

        sock = coro.make_socket_for_ip(address, socket.SOCK_STREAM)
        sock.connect((address, server.port))

        coro.yield_slice()

        # Double checking that everyone thinks they're connected
        # to the same peer
        self.assertEqual(server.accepted_from, address)
        self.assertEqual(sock.getpeername()[0], server.accepted_from)

        self.do_work(sock)

    def test_v4(self):
        self._test('127.0.0.1')

    def test_v6(self):
        if coro.has_ipv6():
            self._test('::1')
        else:
            sys.stderr.write('Warning: No IPv6 support; skipping tests\n')

    def test_make_socket_for_ip(self):
        if coro.has_ipv6():
            sock = coro.make_socket_for_ip('2001::1', socket.SOCK_STREAM)
            self.assertEquals(sock.domain, socket.AF_INET6)
            sock = coro.make_socket_for_ip('::', socket.SOCK_STREAM)
            self.assertEquals(sock.domain, socket.AF_INET6)
        else:
            sys.stderr.write('Warning: No IPv6 support; skipping tests\n')

        sock = coro.make_socket_for_ip('1.2.3.4', socket.SOCK_STREAM)
        self.assertEquals(sock.domain, socket.AF_INET)
        sock = coro.make_socket_for_ip('0.0.0.0', socket.SOCK_STREAM)
        self.assertEquals(sock.domain, socket.AF_INET)

        self.assertRaises(ValueError, coro.make_socket_for_ip, '123', 0)

    def test_invalid_ip(self):
        sock = coro.make_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.assertRaises(ValueError, sock.connect, (('123', 80),))
        self.assertRaises(ValueError, sock.connect, ((123, 80),))

    def test_bind_empty_ip_v4(self):
        sock = coro.make_socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("",5010))
        self.assertEquals(sock.domain, socket.AF_INET)

    def test_bind_empty_ip_v6(self):
        sock = coro.make_socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.bind(("",5010))
        self.assertEquals(sock.domain, socket.AF_INET6)

    def test_bind_wrong_af_4to6(self):
        sock = coro.make_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.assertEquals(sock.domain, socket.AF_INET)
        self.assertRaises(ValueError, sock.bind, (("2001::1",5010),))

    def test_bind_wrong_af_6to4(self):
        sock = coro.make_socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.assertEquals(sock.domain, socket.AF_INET6)
        self.assertRaises(ValueError, sock.bind, (("1.1.1.1",5010),))

    def test_bind_af_unspec(self):
        sock = coro.make_socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.domain = socket.AF_UNSPEC
        self.assertRaises(ValueError, sock.bind, (("1.1.1.1",5010),))
        self.assertRaises(ValueError, sock.bind, (("",5010),))

    def test_getsockname_v4(self):
        sock = coro.make_socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("",5555))
        sn = sock.getsockname()
        self.assertEquals(sn[0], "0.0.0.0")
        self.assertEquals(sn[1], 5555)

    def test_getsockname_v6(self):
        sock = coro.make_socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.bind(("",5555))
        sn = sock.getsockname()
        self.assertEquals(sn[0], "::")
        self.assertEquals(sn[1], 5555)

if __name__ == '__main__':
    coro_unittest.run_tests()

