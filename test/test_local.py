# $Header: //prod/main/ap/shrapnel/test/test_local.py#1 $
# Copyright (c) 2009 IronPort Systems, Inc.
# All rights reserved.
# Unauthorized redistribution prohibited.

"""Unittests for thread-local storage."""

__version__ = '$Revision: #1 $'

import unittest

import coro
import coro_unittest

class Test(unittest.TestCase):

    shared = None
    t1_cv = None
    t2_cv = None

    def t1(self):
        self.assertFalse(hasattr(self.shared, 'x'))
        self.assertRaises(AttributeError, lambda: self.shared.x)
        # Wait for main thread.
        self.t1_cv.wait()
        self.assertFalse(hasattr(self.shared, 'x'))
        self.assertRaises(AttributeError, lambda: self.shared.x)
        self.shared.x = 2
        self.t1_cv.wait()
        self.assertEqual(self.shared.x, 2)


    def t2(self):
        self.assertFalse(hasattr(self.shared, 'x'))
        self.assertRaises(AttributeError, lambda: self.shared.x)
        # Wait for main thread.
        self.t2_cv.wait()
        self.assertFalse(hasattr(self.shared, 'x'))
        self.assertRaises(AttributeError, lambda: self.shared.x)
        self.shared.x = 3
        self.t2_cv.wait()
        self.assertEqual(self.shared.x, 3)

    def test_local(self):
        """Test thread-local storage."""
        self.t1_cv = coro.condition_variable()
        self.t2_cv = coro.condition_variable()
        self.shared = coro.ThreadLocal()
        self.shared.x = 1
        t1 = coro.spawn(self.t1)
        t2 = coro.spawn(self.t2)

        # Let them run.
        coro.yield_slice()
        self.t1_cv.wake_one()
        # Let t1 run.
        coro.yield_slice()
        self.assertEqual(self.shared.x, 1)

        self.t2_cv.wake_one()
        # Let t2 run.
        coro.yield_slice()
        self.assertEqual(self.shared.x, 1)

        self.t1_cv.wake_one()
        self.t2_cv.wake_one()
        coro.yield_slice()

        t1.join()
        t2.join()
        self.assertEqual(self.shared.x, 1)
        del self.shared

if __name__ == '__main__':
    coro_unittest.run_tests()
