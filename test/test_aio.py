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

"""Unittests for AIO.

"""

from coro import oserrors
import coro
from coro.test import coro_unittest
import os
import unittest
import random
import resource

UNAME = os.uname()[0]

class Test(unittest.TestCase):

    FLAG = os.O_RDWR | os.O_CREAT | os.O_TRUNC
    if UNAME == 'Linux':
        FLAG |= os.O_DIRECT

    def tearDown(self):
        if os.path.exists('test_aio_file'):
            os.unlink('test_aio_file')

    def _read_write(self, data):
        n = coro.aio_write(self.fd, data, 0)
        self.assertEqual(n, len(data))
        a = coro.aio_read(self.fd, len(data), 0)
        self.assertEqual(a, data)
        os.ftruncate(self.fd, 0)

    @unittest.skipUnless(hasattr(coro, 'aio_write'), "No aio_write in coro")
    def test_read_write(self):
        """Test read/write."""
        self.fd = os.open('test_aio_file', Test.FLAG)

        # Simple 1-byte test.
        self._read_write('a')

        # Try something really large.
        data = os.urandom(5 * 1024 * 1024)
        self._read_write(data)

        # Test offset read/write.
        orig_data = os.urandom(512 * 1024)
        filesize = len(orig_data)
        coro.aio_write(self.fd, orig_data, 0)
        for x in xrange(100):
            size = random.randint(1, filesize)
            offset = random.randint(0, filesize - size)
            data = coro.aio_read(self.fd, size, offset)
            self.assertEqual(data, orig_data[offset:offset + size])

        os.close(self.fd)

    @unittest.skipUnless(hasattr(coro, 'aio_write'), "No aio_write in coro")
    def test_leak(self):
        """Test map leak."""
        # There was a bug where we were leaking events in the event map.
        self.fd = os.open('test_aio_file', Test.FLAG)

        event_size = len(coro.event_map)

        filesize = 512 * 1024
        orig_data = os.urandom(filesize)
        coro.aio_write(self.fd, orig_data, 0)
        for x in xrange(100):
            size = random.randint(1, filesize)
            offset = random.randint(0, filesize - size)
            data = coro.aio_read(self.fd, size, offset)
            self.assertEqual(data, orig_data[offset:offset + size])

        self.assertEqual(event_size, len(coro.event_map))

        # Try error path.
        os.close(self.fd)

        for x in xrange(100):
            size = random.randint(1, filesize)
            offset = random.randint(0, filesize - size)
            self.assertRaises(OSError, coro.aio_read, self.fd, size, offset)

        self.assertEqual(event_size, len(coro.event_map))

    @unittest.skipUnless(hasattr(coro, 'aio_write'), "No aio_write in coro")
    def test_error(self):
        """Test error return."""
        fd = os.open('test_aio_file', Test.FLAG)
        data = os.urandom(1024 * 1024)
        r = coro.aio_write(fd, data, 0)
        self.assertEqual(r, len(data))
        self.assertEqual(coro.aio_read(fd, len(data), 0), data)

        # Rip away the file descriptor.
        os.close(fd)
        # Verify it fails.
        self.assertRaises(OSError, coro.aio_read, fd, len(data), 0)

        # Try a test that will fail from aio_return.
        # (NOTE: On FreeBSD before 7, this would actually show up as an
        # error immediately from aio_error, but in FreeBSD 7 it now appears to
        # go through the kqueue code path.)
        soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
        if soft >= 0:
            fd = os.open('test_aio_file', Test.FLAG)
            self.assertRaises(oserrors.EFBIG, coro.aio_write, fd, data, soft)
            os.close(fd)


if __name__ == '__main__':
    coro_unittest.run_tests()
