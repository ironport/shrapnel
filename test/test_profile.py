# $Header: //prod/main/ap/shrapnel/test/test_profile.py#1 $

"""Unittests for coro profiler."""

import cStringIO
import os
import sys
import unittest

import coro
import coro.profiler
import coro.print_profile
import coro_unittest

# Sam's favorite profile function.
def tak1 (x,y,z):
    coro.yield_slice()
    if y >= x:
        return z
    else:
        return tak1 (
            tak1 (x-1, y, z),
            tak2 (y-1, z, x),
            tak2 (z-1, x, y)
            )

def tak2 (x,y,z):
    coro.yield_slice()
    if y >= x:
        return z
    else:
        return tak2 (
            tak2 (x-1, y, z),
            tak1 (y-1, z, x),
            tak1 (z-1, x, y)
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
