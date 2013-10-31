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

"""Unittests for semaphore."""

import coro
import coro_unittest
import unittest

class Test(unittest.TestCase):

    def test_sem_interrupt_schedule(self):
        """Test interrupt then schedule on semaphore."""
        s = coro.semaphore(1)
        s.acquire(1)
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._sem_block, s))
        # Spawn a thread that we will not interrupt.
        no_interrupt_thread = coro.spawn(self._sem_block, s)
        coro.yield_slice()
        # Cause an interrupt on these threads.
        for t in threads:
            t.shutdown()
        # Now try to get the non-interrupted thread to run.
        s.release(1)
        coro.yield_slice()
        # Verify that it ran.
        self.assertEqual(self._resume_count, 1)

    def _sem_block(self, s, count=1):
        s.acquire(count)
        self._resume_count += 1
        s.release(count)

    def test_sem_schedule_interrupt(self):
        """Test schedule then interrupt on semaphore."""
        s = coro.semaphore(5)
        s.acquire(5)
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._sem_block, s))
        # Spawn a thread that we will not interrupt.
        no_interrupt_thread = coro.spawn(self._sem_block, s)
        coro.yield_slice()
        # Schedule all of the threads (except the no interrupt thread).
        s.release(5)
        # Now interrupt them.
        for t in threads:
            t.shutdown()
        coro.yield_slice()
        # Verify that it ran.
        self.assertEqual(self._resume_count, 1)

    def test_sem_buildup(self):
        """Test semaphore waiting buildup."""
        # There was a bad bug once where the _waiting list got really big,
        # and a lot of interrupts was causing a lot of thrashing of the
        # _waiting list.
        s = coro.semaphore(1)
        s.acquire(1)
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._sem_block, s))
        coro.yield_slice()
        self.assertEqual(len(s._waiting), 5)
        # Now interrupt them.
        for t in threads:
            t.shutdown()
        self.assertEqual(len(s._waiting), 5)
        # Now try to release.
        s.release(1)
        self.assertEqual(len(s._waiting), 0)
        coro.yield_slice()
        self.assertEqual(self._resume_count, 0)

    def test_exception_stomp(self):
        # Pyrex had a bug where if it raised an exception it would stomp on
        # the "current" exception on the Python stack.
        s = coro.semaphore(0)
        def blocker():
            s.acquire(1)
        t1 = coro.spawn(blocker)
        coro.yield_slice()
        # Mark the thread as scheduled.
        t1.shutdown()
        def raiser():
            try:
                raise ValueError(3)
            except ValueError:
                # This will attempt to schedule t1 which will result in a
                # ScheduleError getting raised and caught within the release
                # code.
                s.release(1)
                # This should re-raise ValueError.  But with the bug, it was
                # re-raising ScheduleError.
                raise
        self.assertRaises(ValueError, raiser)

    def test_exception_stomp2(self):
        # Pyrex had a bug where calling a function within an exception handler,
        # and that function raised and caught an exception, it would stomp on
        # the current exception, so re-raising would raise the wrong exception.
        s = coro.semaphore(0)
        def blocker():
            s.acquire(1)
        t1 = coro.spawn(blocker)
        t2 = coro.spawn(blocker)
        coro.yield_slice()
        # Make t1 scheduled.
        s.release(1)
        # Interrupt t1, it will try to schedule t2, but that will fail.
        t1.shutdown()
        # Cause t2 to be scheduled.
        t2.shutdown()
        coro.yield_slice()

if __name__ == '__main__':
    coro_unittest.run_tests()
