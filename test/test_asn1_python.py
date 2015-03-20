# -*- Mode: Python -*-

import unittest
from coro.test import coro_unittest

from coro.asn1.python import *
from coro.asn1.ber import decode as D

class Test (unittest.TestCase):

    def round_trip (self, a, b):
        self.assertEquals (decode (encode (a)), b)

    def test_empty_list (self):
        self.assertEquals (encode([]), b'0\x00')

    def test_list (self):
        R = self.round_trip
        self.assertEquals (encode([0, 1, 2]), b'0\t\x02\x01\x00\x02\x01\x01\x02\x01\x02')
        R ([0, 1, 2], ([0, 1, 2], 11))
        R ([0, 1, 2], ([0, 1, 2], 11))
        self.assertEquals(
            encode([0, 1, [2, 3, 4]]),
            b'0\x11\x02\x01\x00\x02\x01\x010\t\x02\x01\x02\x02\x01\x03\x02\x01\x04')
        R ([0, 1, [2, 3, 4]], ([0, 1, [2, 3, 4]], 19))

    def test_longs (self):
        R = self.round_trip
        R (1 << 128, (1 << 128, 19))
        R (-1 << 128, (-1 << 128, 19))
        n = 92635422811926300371494754185131031660572678207193169844405659339331266122107L
        R (n, (n, 35))
        nn = -92635422811926300371494754185131031660572678207193169844405659339331266122107L
        R (nn, (nn, 35))

    def test_bool (self):
        R = self.round_trip
        R (True, (True, 3))
        R (False, (False, 3))

    def test_tuple (self):
        R = self.round_trip
        R ((0, 1, 2), ((0, 1, 2), 11))
        R ((), ((), 2))

    def test_dict (self):
        R = self.round_trip
        R ({1: 2, 3: "hi"}, ({1: 2, 3: 'hi'}, 19))

    def test_set (self):
        R = self.round_trip
        R (set([0, 1, 2]), (set([0, 1, 2]), 11))
        R (set([(0, 1), 2]), (set([(0, 1), 2]), 13))

    def test_float (self):
        R = self.round_trip
        R (3.1415926535, (3.1415926535, 10))
        R (0.0, (0.0, 10))
        R (-0.0, (-0.0, 10))
        import random
        for i in range (1000):
            x = random.randint (0, 1000000)
            R (x/1000.0, (x/1000.0, 10))
            R (-x/1000.0, (-x/1000.0, 10))

    def test_none (self):
        R = self.round_trip
        R (None, (None, 2))

    def test_bytes (self):
        R = self.round_trip
        R ('howdy there', ('howdy there', 13))

    def test_unicode (self):
        R = self.round_trip
        R (u'\u4e2d\u570b', (u'\u4e2d\u570b', 8))

    def test_complex_object (self):
        R = self.round_trip
        x = [12, "thirteen", (14, 15, {16: 17, 18: 19}, False), [[[[[[None]]]]]]]
        R (x, (x, 58))


if __name__ == '__main__':
    coro_unittest.run_tests()
