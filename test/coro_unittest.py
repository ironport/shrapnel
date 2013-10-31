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

"""coro unittest helper.

This code will help you start up a unittest running in a coro environment.

In your unittest, add test case classes:

    class SomeTest(unittest.TestCase):

        def test_foo(self):
            \"\"\"Do the foo test.\"\"\"
            ...

At the bottom of the file, put this:

    if __name__ == '__main__':
        coro_unittest.run_tests()

This will automatically find any TestCase class in your file and run all
methods starting with "test_" in it.

This will also set up a test case that will assert that no threads crashed
while running.
"""

import coro
import signal
import sys
from coro import tb
import unittest

exc_str_list = []

def exception_notifier():
    exc_str = tb.traceback_string()
    coro.default_exception_notifier()
    exc_str_list.append(exc_str)

class ThreadFailedTest(unittest.TestCase):

    def test_threads_failed(self):
        """Checking for threads that crashed."""
        coro.sleep_relative(0)
        if len(exc_str_list) != 0:
            self.fail('Threads have crashed: %r' % (exc_str_list,))

exit_code = 0

def main():
    global exit_code
    try:
        try:
            #p = unittest.TestProgram(runNow=False)
            p = unittest.TestProgram()
            # This should always be the last test case run.
            p.test.addTest(ThreadFailedTest('test_threads_failed'))
            p.runTests()
        except SystemExit, e:
            exit_code = e.code
    finally:
        coro.set_exit(exit_code)

main_thread = None

def sigterm_handler(unused):
    main_thread.raise_exception(KeyboardInterrupt)

def run_tests():
    global main_thread
    coro.install_signal_handlers = 0
    coro.signal_handler.register (signal.SIGTERM, sigterm_handler)
    coro.signal_handler.register (signal.SIGINT, sigterm_handler)
    coro.set_exception_notifier(exception_notifier)
    main_thread = coro.spawn(main)
    coro.set_print_exit_string(False)
    coro.event_loop()
    sys.exit(exit_code)
