# $Header: //prod/main/ap/shrapnel/test/test_mutex.py#1 $
# Copyright (c) 2007 IronPort Systems, Inc.
# All rights reserved.
# Unauthorized redistribution prohibited.

"""Unittests for mutex."""

__version__ = '$Revision: #1 $'

import coro
import coro_unittest
import unittest

class Test(unittest.TestCase):

    def test_mutex_interrupt_schedule(self):
        """Test interrupt then schedule on mutex."""
        m = coro.mutex()
        m.lock()
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._mutex_block, m))
        # Spawn a thread that we will not interrupt.
        no_interrupt_thread = coro.spawn(self._mutex_block, m)
        coro.yield_slice()
        # Cause an interrupt on these threads.
        for t in threads:
            t.shutdown()
        # Now try to get the non-interrupted thread to run.
        m.unlock()
        coro.yield_slice()
        # Verify that it ran.
        self.assertEqual(self._resume_count, 1)

    def _mutex_block(self, m):
        m.lock()
        self._resume_count += 1
        m.unlock()

    def test_mutex_schedule_interrupt(self):
        """Test schedule then interrupt on mutex."""
        m = coro.mutex()
        m.lock()
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._mutex_block, m))
        # Spawn a thread that we will not interrupt.
        no_interrupt_thread = coro.spawn(self._mutex_block, m)
        coro.yield_slice()
        # Schedule all of the threads.
        m.unlock()
        # Now interrupt them.
        for t in threads:
            t.shutdown()
        coro.yield_slice()
        # Verify that it ran.
        self.assertEqual(self._resume_count, 1)

    def test_ownership(self):
        """Test mutex ownership."""
        m = coro.mutex()
        m.lock()
        t = coro.spawn(self._test_ownership, m)
        coro.yield_slice()
        self.assertTrue(m.has_lock())
        self.assertFalse(m.has_lock(t))
        self.assertTrue(m.unlock())
        coro.yield_slice()
        self.assertFalse(m.has_lock())
        self.assertTrue(m.has_lock(t))
        coro.yield_slice()

    def _test_ownership(self, m):
        # This trylock "fails".
        self.assertTrue(m.trylock())
        # This one blocks.
        self.assertTrue(m.lock())
        # Bounce back to other thread.
        coro.yield_slice()

    def test_multiple_lock(self):
        """Test locking mutex multiple times."""
        m = coro.mutex()
        self.assertFalse(m.locked())
        self.assertFalse(m.has_lock())
        self.assertFalse(m.lock())
        self.assertTrue(m.locked())
        self.assertTrue(m.has_lock())
        self.assertFalse(m.lock())
        self.assertTrue(m.locked())
        self.assertTrue(m.has_lock())
        self.assertFalse(m.unlock())
        self.assertTrue(m.locked())
        self.assertTrue(m.has_lock())
        self.assertFalse(m.unlock())
        self.assertFalse(m.locked())
        self.assertFalse(m.has_lock())

    def test_unlock_resume(self):
        """Test that unlock resume."""
        m = coro.mutex()
        coro.spawn(self._test_unlock_resume, m)
        coro.yield_slice()
        # This will block, bounce over to other thread.
        self.assertTrue(m.lock())
        self.assertTrue(m.has_lock())
        self.assertFalse(m.unlock())
        self.assertFalse(m.has_lock())

    def _test_unlock_resume(self, m):
        self.assertFalse(m.lock())
        # Bounce back to other thread.
        coro.yield_slice()
        self.assertTrue(m.unlock())

if __name__ == '__main__':
    coro_unittest.run_tests()
