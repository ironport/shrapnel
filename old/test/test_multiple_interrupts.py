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

# This script will trigger multiple interrupts to test the "latent interrupt"
# code of coro_sched.c.

import coro
import sys

exitval = -1
msg = "failure message was not set"

def simple_thread():
    global exitval, msg
    count = 0
    try:
        while count < 10:
            # print "count is %d" % (count,)
            coro.sleep_relative (1.0)
            count += 1
        msg = "thread was never interrupted"
        exitval = 1
    except coro.Interrupted as why:
        if why == []:
            msg = "multiple interrupts policy succeeded"
            exitval = 0
        elif why == [{}]:
            msg = "multiple interrupts policy reversed - it should use the first interrupt's value"
            exitval = 1
        else:
            msg = "interrupts out of order: interrupt value is %r" % (why,)
            exitval = 1
    except:
        msg = "multiple interrupts test failed: exception is %r" % tb.traceback_string()
        exitval = 1
    coro._exit = 1

def tripwire(sleep_val):
    thread = coro.spawn (simple_thread)
    # let simple_thread run for a while:
    coro.sleep_relative (sleep_val)
    # use these values to try to trigger refcount bugs:
    thread.interrupt([])
    thread.interrupt({})
    thread.interrupt({'': []})
    thread.interrupt([{}])

def main(verbose=0):
    global exitval, msg
    default_exitval = exitval
    default_msg = msg
    reports = []
    failures = 0

    # 3.0 is a multiple of 1.0, which timing allows a latent interrupt.
    for sleep_val in [2.5, 3.0]:
        coro.spawn (tripwire, sleep_val)
        coro.event_loop ()
        reports.append ((sleep_val, msg, exitval))
        if exitval != 0:
            failures += 1

        # reset values:
        coro._exit = 0
        exitval = default_exitval
        msg = default_msg

    if failures:
        if verbose:
            print "%d failures" % (failures,)
            for sleep_val, msg, exitval in reports:
                print "sleep val %s: %s" % (sleep_val, msg)

        sys.exit (1)
    else:
        if verbose:
            print "All tests passed."
        sys.exit (0)

if __name__ == '__main__':
    main(verbose=1)
