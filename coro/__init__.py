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

"""Coroutine threading library.

Introduction
============
Shrapnel is a cooperative threading library.

Getting Started
===============
When your process starts up, you must spawn a thread to do some work, and then
start the event loop.  The event loop runs forever processing events until the
process exits.  An example::

    import coro

    def main():
        print 'Hello world!'
        # This will cause the process to exit.
        coro.set_exit(0)

    coro.spawn(main)
    coro.event_loop()

Coroutines
==========
Every coroutine thread is created with either the `new` function (which does
NOT automatically start the thread) or the `spawn` function (which DOES
automatically start it).

Every thread has a unique numeric ID.  You may also set the name of the thread
when you create it.

Timeouts
========
The shrapnel timeout facility allows you to execute a function which will be
interrupted if it does not finish within a specified period of time.  The
`coro.TimeoutError` exception will be raised if the timeout expires.  See the
`with_timeout` docstring for more detail.

If the event loop is not running (such as in a non-coro process), a custom
version of `with_timeout` is installed that will operate using SIGALRM so that
you may use `with_timeout` in code that needs to run in non-coro processes
(though this is not recommended and should be avoided if possible).

Thread Local Storage
====================
There is a thread-local storage interface available for storing global data that
is thread-specific.  You instantiate a `ThreadLocal` instance and you can
assign attributes to it that will be specific to that thread.  See the
`ThreadLocal` docs for more detail.

Signal Handlers
===============
By default when you start the event loop, two signal handlers are installed
(for SIGTERM and SIGINT). The default signal handler will exit the event loop.
You can change this behavior by setting `install_signal_handlers` to False
before starting the event loop.

See `coro.signal_handler` for more detail on setting coro signal handlers.

Selfishness
===========
Certain socket operations are allowed to try to execute without blocking if
they are able to (such as send/receiving data on a local socket or on a
high-speed network). However, there is a limit to the number of times a thread
is allowed to do this. The default is 4.  The default may be changed
(`set_selfishness`) and the value on a per-thread may be changed
(`coro.coro.set_max_selfish_acts`).

Time
====
Shrapnel uses the `tsc_time` module for handling time.  It uses the TSC
value for a stable and high-resolution unit of time.  See that module's
documentation for more detail.

A thread is always created when you start the event loop that will
resynchronize the TSC relationship to accomodate any clock drift (see
`tick_updater` and `tsc_time.update_time_relation`).

Exception Notifier
==================
When a thread exits due to an exception, by default a stack trace is printed to
stderr.  You may install your own callback to handle this situation.  See the
`set_exception_notifier` function for more detail.

Debug Output
============
The shrapnel library provides a mechanism for printing debug information to
stderr.  The `print_stderr` function will print a string with a timestamp
and the thread number.  The `write_stderr` function writes the string verbatim.

Shrapnel keeps a reference to the "real" stderr (in `saved_stderr`) and the
`print_stderr` and `write_stderr` functions always use the real stderr value. A
particular reason for doing this is the backdoor module replaces sys.stderr and
sys.stdout, but we do not want debug output to go to the interactive session.

Profiling
=========
Shrapnel has its own profiler that is coro-aware.  See `coro.profiler` for
details on how to run the profiler.

:Variables:
    - `all_threads`: A dictionary of all live coroutine objects.  The key is
      the coroutine ID, and the value is the coroutine object.
    - `saved_stderr`: The actual stderr object for the process.  This normally
      should not be used.  An example of why this exists is because the
      backdoor replaces sys.stderr while executing user code.
"""

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

# ============================================================================
#                        tracebacks/exceptions
# ============================================================================

compact_traceback = tb.traceback_string

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

    """An error occurred in the `in_parallel` function.

    :IVariables:
        - `result_list`: A list of ``(status, result)`` tuples. ``status`` is
          either `SUCCESS` or `FAILURE`.  For success, the result is the return
          value of the function.  For failure, it is the output from
          `sys.exc_info`.
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

    If one or more functions raises an exception, then the `InParallelError`
    exception will be raised.

    :Parameters:
        - `fun_arg_list`: A list of ``(fun, args)`` tuples.

    :Return:
        Returns a list of return values from the functions.

    :Exceptions:
        - `InParallelError`: One or more of the functions raised an exception.
    """
#         InParallelError, [(SUCCESS, result0), (FAILURE, exc_info1), ...]

    n = len(fun_arg_list)
    if n==0:
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
            raise InParallelError, result_list
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

    :Parameters:
        - `pid`: The process ID to wait for.

    :Return:
        Returns a tuple ``(pid, status)`` of the process.

    :Exceptions:
        - `SimultaneousError`: Something is already waiting for this process
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

    :Parameters:
        - `thread_id`: The thread ID.

    :Return:
        Returns the coroutine object.

    :Exceptions:
        - `KeyError`: The coroutine does not exist.
    """
    return all_threads[thread_id]

def where (co):
    """Return a string indicating where the given coroutine thread is currently
    running.

    :Parameters:
        - `co`: The coroutine object.

    :Return:
        Returns a string displaying where the coro thread is currently
        executing.
    """
    f = co.get_frame()
    return tb.stack_string(f)

def where_all():
    """Get a dictionary of where all coroutines are currently executing.

    :Return:
        Returns a dictionary mapping the coroutine ID to a tuple of ``(name,
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

    :Parameters:
        - `fun`: The function to call when the coroutine starts.
        - `thread_name`: The name of the thread.  Defaults to the name of the
          function.

    :Return:
        Returns the new coroutine object.
    """
    if kwargs.has_key('thread_name'):
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

    :Parameters:
        - `fun`: The function to call when the coroutine starts.
        - `thread_name`: The name of the thread.  Defaults to the name of the
          function.

    :Return:
        Returns the new coroutine object.
    """
    if kwargs.has_key('thread_name'):
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

    :Return:
        Returns True if the event loop is running, otherwise False.
    """
    return event_loop_is_running

def sigterm_handler (*_unused_args):
    _coro.set_exit()

def event_loop (timeout=30):
    """Start the event loop.

    :Parameters:
        - `timeout`: The amount of time to wait for kevent to return
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
