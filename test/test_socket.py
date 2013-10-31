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

"""Basic unittests for sockets including IPv6."""

import socket
import sys
import unittest

import coro
import coro_unittest

class TestServer:

    accepted_from = None

    def serve(self, address, family):
        self.s = coro.make_socket(family, socket.SOCK_STREAM)
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

    def _test(self, address, family):
        server = TestServer()
        server_thread = coro.spawn(server.serve, address, family)
        # Give the server a chance to start.
        coro.yield_slice()
        self.assertEqual(server.bound_ip, address)

        sock = coro.make_socket(family, socket.SOCK_STREAM)
        sock.connect((address, server.port))

        coro.yield_slice()

        # Double checking that everyone thinks they're connected
        # to the same peer
        self.assertEqual(server.accepted_from, address)
        self.assertEqual(sock.getpeername()[0], server.accepted_from)

        self.do_work(sock)

    def test_v4(self):
        self._test('127.0.0.1', socket.AF_INET)

    def test_v6(self):
        if coro.has_ipv6():
            self._test('::1', socket.AF_INET6)
        else:
            sys.stderr.write('Warning: No IPv6 support; skipping tests\n')

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
