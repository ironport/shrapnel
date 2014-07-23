import coro
import unittest

class CoroMain(unittest.TestCase):
    def test_coro_main_connect(self):
        s = coro.tcp_sock()
        with self.assertRaises(coro.YieldFromMain):
            s.connect (('127.0.0.1', 80))

    def test_coro_main_yield(self):
        s = coro.tcp_sock()
        with self.assertRaises(coro.YieldFromMain):
            coro.yield_slice()

if __name__ == '__main__':
    unittest.main()
