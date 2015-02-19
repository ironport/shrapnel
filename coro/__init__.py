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

# $Header: //prod/main/ap/shrapnel/coro/__init__.py#31 $

"""Coroutine threading library."""

from coro._coro import *
from coro._coro import _yield
from coro import signal_handler
from coro import optional
from coro import tb

import signal
import sys
import time
import os

UNAME = os.uname()[0]

# install default dns resolver
import coro.dns.cache
coro.dns.cache.install()

# ============================================================================
#                        tracebacks/exceptions
# ============================================================================

compact_traceback = tb.traceback_string
traceback_data = tb.traceback_data

# This overrides the one in <_coro>
def default_exception_notifier():
    me = current()
    print_stderr (
        'thread %d (%s): error %r\n' % (
            me.id,
            me.name,
            compact_traceback(),
        )
    )

set_exception_notifier (default_exception_notifier)

# ============================================================================
#                          parallel execution
# ============================================================================

class InParallelError (Exception):

    """An error occurred in the :func:`in_parallel` function.

    :ivar result_list: A list of ``(status, result)`` tuples. ``status`` is
          either :data:`SUCCESS` or :data:`FAILURE`.  For success, the result is the return
          value of the function.  For failure, it is the output from
          ``sys.exc_info``.
    """

    def __init__(self, result_list):
        self.result_list = result_list
        Exception.__init__(self, result_list)

SUCCESS = 'success'
FAILURE = 'failure'

def _in_parallel_wrap (result_list, i, sem, (fun, args)):
    try:
        result = (SUCCESS, fun (*args))
    except:
        result = (FAILURE, sys.exc_info())
    result_list[i] = result
    sem.release(1)

def in_parallel (fun_arg_list):
    """Execute several functions in parallel.

    This will block until all functions have returned or raised an exception.

    If one or more functions raises an exception, then the :exc:`InParallelError`
    exception will be raised.

    :param fun_arg_list: A list of ``(fun, args)`` tuples.

    :returns: A list of return values from the functions.

    :raises InParallelError: One or more of the functions raised an exception.
    """
#         InParallelError, [(SUCCESS, result0), (FAILURE, exc_info1), ...]

    n = len(fun_arg_list)
    if n == 0:
        return []
    result_list = [None] * n
    sem = inverted_semaphore(n)
    for i in xrange (n):
        spawn (
            _in_parallel_wrap,
            result_list,
            i,
            sem,
            fun_arg_list[i]
        )
    sem.block_till_zero()
    for i in xrange (n):
        if result_list[i][0] is FAILURE:
            raise InParallelError(result_list)
    # no errors, convert to a simple result list
    return [x[1] for x in result_list]

# ============================================================================
#                                 time
# ============================================================================

# Every hour
tick_update_interval = 3600

def tick_updater():
    """Updates TSC<->POSIX relation.

    This is a thread that runs forever.  It is responsible for updating the now
    and now_usec variables every hour.  This will take care of any clock drift
    because our ticks_per_sec variable might be slightly off.

    This runs once an hour.
    """
    global tick_update_interval
    while 1:
        sleep_relative(tick_update_interval)
        tsc_time.update_time_relation()

# ============================================================================
#                               waitpid
# ============================================================================

def waitpid (pid):
    """Wait for a process to exit.

    :param pid: The process ID to wait for.

    :returns: A tuple ``(pid, status)`` of the process.

    :raises SimultaneousError: Something is already waiting for this process
          ID.
    """
    if UNAME == "Linux":
        # XXX Replace this sleep crap with netlink and epoll
        status = 0
        while status == 0:
            returned_pid, status = os.waitpid (pid, os.WNOHANG)
            sleep_relative(4)

        return returned_pid, status
    else:
        me = current()
        wait_for(pid, EVFILT.PROC, fflags=NOTE.EXIT)
        # this should always succeed immediately.
        # XXX too bad kqueue NOTE_EXIT doesn't have the status.
        return os.waitpid (pid, 0)


# ============================================================================
#                                 misc
# ============================================================================

def get_thread_by_id (thread_id):
    """Get a coro thread by ID.

    :param thread_id: The thread ID.

    :returns: The coroutine object.

    :raises KeyError: The coroutine does not exist.
    """
    return all_threads[thread_id]

def where (co):
    """Return a string indicating where the given coroutine thread is currently
    running.

    :param co: The coroutine object.

    :returns: A string displaying where the coro thread is currently
        executing.
    """
    f = co.get_frame()
    return tb.stack_string(f)

def where_all():
    """Get a dictionary of where all coroutines are currently executing.

    :returns: A dictionary mapping the coroutine ID to a tuple of ``(name,
        coro, where)`` where ``where`` is a string representing where the
        coroutine is currently running.
    """
    output = {}
    for id, c in all_threads.items():
        output[id] = (c.get_name(), c, where(c))
    return output

