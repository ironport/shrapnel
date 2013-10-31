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

"""Unittests for interrupting coroutines."""

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
