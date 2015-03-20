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

"""Unittests for coro profiler."""

import cStringIO
import os
import sys
import unittest

import coro
import coro.profiler
import coro.print_profile
from coro.test import coro_unittest

# Sam's favorite profile function.
def tak1 (x, y, z):
    coro.yield_slice()
    if y >= x:
        return z
    else:
        return tak1 (
            tak1 (x - 1, y, z),
            tak2 (y - 1, z, x),
            tak2 (z - 1, x, y)
        )

def tak2 (x, y, z):
    coro.yield_slice()
    if y >= x:
        return z
    else:
        return tak2 (
            tak2 (x - 1, y, z),
            tak1 (y - 1, z, x),
            tak1 (z - 1, x, y)
        )

def multi_test():
    t1 = coro.spawn(tak2, 18, 12, 6)
    t2 = coro.spawn(tak2, 18, 12, 6)
    t3 = coro.spawn(tak2, 18, 12, 6)
    t1.join()
    t2.join()
    t3.join()

class Test(unittest.TestCase):

    def test_profile(self):
        prof_filename = 'test_profile.bin'
        # Mainly this just checks that it doesn't raise any exceptions.
        try:
            coro.profiler.go(multi_test, profile_filename=prof_filename)
            output = cStringIO.StringIO()
            real_stdout = sys.stdout
            sys.stdout = output
            try:
                coro.print_profile.main(prof_filename)
            finally:
                sys.stdout = real_stdout
        finally:
            if os.path.exists(prof_filename):
                os.unlink(prof_filename)


if __name__ == '__main__':
    coro_unittest.run_tests()