# ============================================================================
#                          spawn/new wrappers
# ============================================================================

_original_spawn = spawn

def spawn (fun, *args, **kwargs):
    """Spawn a new coroutine.

    Additional arguments and keyword arguments will be passed to the given function.

    :param fun: The function to call when the coroutine starts.
    :param thread_name: The name of the thread.  Defaults to the name of the
          function.

    :returns: The new coroutine object.
    """
    if 'thread_name' in kwargs:
        thread_name = kwargs['thread_name']
        del kwargs['thread_name']
    else:
        thread_name = '%s' % (fun,)
    return _original_spawn (fun, *args, **kwargs).set_name (thread_name)

_original_new = new
def new (fun, *args, **kwargs):
    """Create a new coroutine object.

    Additional arguments and keyword arguments will be passed to the given
    function.

    This will not start the coroutine.  Call the ``start`` method on the
    coroutine to schedule it to run.

    :param fun: The function to call when the coroutine starts.
    :param thread_name: The name of the thread.  Defaults to the name of the
          function.

    :returns: The new coroutine object.
    """
    if 'thread_name' in kwargs:
        thread_name = kwargs['thread_name']
        del kwargs['thread_name']
    else:
        thread_name = '%s' % (fun,)
    return _original_new (fun, *args, **kwargs).set_name (thread_name)

# ============================================================================
#                      time backwards compatibility
# ============================================================================
import coro.clocks.tsc_time as tsc_time

ticks_per_sec = tsc_time.ticks_per_sec
ticks_per_usec = tsc_time.ticks_per_usec
microseconds      = 1000000

absolute_time_to_ticks = tsc_time.usec_to_ticks
ticks_to_absolute_time = tsc_time.ticks_to_usec
absolute_time_to_ticks_safe = tsc_time.usec_to_ticks_safe
ticks_to_absolute_time_safe = tsc_time.ticks_to_usec_safe
absolute_secs_to_ticks = tsc_time.sec_to_ticks
ticks_to_absolute_secs = tsc_time.ticks_to_sec
get_now = tsc_time.rdtsc
update_time_relation = tsc_time.update_time_relation

def get_usec():
    """This is for backwards compatibility and should not be used."""
    return tsc_time.ticks_to_usec(get_now())

def ctime_ticks(t):
    """This is for backwards compatibility and should not be used."""
    return tsc_time.TSC_from_ticks(t).ctime()

def ctime_usec(u):
    """This is for backwards compatibility and should not be used."""
    return tsc_time.TSC_from_posix_usec(u).ctime()

now = get_now()
now_usec = get_usec()


# ============================================================================
#                           non-coro compatibility
# ============================================================================

# XXX 2013 SMR: there's a problem with this hack - if you use this form of import:
#    "from coro import sleep_relative" you'll get the non-coro one.  This is why
#    we don't like monkey-patching!
_original_with_timeout = with_timeout
with_timeout = optional.with_timeout
_original_sleep_relative = sleep_relative
sleep_relative = optional.sleep_relative

# ============================================================================
#                            Python compatibility
# ============================================================================

def install_thread_emulation():
    """Install Python threading emulation.

    It is recommended that you call this at the very beginning of the main
    script of your application before importing anything else.  This will
    cause the following modules to be emulated:

    - thread
    - threading
    - socket

    At this time, no other blocking operations are supported.
    """
    import coro.emulation.socket
    import coro.emulation.thread
    import coro.emulation.threading
    sys.modules['thread'] = coro.emulation.thread
    sys.modules['threading'] = coro.emulation.threading
    sys.modules['socket'] = coro.emulation.socket

# ============================================================================
#                                 event loop
# ============================================================================

_original_event_loop = event_loop
install_signal_handlers = True
event_loop_is_running = False

def coro_is_running():
    """Determine if the coro event loop is running.

    :returns: True if the event loop is running, otherwise False.
    """
    return event_loop_is_running

def sigterm_handler (*_unused_args):
    _coro.set_exit()

def event_loop (timeout=30):
    """Start the event loop.

    :param timeout: The amount of time to wait for kevent to return
          events. You should probably *not* set this value.
    """
    global event_loop_is_running, with_timeout, sleep_relative
    # replace time.time with our tsc-based version
    time.time, time.original_time = tsc_time.now_raw_posix_fsec, time.time
    with_timeout = _original_with_timeout
    sleep_relative = _original_sleep_relative
    if install_signal_handlers:
        signal_handler.register(signal.SIGTERM, sigterm_handler)
        signal_handler.register(signal.SIGINT, sigterm_handler)
    spawn (tick_updater).set_name ('tick_updater')
    try:
        event_loop_is_running = True
        _original_event_loop (timeout)
    finally:
        event_loop_is_running = False
        # put it back
        time.time = time.original_time
