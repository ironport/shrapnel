# $Header: //prod/main/ap/shrapnel/test/test_condition_variable.py#1 $
# Copyright (c) 2007 IronPort Systems, Inc.
# All rights reserved.
# Unauthorized redistribution prohibited.

"""Unittests for condition variable.

XXX: This needs additional tests for:
- wake_one
- wake_n
- raise_all
"""

__version__ = '$Revision: #1 $'

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
