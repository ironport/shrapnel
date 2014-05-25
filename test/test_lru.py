# -*- Mode: Python -*-

from coro.lru import lru
import unittest

class Test (unittest.TestCase):

    def test_0 (self):
        d = lru (4)

        for x in range (4):
            d[x] = repr(x)

        # they're in the LRU in the reverse order they were inserted;
        # i.e., '3' is the last one inserted, and is thus at the head.
        self.assertEqual (list(d), [(3, '3'), (2, '2'), (1, '1'), (0, '0')])
        # '1' is at the tail.  Let's refer to it and put it at the head.
        x = d[1]
        self.assertEqual (list(d), [(1, '1'), (3, '3'), (2, '2'), (0, '0')])
        # same thing, with '0'.
        y = d[0]
        self.assertEqual (list(d), [(0, '0'), (1, '1'), (3, '3'), (2, '2')])
        # if we insert a new node now, it should push out '2'.
        d[5] = '5'
        self.assertEqual (list(d), [(5, '5'), (0, '0'), (1, '1'), (3, '3')])

    def test_1 (self):
        # test delete-to-empty
        d = lru (4)
        d[0] = 1
        d[1] = 2
        d[2] = 3
        d[3] = 4
        # print 'del[2]'
        del d[2]
        # print 'del[1]'
        del d[1]
        # print 'del[3]'
        del d[3]
        # print 'del[0]'
        del d[0]
        self.assertEqual (len(d), 0)

    def test_2 (self):
        # test delete-to-empty
        d = lru (4)
        d[0] = 1
        del d[0]
        self.assertEqual (len(d), 0)
        return d

    def test_3 (self):
        # test size limitation
        d = lru (100)
        import random
        for i in range (10000):
            k = random.random()
            v = str(k)
            d[k] = v
        self.assertEqual (len(d), 100)

if __name__ == '__main__':
    unittest.main()
