import coro
import unittest

def exit_coro():
    coro.sleep_relative(0.1)
    coro.set_exit()


class CoroMain(unittest.TestCase):
    def test_coro_main(self):
        coro.set_print_exit_string(None)

        for x in range(4):
            try:
                coro.spawn(exit_coro)
                coro.event_loop()
            except SystemExit:
                pass

if __name__ == '__main__':
    unittest.main()
