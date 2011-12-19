# $Header: //prod/main/ap/shrapnel/test/test_aio.py#3 $

"""Unittests for AIO.

"""

from coro import oserrors
import coro
import coro_unittest
import os
import unittest
import random
import resource

class Test(unittest.TestCase):

    def tearDown(self):
        if os.path.exists('test_aio_file'):
            os.unlink('test_aio_file')

    def _read_write(self, data):
        n = coro.aio_write(self.fd, data, 0)
        self.assertEqual(n, len(data))
        a = coro.aio_read(self.fd, len(data), 0)
        self.assertEqual(a, data)
        os.ftruncate(self.fd, 0)

    def test_read_write(self):
        """Test read/write."""
        self.fd = os.open('test_lio_file', os.O_RDWR|os.O_CREAT|os.O_TRUNC)

        # Simple 1-byte test.
        self._read_write('a')

        # Try something really large.
        data = os.urandom(5 * 1024 * 1024)
        self._read_write(data)

        # Test offset read/write.
        filesize = 512 * 1024
        orig_data = os.urandom(filesize)
        coro.aio_write(self.fd, orig_data, 0)
        for x in xrange(100):
            size = random.randint(1, filesize)
            offset = random.randint(0, filesize)
            data = coro.aio_read(self.fd, size, offset)
            self.assertEqual(data, orig_data[offset:offset+size])

        os.close(self.fd)

    def test_leak(self):
        """Test map leak."""
        # There was a bug where we were leaking events in the event map.
        self.fd = os.open('test_lio_file', os.O_RDWR|os.O_CREAT|os.O_TRUNC)

        event_size = len(coro.event_map)

        filesize = 512 * 1024
        orig_data = os.urandom(filesize)
        coro.aio_write(self.fd, orig_data, 0)
        for x in xrange(100):
            size = random.randint(1, filesize)
            offset = random.randint(0, filesize)
            data = coro.aio_read(self.fd, size, offset)
            self.assertEqual(data, orig_data[offset:offset+size])

        self.assertEqual(event_size, len(coro.event_map))

        # Try error path.
        os.close(self.fd)

        for x in xrange(100):
            size = random.randint(1, filesize)
            offset = random.randint(0, filesize)
            self.assertRaises(OSError, coro.aio_read, self.fd, size, offset)

        self.assertEqual(event_size, len(coro.event_map))

    def test_error(self):
        """Test error return."""
        fd = os.open('test_aio_file', os.O_RDWR|os.O_CREAT|os.O_TRUNC)
        data = os.urandom(1024 * 1024)
        r = coro.aio_write(fd, data, 0)
        self.assertEqual(r, len(data))
        self.assertEqual(coro.aio_read(fd, len(data), 0), data)

        # Rip away the file descriptor.
        os.close(fd)
        # Verify it fails.
        self.assertRaises(oserrors.EBADF, coro.aio_read, fd, len(data), 0)

        # Try a test that will fail from aio_return.
        # (NOTE: On FreeBSD before 7, this would actually show up as an
        # error immediately from aio_error, but in FreeBSD 7 it now appears to
        # go through the kqueue code path.)
        soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
        fd = os.open('test_aio_file', os.O_RDWR|os.O_CREAT|os.O_TRUNC)
        self.assertRaises(oserrors.EFBIG, coro.aio_write, fd, data, soft)
        os.close(fd)


if __name__ == '__main__':
    coro_unittest.run_tests()
