# $Header: //prod/main/ap/shrapnel/test/test_notify_of_close.py#2 $

"""Unittests for the notify_of_close functionality."""

import coro
import coro_unittest
import os
import unittest
from aplib import oserrors

class ForceSend(coro.Interrupted):
    pass

class Test(unittest.TestCase):

    _dummy_thread = None
    _blocker_socket = None
    _echo_thread = None
    _echo_socket = None
    port = 0

    def setUp(self):
        self._start_listener()

    def tearDown(self):
        if self._dummy_thread:
            self._dummy_thread.shutdown()
            self._dummy_thread.join()

    def _echo(self, sock):
        while 1:
            try:
                try:
                    data = sock.recv(1024)
                except oserrors.ECONNRESET:
                    return
            except ForceSend:
                sock.send('hi there\n')
            else:
                if not data:
                    return
                sock.send(data)

    def _dummy_listener(self, s):
        while 1:
            sock, addr = s.accept()
            self._echo_socket = sock
            self._echo_thread = coro.spawn(self._echo, sock)

    def _start_listener(self):
        s = coro.tcp_sock()
        s.bind(('127.0.0.1', 0))
        s.listen(5)
        addr = s.getsockname()
        self.port = addr[1]
        self._dummy_thread = coro.spawn(self._dummy_listener, s)
        coro.yield_slice()

    def _blocker_thread(self):
        self._blocker_socket = coro.tcp_sock()
        self._blocker_socket.connect(('127.0.0.1', self.port))
        while 1:
            coro.print_stderr('reading')
            try:
                self._blocker_socket.read(1024)
            except coro.ClosedError:
                coro.print_stderr('it was closed')
                return

    def test_submitted_shutdown_close(self):
        t = coro.spawn(self._blocker_thread)
        coro.sleep_relative(1)
        t.shutdown()
        self._blocker_socket.close()
        t.join()

    def test_submitted_close_shutdown(self):
        t = coro.spawn(self._blocker_thread)
        coro.sleep_relative(1)
        self._blocker_socket.close()
        t.shutdown()
        t.join()

    def _shutdown_close(self, t):
        t.shutdown()
        self._blocker_socket.close()

    def test_new_shutdown_close(self):
        t = coro.spawn(self._blocker_thread)
        t2 = coro.spawn(self._shutdown_close, t)
        t.join()
        t2.join()

    def _close_shutdown(self, t):
        self._blocker_socket.close()
        t.shutdown()

    def test_new_close_shutdown(self):
        t = coro.spawn(self._blocker_thread)
        t2 = coro.spawn(self._close_shutdown, t)
        t.join()
        t2.join()

    def _fired_blocker(self):
        self.assertRaises(coro.ClosedError, self._fired_blocker_socket.read, 1024)
        return

    def _fired_closer(self, event):
        self._fired_blocker_socket.close()

    _fired_blocker_socket = None

    def test_fired(self):
        s = coro.tcp_sock()
        s.connect(('127.0.0.1', self.port))
        self._fired_blocker_socket = s
        # We need to somehow schedule two threads to both wake up on kevent at
        # the same time in a particular order.  The first one will call close
        # on the socket of the second one.
        f = open('test_fire', 'w')
        coro.set_handler((f.fileno(), coro.EVFILT.VNODE),
                         self._fired_closer,
                         fflags=coro.NOTE.DELETE
                        )

        t2 = coro.spawn(self._fired_blocker)
        #t2.set_max_selfish_acts(1)
        # Yield to allow fired blocker to block.
        coro.yield_slice()
        # Now, cause threads blocked on kevents to get scheduled in a specific
        # order.
        os.unlink('test_fire')
        s.send('force send')
        # Let those threads run.
        coro.yield_slice()

if __name__ == '__main__':
    coro_unittest.run_tests()
