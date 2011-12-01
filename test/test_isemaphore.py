# $Header: //prod/main/ap/shrapnel/test/test_isemaphore.py#1 $
# Copyright (c) 2007 IronPort Systems, Inc.
# All rights reserved.
# Unauthorized redistribution prohibited.

"""Unittests for inverted semaphore."""

__version__ = '$Revision: #1 $'

import coro
import coro_unittest
import unittest

class Test(unittest.TestCase):

    def test_isem_interrupt_schedule(self):
        """Test interrupt then schedule on inverted semaphore."""
        s = coro.inverted_semaphore()
        s.acquire(1)
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._isem_block, s))
        # Spawn a thread that we will not interrupt.
        no_interrupt_thread = coro.spawn(self._isem_block, s)
        coro.yield_slice()
        # Cause an interrupt on these threads.
        for t in threads:
            t.shutdown()
        # Now try to get the non-interrupted thread to run.
        s.release(1)
        coro.yield_slice()
        # Verify that it ran.
        self.assertEqual(self._resume_count, 1)

    def _isem_block(self, s):
        s.block_till_zero()
        self._resume_count += 1

    def test_isem_schedule_interrupt(self):
        """Test schedule then interrupt on inverted semaphore."""
        s = coro.inverted_semaphore()
        s.acquire(1)
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._isem_block, s))
        # Spawn a thread that we will not interrupt.
        no_interrupt_thread = coro.spawn(self._isem_block, s)
        coro.yield_slice()
        # Schedule all of the threads.
        s.release(1)
        # Now interrupt them.
        for t in threads:
            t.shutdown()
        coro.yield_slice()
        # Verify that it ran.
        self.assertEqual(self._resume_count, 1)


if __name__ == '__main__':
    coro_unittest.run_tests()
