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

"""Unittests for event queue wrapper."""

import unittest

import coro
import coro_unittest

class Test(unittest.TestCase):

    def setUp(self):
        self.q = coro.event_queue()

    def test_insert(self):
        data = [(3, "3"), (2, "21"), (1, "1"), (2, "22")]
        res  = ["1", "21", "22", "3"]

        for i in data:
            self.q.insert(*i)
        self.assertEquals(len(data), len(self.q))
        for j in res:
            self.assertEquals(self.q.top(), j)
            self.assertEquals(self.q.pop(), j)

    def test_remove(self):
        data = [(3, "3"), (2, "21"), (1, "1"), (2, "22")]

        for i in data:
            self.q.insert(*i)
        self.assertRaises(IndexError, self.q.remove, 1, "2")
        self.assertRaises(IndexError, self.q.remove, 10, "2")
        for i in data:
            self.q.remove(*i)
        self.assertEquals(0, len(self.q))

    def test_empty(self):
        self.assertRaises(IndexError, self.q.top)
        self.assertRaises(IndexError, self.q.pop)
        self.assertRaises(IndexError, self.q.remove, 1, "2")

if __name__ == '__main__':
    coro_unittest.run_tests()
