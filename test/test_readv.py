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

"""Unittests for readv socket call."""

import socket
import sys
import unittest

import coro
import coro_unittest

do_sleeps = False

class TestServer:

    block_sends = ()

    def serve(self, family, address):
        self.s = coro.make_socket(family, socket.SOCK_STREAM)
        self.s.bind((address, 0))
        self.port = self.s.getsockname()[1]
        self.s.set_reuse_addr()
        self.s.listen(5)
        while 1:
            try:
                s, addr = self.s.accept()
            except coro.Shutdown:
                break
            session = TestSession(s, addr, self.block_sends)
            coro.spawn(session.run)

big_block = '0123456789' * 1024 * 100

class TestSession:

    def __init__(self, s, addr, block_sends):
        self.s = s
        self.addr = addr
        self.block_sends = block_sends

    def run(self):
        for block_size in self.block_sends:
            if do_sleeps:
                coro.sleep_relative(0.1)
            self.s.send(big_block[:block_size])
        self.s.close()


class Test(unittest.TestCase):

    def test_readv(self):
        """Test readv."""
        global do_sleeps

        def testit(family, address, block_sends, block_receives, expected_results):
            s = coro.make_socket(family, socket.SOCK_STREAM)
            server.block_sends = block_sends
            coro.with_timeout(5, s.connect, (address, server.port))
            blocks = coro.with_timeout(5, s.readv, block_receives)
            self.assertEqual(len(blocks), len(expected_results))
            for block, expected_block in zip(blocks, expected_results):
                self.assertEqual(block, expected_block)

        to_test = [(socket.AF_INET, '127.0.0.1')]
        if coro.has_ipv6():
            to_test.append((socket.AF_INET6, '::1'))
        else:
            sys.stderr.write('Warning: No IPv6 support; skipping tests\n')
        for family, address in to_test:
            server = TestServer()
            server_thread = coro.spawn(server.serve, family, address)
            # Give the server a chance to start.
            coro.yield_slice()

            # Different levels of greediness.
            for greediness in (1024, 1):
                coro.current().set_max_selfish_acts(greediness)
                # Do it once without sleeps, once with sleeps.
                for sleep in (False, True):
                    do_sleeps = sleep
                    testit(family, address, (5, 19, 3, 8), (5, 19, 3, 8), ('01234', '0123456789012345678', '012', '01234567'))
                    testit(family, address, (5, 19, 3, 8), (24, 3, 8), ('012340123456789012345678', '012', '01234567'))
                    testit(family, address, (5, 19, 3, 8), (2, 3, 19, 3, 8), ('01', '234', '0123456789012345678', '012', '01234567'))
                    testit(family, address, (5, 5), (1, 1, 1, 1, 1, 1, 1, 1, 1, 1), ('0', '1', '2', '3', '4', '0', '1', '2', '3', '4'))
                    testit(family, address, (1, 1, 1, 1, 1, 1, 1, 1, 1, 1), (5, 5), ('00000', '00000'))
                    testit(family, address, (10,), (5,), ('01234',))
                    testit(family, address, (5,), (10,), ('01234',))
                    testit(family, address, (), (), ())
                    testit(family, address, (), (5, 2, 8), ())
                    testit(family, address, (5, 9), (5, 10), ('01234', '012345678'))
                    testit(family, address, (5, 9), (5, 5, 3, 7), ('01234', '01234', '567', '8'))
                    testit(family, address, (5, 5), (5, 5, 10), ('01234', '01234'))
                    testit(family, address, (5,), (6,), ('01234',))
                    testit(family, address, (512*1024,), (512*1024,), (big_block[:512*1024],))

            server_thread.raise_exception(coro.Shutdown)


if __name__ == '__main__':
    coro_unittest.run_tests()
