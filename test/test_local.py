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

"""Unittests for thread-local storage."""

import unittest

import coro
import coro_unittest

class Test(unittest.TestCase):

    shared = None
    t1_cv = None
    t2_cv = None

    def t1(self):
        self.assertFalse(hasattr(self.shared, 'x'))
        self.assertRaises(AttributeError, lambda: self.shared.x)
        # Wait for main thread.
        self.t1_cv.wait()
        self.assertFalse(hasattr(self.shared, 'x'))
        self.assertRaises(AttributeError, lambda: self.shared.x)
        self.shared.x = 2
        self.t1_cv.wait()
        self.assertEqual(self.shared.x, 2)


    def t2(self):
        self.assertFalse(hasattr(self.shared, 'x'))
        self.assertRaises(AttributeError, lambda: self.shared.x)
        # Wait for main thread.
        self.t2_cv.wait()
        self.assertFalse(hasattr(self.shared, 'x'))
        self.assertRaises(AttributeError, lambda: self.shared.x)
        self.shared.x = 3
        self.t2_cv.wait()
        self.assertEqual(self.shared.x, 3)

    def test_local(self):
        """Test thread-local storage."""
        self.t1_cv = coro.condition_variable()
        self.t2_cv = coro.condition_variable()
        self.shared = coro.ThreadLocal()
        self.shared.x = 1
        t1 = coro.spawn(self.t1)
        t2 = coro.spawn(self.t2)

        # Let them run.
        coro.yield_slice()
        self.t1_cv.wake_one()
        # Let t1 run.
        coro.yield_slice()
        self.assertEqual(self.shared.x, 1)

        self.t2_cv.wake_one()
        # Let t2 run.
        coro.yield_slice()
        self.assertEqual(self.shared.x, 1)

        self.t1_cv.wake_one()
        self.t2_cv.wake_one()
        coro.yield_slice()

        t1.join()
        t2.join()
        self.assertEqual(self.shared.x, 1)
        del self.shared

if __name__ == '__main__':
    coro_unittest.run_tests()
