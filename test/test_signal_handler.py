# -*- Mode: Python -*-

import coro
import unittest
import os
import signal
from coro import signal_handler
from coro.test import coro_unittest

signal_caught_flag = False

W = coro.write_stderr

class Test (unittest.TestCase):

    def test_0_set_signal_handler (self):
        signal_handler.register (signal.SIGUSR1, self.usr1_handler)

    def usr1_handler (self, *args):
        global signal_caught_flag
        signal_caught_flag = True

    def test_1_trigger_signal (self):
        # XXX on osx, this sleep is necessary, otherwise this
        #     too-quick SIGUSR1 is lost.
        coro.sleep_relative (0.1)
        pid = os.getpid()
        os.kill (pid, signal.SIGUSR1)
        coro.sleep_relative (0.1)
        self.assertEqual (signal_caught_flag, True)

if __name__ == '__main__':
    coro_unittest.run_tests()
