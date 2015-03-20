# -*- Mode: Python -*-

"""Unittest for with_timeout() call."""

import time
import unittest
import os

import coro
from coro.test import coro_unittest


class TestWithTimeout (unittest.TestCase):

    def test_with_timeout (self):
        def go():
            print "timer"
            with self.assertRaises(coro.TimeoutError):
                # coro.with_timeout(2, coro.sleep_relative, 4)
                coro.with_timeout(2, coro.waitpid, os.getpid())
            print "foo"

        coro.spawn(go)
        for i in range(5):
            coro.yield_slice()
            coro.sleep_relative(1)

if __name__ == '__main__':
    coro_unittest.run_tests()
