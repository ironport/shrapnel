# $Header: //prod/main/ap/shrapnel/test/test_rw_lock.py#1 $
# Copyright (c) 2007 IronPort Systems, Inc.
# All rights reserved.
# Unauthorized redistribution prohibited.

"""Unittests for read-write lock."""

__version__ = '$Revision: #1 $'

import coro
import coro_unittest
import unittest

class Test(unittest.TestCase):

    def test_write_block_interrupt_schedule(self):
        """Test write block interrupt then schedule on rw_lock."""
        lock = coro.rw_lock()
        lock.read_lock()
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._write_block, lock))
        # Spawn a thread that we will not interrupt.
        no_interrupt_thread = coro.spawn(self._write_block, lock)
        coro.yield_slice()
        # Cause an interrupt on these threads.
        for t in threads:
            t.shutdown()
        # Now try to get the non-interrupted thread to run.
        lock.read_unlock()
        coro.yield_slice()
        # Verify that it ran.
        self.assertEqual(self._resume_count, 1)

    def _write_block(self, lock):
        lock.write_lock()
        self._resume_count += 1
        lock.write_unlock()

    def _read_block(self, lock):
        lock.read_lock()
        self._resume_count += 1
        lock.read_unlock()

    def test_write_block_schedule_interrupt(self):
        """Test write block schedule then interrupt on rw_lock."""
        lock = coro.rw_lock()
        lock.read_lock()
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._write_block, lock))
        # Spawn a thread that we will not interrupt.
        no_interrupt_thread = coro.spawn(self._write_block, lock)
        coro.yield_slice()
        # Schedule all of the threads.
        lock.read_unlock()
        # Now interrupt them.
        for t in threads:
            t.shutdown()
        coro.yield_slice()
        # Verify that it ran.
        self.assertEqual(self._resume_count, 1)

    def test_read_block_interrupt_schedule(self):
        """Test read block interrupt then schedule on rw_lock."""
        lock = coro.rw_lock()
        lock.write_lock()
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._read_block, lock))
        # Spawn a thread that we will not interrupt.
        no_interrupt_thread = coro.spawn(self._read_block, lock)
        coro.yield_slice()
        # Cause an interrupt on these threads.
        for t in threads:
            t.shutdown()
        # Now try to get the non-interrupted thread to run.
        lock.write_unlock()
        coro.yield_slice()
        # Verify that it ran.
        self.assertEqual(self._resume_count, 1)

    def test_read_block_schedule_interrupt(self):
        """Test read block schedule then interrupt on rw_lock."""
        lock = coro.rw_lock()
        lock.write_lock()
        self._resume_count = 0
        threads = []
        # Spawn some threads that will block and be interrupted.
        for unused in xrange(5):
            threads.append(coro.spawn(self._read_block, lock))
        # Spawn a thread that we will not interrupt.
        no_interrupt_thread = coro.spawn(self._read_block, lock)
        coro.yield_slice()
        # Schedule all of the threads.
        lock.write_unlock()
        # Now interrupt them.
        for t in threads:
            t.shutdown()
        coro.yield_slice()
        # Verify that it ran.
        self.assertEqual(self._resume_count, 1)

if __name__ == '__main__':
    coro_unittest.run_tests()
