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

# test_coro
#
# This file tries to excersize all the functionality of the coroutine system.
# It will try to make sure things function properly, and don't leak.

# To Test:
# - sleep_absolute/relative
# - with_timeout
# - wait_for_kevent
# - register_other_kevent
# - aio_read/write
# - selfish operations
# - yield/resume
# - socket functions
# - interrupt
#
# Tests:
# - functional
# - memory leaks

from comma_group import comma_group
import coro
import GetArg
import mstats
import sys
import types

##############################################################################

def test_make_coro():
    test_func = lambda(x,y): (x,y)
    for x in xrange(1000):
        a = coro.new(test_func, 0, 1)
        # Unspawned threads aren't able to clean up their all_threads reference
        del coro.all_threads[a.thread_id()]
        del a
    coros = map(lambda x,test_func=test_func: coro.new(test_func, x, 1), range(1000))
    for x in coros:
        # Unspawned threads aren't able to clean up their all_threads reference
        del coro.all_threads[x.thread_id()]
    del coros

##############################################################################

def test_sleep():
    coro.print_stderr('    This pause should be 1 second.\n')
    coro.sleep_relative(1)
    coro.print_stderr('    This pause should be 1 second.\n')
    coro.sleep_relative(1.0)
    coro.print_stderr('    This pause should be 1 second.\n')
    coro.sleep_relative(1L*coro.ticks_per_sec)
    coro.print_stderr('    This pause should be 1 second.\n')
    coro.sleep_absolute(coro.now+1L*coro.ticks_per_sec)

##############################################################################

def test_sleep_interrupt():
    coro.spawn(_test_sleep_interrupt, coro.current())
    # The other thread will interrupt me
    coro.print_stderr('There should be no pause here:\n')
    try:
        coro.sleep_relative(10)
    except coro.Interrupted, why:
        if why!='foobar':
            raise ValueError, 'Incorrect interrupt value.'

def _test_sleep_interrupt(c):
    c.interrupt('foobar')

##############################################################################

def test_multiple_sleep_interrupt():
    # The first interrupt will work just fine
    coro.spawn(_test_multiple_sleep_interrupt_ok, coro.current())
    # Since it has already been interrupted, you can't interrupt it ever again.
    # The following threads will fail.  This is to be expected.
    # Someday we need to redesign how interrupts work so that these won't fail.
    # But that will be very tricky.
    coro.spawn(_test_multiple_sleep_interrupt_fail, coro.current())
    coro.spawn(_test_multiple_sleep_interrupt_fail, coro.current())
    coro.spawn(_test_multiple_sleep_interrupt_fail, coro.current())
    # The other thread will interrupt me
    coro.print_stderr('    There should be no pause here:\n')
    try:
        coro.sleep_relative(10)
    except coro.Interrupted, why:
        if why!='foobar':
            raise ValueError, 'Incorrect interrupt value.'

def _test_multiple_sleep_interrupt_ok(c):
    c.interrupt('foobar')

def _test_multiple_sleep_interrupt_fail(c):
    try:
        c.interrupt('foobar')
    except SystemError, why:
        coro.print_stderr('    Expected exception: %s\n' % (why,))
    else:
        raise ValueError, 'SystemError didn\'t happen as expected!'

##############################################################################

def test_with_timeout():
    try:
        coro.print_stderr('    Should be a 1 second pause:\n')
        coro.with_timeout(1, coro.sleep_relative, 5)
    except coro.TimeoutError:
        pass
    else:
        raise ValueError, 'Timeout didn\'t happen as expected!'

def test_with_timeout_with_interrupt():
    coro.spawn(_test_with_timeout_with_interrupt, coro.current())
    try:
        coro.print_stderr('    Should be no pause:\n')
        coro.with_timeout(1, coro.sleep_relative, 5)
    except coro.Interrupted, why:
        if why!='foobar':
            raise ValueError, 'Interrupt value is not foobar!'
    else:
        raise ValueError, 'Interrupt didn\'t happen as expected!'

def _test_with_timeout_with_interrupt(c):
    c.interrupt('foobar')

##############################################################################

def test_resume():
    # Resume myself.  This should work without problems.
    coro.spawn(_test_resume, coro.current())
    result = coro.yield()
    if result != 'yoyo':
        raise ValueError, 'Resume with wrong value!'

def _test_resume(c):
    c.resume('yoyo')

##############################################################################

def test_interrupt():
    # Resume myself.  This should work without problems.
    coro.spawn(_test_interrupt_resume, coro.current())
    # Interrupt, this should be latent
    coro.spawn(_test_interrupt_latent, coro.current())
    # Interrupt, this should fail
    coro.spawn(_test_interrupt_fail, coro.current())
    result = coro.yield()
    coro.print_stderr('resuming with result %r\n' % (result,))
    if result != 'yoyo':
        raise ValueError, 'Resume with wrong value!'
    # Go back to sleep to catch the latent interrupt
    try:
        result = coro.yield()
    except coro.Interrupted, why:
        if why != 'foo':
            raise ValueError, 'Wrong why %s' % why

def _test_interrupt_resume(c):
    coro.print_stderr('resume running\n')
    coro.coro_sched.the_scheduler.schedule(c, 'yoyo')

def _test_interrupt_latent(c):
    coro.print_stderr('interrupter running\n')
    result = c.interrupt('foo')
    if result != 1:
        raise ValueError, 'Not latent? %i' % result

def _test_interrupt_fail(c):
    try:
        c.interrupt('bar')
    except SystemError:
        pass
    else:
        raise ValueError, 'Second latent interrupt didn\'t fail?'


##############################################################################

def test_raise():
    # Resume myself.  This should work without problems.
    coro.spawn(_test_raise, coro.current())
    try:
        result = coro.yield()
    except ZeroDivisionError, why:
        if why[0] != 12345:
            raise ValueError, 'Why is wrong %s' % (why,)
        pass
    else:
        raise ValueError, 'Failed to raise!'

def _test_raise(c):
    c.resume_with_exc(ZeroDivisionError, 12345)

##############################################################################
##############################################################################
##############################################################################

def do_tests(tests):
    for x in xrange(5):
        for func_name in tests:
            f = globals()[func_name]
            if type(f) is types.FunctionType:
                if f.func_name.startswith('test_'):
                    coro.print_stderr('Running test %s...\n' % f.func_name)
                    start_ram = mstats.get_malloc_stats()['allocated_bytes']
                    apply(f, ())
                    end_ram = mstats.get_malloc_stats()['allocated_bytes']
                    coro.print_stderr('RAM difference: %s\n' % comma_group(end_ram - start_ram))
    coro._exit = 1

if __name__=='__main__':
    args = GetArg.GetArg()
    args.process(sys.argv[1:])
    if args.arguments:
        tests = args.arguments
    else:
        tests = globals().keys()
    coro.spawn(do_tests, tests)
    coro.event_loop()
