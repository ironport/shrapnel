# $Header: //prod/main/ap/shrapnel/test/test_interrupt.py#3 $
# Copyright (c) 2006 IronPort Systems, Inc.
# All rights reserved.
# Unauthorized redistribution prohibited.

"""Unittests for interrupting coroutines."""

__version__ = '$Revision: #3 $'

import coro
import coro_unittest
import unittest

class TestException(Exception):
    pass

class Test(unittest.TestCase):

    def test_scheduled_staging_interrupt(self):
        """Test interrupting a thread that is scheduled and in the staging list."""
        t = coro.get_now() + coro.ticks_per_sec*3
        exception_raised = [False]
        def foo():
            self.assertFalse(exception_raised[0])
            try:
                coro.sleep_absolute(t)
            except TestException:
                exception_raised[0] = True

        c = coro.spawn(foo)
        coro.sleep_absolute(t)
        c.raise_exception(TestException)
        coro.yield_slice()
        self.assertTrue(exception_raised[0])

    def test_scheduled_pending_interrupt(self):
        """Test interrupting a thread that is scheduled and in the pending list."""
        exception_raised = [False]
        def foo():
            self.assertFalse(exception_raised[0])
            try:
                coro._yield()
            except TestException:
                exception_raised[0] = True

        c = coro.spawn(foo)
        coro.yield_slice()
        c.schedule()
        c.raise_exception(TestException)
        coro.yield_slice()
        self.assertTrue(exception_raised[0])

    def test_interrupt_sleeping_coro(self):
        """Test interrupting a thread in a sleep call."""
        exception_raised = [False]
        def foo():
            self.assertFalse(exception_raised[0])
            try:
                coro.sleep_relative(3)
            except TestException:
                exception_raised[0] = True

        c = coro.spawn(foo)
        coro.yield_slice()
        c.raise_exception(TestException)
        coro.yield_slice()
        self.assertTrue(exception_raised[0])

    def test_not_started_interrupt(self):
        """Test interrupting a thread that has not started."""
        def foo():
            pass

        c = coro.spawn(foo)
        self.assertRaises(coro.NotStartedError, c.raise_exception, TestException)
        self.assertTrue(c.scheduled)
        self.assertFalse(c.dead)
        self.assertFalse(c.started)
        c.raise_exception(TestException, cancel_start=True)
        self.assertFalse(c.scheduled)
        self.assertTrue(c.dead)
        self.assertFalse(c.started)
        # Try again and see what happens.
        self.assertRaises(coro.DeadCoroutine, c.raise_exception, TestException, cancel_start=True)
        self.assertFalse(c.scheduled)
        self.assertTrue(c.dead)
        self.assertFalse(c.started)
        # Shutdown shouldn't ever raise an exception.
        c.shutdown()
        self.assertFalse(c.scheduled)
        self.assertTrue(c.dead)
        self.assertFalse(c.started)

    def test_interrupt_sleeping(self):
        """Test interrupting a sleeping thread at the exact same time the sleep
        expires.
        """
        self.assertRaises(coro.TimeoutError,
            coro.with_timeout, 0, coro.sleep_relative, 0)


if __name__ == '__main__':
    coro_unittest.run_tests()
