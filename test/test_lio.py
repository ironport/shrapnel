# $Header: //prod/main/ap/shrapnel/test/test_lio.py#1 $

"""Unittests for LIO.

XXX TODO:
- Test pack_blocks_for_write.
"""

import coro
import coro_unittest
import operator
import os
import tempfile
import unittest

class Test(unittest.TestCase):

    def tearDown(self):
        if os.path.exists('test_lio_file'):
            os.unlink('test_lio_file')

    def _read_write(self, data):
        total_bytes = reduce(operator.add, map(len, data))
        n = coro.many_lio_writes(self.fd, 0, data)
        self.assertEqual(n, total_bytes)
        a = coro.many_lio_reads(self.fd, 0, total_bytes)
        self.assertEqual(a, data)
        os.ftruncate(self.fd, 0)

    def test_read_write(self):
        """Test read/write."""
        self.fd = os.open('test_lio_file', os.O_RDWR|os.O_CREAT|os.O_TRUNC)

        # Simple 1-byte test.
        self._read_write(['a'])

        # Test 3 blocks in 1 batch.
        data = [ os.urandom(coro.MAX_AIO_SIZE),
                 os.urandom(coro.MAX_AIO_SIZE),
                 os.urandom(int(coro.MAX_AIO_SIZE * 0.6)),
               ]
        self._read_write(data)

        # Test various numbers of full batches.
        for n in xrange(1, 5):
            data = [ os.urandom(coro.MAX_AIO_SIZE) for x in xrange(coro.MAX_LIO*n) ]
            self._read_write(data)

        # Test offset read/write.
        data = [ os.urandom(coro.MAX_AIO_SIZE) for x in xrange(3) ]
        total_bytes = reduce(operator.add, map(len, data))
        coro.many_lio_writes(self.fd, 0, data)
        a = coro.many_lio_reads(self.fd, 512, total_bytes-512)
        expected_data = ''.join(data)[512:]
        actual_data = ''.join(a)
        self.assertEqual(actual_data, expected_data)

        coro.many_lio_writes(self.fd, 1024, ['hi there'])
        a = coro.many_lio_reads(self.fd, 1024, 8)
        self.assertEqual(a, ['hi there'])


if __name__ == '__main__':
    coro_unittest.run_tests()
