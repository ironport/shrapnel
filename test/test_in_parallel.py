# $Header: //prod/main/ap/shrapnel/test/test_in_parallel.py#1 $
# Copyright (c) 2007 IronPort Systems, Inc.
# All rights reserved.
# Unauthorized redistribution prohibited.

"""Unittests for coro.in_parallel."""

__version__ = '$Revision: #1 $'

import coro
import coro_unittest
import unittest

class Test(unittest.TestCase):

    def test_timeout(self):
        """Test in_parallel with timeout (interrupted)."""
        def sleeper(num):
            coro.sleep_relative(5)
            return num

        self.assertRaises(coro.TimeoutError,
            coro.with_timeout,
                2,
                coro.in_parallel,
                    [(sleeper, (1,)),
                     (sleeper, (2,)),
                     (sleeper, (3,)),
                    ]
        )

        results = coro.with_timeout(7, coro.in_parallel,
                    [(sleeper, (4,)),
                     (sleeper, (5,)),
                     (sleeper, (6,)),
                    ]
        )
        self.assertEqual(results, [4,5,6])

if __name__ == '__main__':
    coro_unittest.run_tests()
