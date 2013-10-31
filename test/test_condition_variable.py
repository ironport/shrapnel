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

"""Unittests for condition variable.

XXX: This needs additional tests for:
- wake_one
- wake_n
- raise_all
"""

import coro
import coro_unittest
import unittest

class Test(unittest.TestCase):

    def test_cond_interrupt_schedule(self):
        """Test interrupt then schedule on condition variable."""
        c = coro.condition_variable()
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._cond_block, c))
        # Spawn a thread that we will not interrupt.
        no_interrupt_thread = coro.spawn(self._cond_block, c)
        coro.yield_slice()
        # Cause an interrupt on these threads.
        for t in threads:
            t.shutdown()
        # Now try to get the non-interrupted thread to run.
        c.wake_all()
        coro.yield_slice()
        # Verify that it ran.
        self.assertEqual(self._resume_count, 1)

    def _cond_block(self, c):
        c.wait()
        self._resume_count += 1

    def test_cond_schedule_interrupt(self):
        """Test schedule then interrupt on condition variable."""
        c = coro.condition_variable()
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._cond_block, c))
        # Spawn a thread that we will not interrupt.
        no_interrupt_thread = coro.spawn(self._cond_block, c)
        coro.yield_slice()
        # Schedule all of the threads (except the no interrupt thread).
        c.wake_all()
        # Now interrupt them.
        for t in threads:
            t.shutdown()
        coro.yield_slice()
        # Verify that it ran.
        self.assertEqual(self._resume_count, 1)

if __name__ == '__main__':
    coro_unittest.run_tests()
