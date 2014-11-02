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

# -*- Mode: Pyrex -*-
#cython: embedsignature=True

"""Pyrex module for coroutine implementation.

Module variables defined below are available only from Pyrex. Python-accessible
variables are documented in the top level of the coro package ``__init__.py``.

"""

__coro_version__ = "$Id: //prod/main/ap/shrapnel/coro/_coro.pyx#114 $"


import coro as coro_package
import warnings

# ================================================================================
# a re-implementation of the IronPort coro-threading system, this time
# in Cython, and using stack copying and switching with a stripped-down
# version of the 'set/getcontext' API.
# ================================================================================

# XXX: blame jj behrens for this.
# XXX: instead of a two-stack solution, think about an n-stack solution.
#      [the main drawback is that each coro is then tied to a particular stack...
#       this might be appropriate for a system that needs a small number of high-priority
#       threads that never get swapped out, e.g, a TCP implementation]

# ================================================================================
#                        external declarations
# ================================================================================

include "pyrex_helpers.pyx"
include "tsc_time_include.pyx"

from coro.clocks import tsc_time as tsc_time_module

cdef extern from "stdlib.h":
    IF UNAME_SYSNAME == "Linux":
        void random()
    ELSE:
        void srandomdev()

from cpython.ref cimport Py_DECREF, Py_INCREF
from cpython.mem cimport PyMem_Free, PyMem_Malloc
from cpython.list cimport PyList_New
from cpython.bytes cimport PyBytes_FromStringAndSize
from posix.unistd cimport fork as posix_fork

cdef extern from "Python.h":
    ctypedef struct PyThreadState:
        PyFrameObject * frame
        int recursion_depth
        void * curexc_type
        void * curexc_value
        void * curexc_traceback
        void * exc_type
        void * exc_value
        void * exc_traceback
    PyThreadState * _PyThreadState_Current

# ================================================================================
#                             global variables
# ================================================================================
# Number of CPU ticks per second (uint64_t).
cdef uint64_t _ticks_per_sec
cdef object ticks_per_sec
_ticks_per_sec = tsc_time_module.ticks_per_sec
# Make a Python Long version.  There are a few cases where we want to do math
# against a Python object, and this prevents Pyrex from first converting this
# to a Long.
ticks_per_sec = _ticks_per_sec

cdef dict _all_threads
_all_threads = {}
all_threads = _all_threads

# ================================================================================
#                             utility funs
# ================================================================================

import os

def get_module_name (n):
    try:
        return os.path.split (n)[-1].split('.')[0]
    except:
        return '???'

cdef int _get_refcnt (void * ob):
    return (<int *>ob)[0]

def get_refcnt (ob):
    return _get_refcnt (<void*>ob)

cdef void ZAP(void **p):
    # Silly dance because Pyrex calls INCREF when you cast to an object.
    if p[0] != NULL:
        Py_DECREF(<object>p[0])
        p[0] = NULL

# ================================================================================
#                                sysctl
# ================================================================================

IF UNAME_SYSNAME == "FreeBSD":
    cdef extern from "sys/sysctl.h":
        int sysctlbyname (
            char * name,
            void * oldp, size_t * oldlenp,
            void * newp, size_t newlen
            )

    class SysctlError (Exception):
        pass

    cdef int get_sysctl_int (name) except? -1:
        cdef int result
        cdef size_t oldlen
        oldlen = sizeof (result)
        if sysctlbyname (name, <void*>&result, &oldlen, NULL, 0) == -1:
            raise_oserror()
        elif oldlen != sizeof (result):
            raise SysctlError, "sizeof (sysctl(%s)) != sizeof(int)" % (name,)
        else:
            return result

include "fifo.pyx"

# ================================================================================
#                       coroutine/context object
# ================================================================================

import sys

class YieldFromMain (Exception):
    "attempt to yield from main"
    pass

class ScheduleError (Exception):
    "attempt to schedule an already-scheduled coroutine"
    pass

class DeadCoroutine (ScheduleError):
    "attempt to resume a dead coroutine"
    pass

class NotStartedError (ScheduleError):
    """Attempted to interrupt a thread before it has started."""

# used by the profiler
cdef struct call_stack:
    # Next is NULL for the end of the linked list.
    call_stack * next
    void * func     # Really a <function>
    void * b        # Really a <bench>

cdef struct machine_state:
    void * stack_pointer
    void * frame_pointer
    void * insn_pointer
    # other registers that need saving
    #          #  x86    amd64
    void * r1  #  ebx     rbx
    void * r2  #  esi     r12
    void * r3  #  edi     r13
    void * r4  #          r14
    void * r5  #          r15

# from swap.c
cdef extern int __swap (void * ts, void * fs)
cdef extern object void_as_object (void * p)
cdef extern int frame_getlineno (object frame)
cdef extern int coro_breakpoint()
cdef extern int SHRAP_STACK_PAD

# forward
#cdef public class sched  [ object sched_object, type sched_type ]
cdef public class queue_poller [ object queue_poller_object, type queue_poller_type ]
cdef sched the_scheduler "_the_scheduler"
cdef main_stub the_main_coro "the_main_coro"
cdef queue_poller the_poller "the_poller"

cdef int default_selfishness
default_selfishness = 4

def set_selfishness(n):
    """Set the global default selfishness limit.

    This sets the default for every new coroutine.

    :param n: The new limit.
    """
    global default_selfishness
    default_selfishness = n

cdef int live_coros
live_coros = 0

cdef public class coro [ object _coro_object, type _coro_type ]:

    """The coroutine object.

    Do not create this object directly.  Use either :func:`new` or
    :func:`spawn` to create one.
    """

    def __init__ (self, fun, args, kwargs, int id, name=None):
        global live_coros
        self.fun = fun
        self.args = args
        self.kwargs = kwargs
        self.dead = 0
        self.started = 0
        self.id = id
        self.scheduled = 0
        self.stack_copy = NULL
        self.stack_size = 0
        self.frame = NULL
        self.top = NULL
        self.selfish_acts = default_selfishness
        self.max_selfish_acts = default_selfishness
        if name is None:
            self.name = <bytes> ('coro %d' % (self.id,))
        live_coros = live_coros + 1

    def __dealloc__ (self):
        global live_coros
        live_coros = live_coros - 1
        if self.stack_copy != NULL:
            IF CORO_DEBUG:
                # clear memory to help in gdb
                memset (self.stack_copy, 0, self.stack_size)
            PyMem_Free (self.stack_copy)
        ZAP(&self.saved_exception_data[0])
        ZAP(&self.saved_exception_data[1])
        ZAP(&self.saved_exception_data[2])
        ZAP(&self.saved_exception_data[3])
        ZAP(&self.saved_exception_data[4])
        ZAP(&self.saved_exception_data[5])
        #W ('__dealloc__ coro #%d\n' % (self.id,))

    # XXX backward compatibility - remove me some day.
    def thread_id (self):
        return self.id

    def __repr__ (self):
        return "<%s #%d name='%s' dead=%d started=%d scheduled=%d at 0x%x>" % (
            self.__class__.__name__,
            self.id,
            self.name,
            self.dead,
            self.started,
            self.scheduled,
            <long><void *>self
            )

    cdef __create (self):
        cdef void ** stack_top
        #
        # the idea is that when we __resume() <coro>, that the 'restored' environment
        # will mimic that of a fresh call to "_wrap (<co>, <fun>, <args>)", with the
        # correct arguments sitting in their correct places on the stack.
        #
        #
        #  |    ...    |
        #  +-----------+
        #  |  local3   |  <-- %esp
        #  +-----------+
        #  |  local2   |
        #  +-----------+
        #  |  local1   |
        #  +-----------+
        #  |  return   |  <-- %ebp
        #  +-----------+
        #  |  arg0     |
        #  +-----------+
        #  |  arg1     |
        #  +-----------+
        #  | <unused>  |
        #  +-----------+  <-- stack_top
        #
        # There's an extra unused slot at the very top of the stack,
        # this is to keep the stack frame of _wrap0() 16-byte aligned,
        # a requirement on the amd64.  [Normally the compiler would take
        # care of this for us...]
        #
        stack_top = <void**> (the_scheduler.stack_base + (the_scheduler.stack_size - SHRAP_STACK_PAD))
        # bogus return address
        stack_top[-2] = <void*>NULL
        # simulate "_wrap0 (<co>)"
        stack_top[-1] = <void*>self
        self.state.stack_pointer = &(stack_top[-3])
        self.state.frame_pointer = &(stack_top[-2])
        self.state.insn_pointer  = <void*> _wrap0

    cdef __destroy (self):
        self.fun = None
        self.args = None
        self.kwargs = None

    cdef __yield (self):
        # -- always runs outside of main --
        # save exception data
        self.save_exception_data()
        if not self.dead:
            the_scheduler._current = the_main_coro
            the_scheduler._last = self
        else:
            # Beware.  When this coroutine is 'dead', it's about to __swap()
            # back to <main>, *never to return*.  That means the DECREF's that
            # pyrex generates at the end of this function will never be
            # performed.  At the time of this writing, there are no local
            # variables in use yet, so there's nothing we need to do.  Just be
            # very careful when touching this method.

            # This is opportunistic to clear references to cyclical structures.
            ZAP(&self.saved_exception_data[0])
            ZAP(&self.saved_exception_data[1])
            ZAP(&self.saved_exception_data[2])
            ZAP(&self.saved_exception_data[3])
            ZAP(&self.saved_exception_data[4])
            ZAP(&self.saved_exception_data[5])

        # save/restore tstate->frame
        self.frame = _PyThreadState_Current.frame
        if the_scheduler.profiling and self.top:
            the_profiler.charge_yield (self.top)
        _PyThreadState_Current.frame = NULL
        self.saved_recursion_depth = _PyThreadState_Current.recursion_depth
        __swap (<void*>&(the_scheduler.state), <void*>&(self.state))
        _PyThreadState_Current.frame = self.frame
        self.frame = NULL
        v = self.value
        # Clear out the reference so we don't hang on to it for a potentially
        # long time.
        self.value = None
        # XXX think about ways of keeping a user from resuming with
        #     an <exception> object. [keep the type secret?]
        if isinstance(v, exception):
            raise v.exc_value
        else:
            return v

    cdef __resume (self, value):
        cdef PyFrameObject * main_frame
        cdef uint64_t t0, t1
        # -- always runs in main --
        if not self.started:
            self.__create()
            self.started = 1
        if not self.dead:
            self.scheduled = 0
            self.value = value
            the_scheduler._current = self
            the_scheduler._restore (self)
            # restore exception data
            self.restore_exception_data()
            # restore frame
            main_frame = _PyThreadState_Current.frame
            _PyThreadState_Current.recursion_depth = self.saved_recursion_depth
            _PyThreadState_Current.frame = NULL
            if the_scheduler.profiling and self.top:
                the_profiler.charge_main()
            t0 = c_rdtsc()
            __swap (<void*>&(self.state), <void*>&(the_scheduler.state))
            t1 = c_rdtsc()
            _PyThreadState_Current.frame = main_frame
            the_scheduler._current = None
            if self.dead:
                the_scheduler._last = None
                return
            else:
                the_scheduler._preserve_last()
                if the_scheduler.latency_threshold and (t1 - t0) > the_scheduler.latency_threshold:
                    the_scheduler.print_latency_warning (self, t1 - t0)
                return
        else:
            raise DeadCoroutine, self

    cdef save_exception_data (self):
        self.saved_exception_data[0] = _PyThreadState_Current.curexc_type
        self.saved_exception_data[1] = _PyThreadState_Current.curexc_value
        self.saved_exception_data[2] = _PyThreadState_Current.curexc_traceback
        self.saved_exception_data[3] = _PyThreadState_Current.exc_type
        self.saved_exception_data[4] = _PyThreadState_Current.exc_value
        self.saved_exception_data[5] = _PyThreadState_Current.exc_traceback

        _PyThreadState_Current.curexc_type      = NULL
        _PyThreadState_Current.curexc_value     = NULL
        _PyThreadState_Current.curexc_traceback = NULL
        _PyThreadState_Current.exc_type         = NULL
        _PyThreadState_Current.exc_value        = NULL
        _PyThreadState_Current.exc_traceback    = NULL

    cdef restore_exception_data (self):
        cdef void * curexc_type
        cdef void * curexc_value
        cdef void * curexc_traceback
        cdef void * exc_type
        cdef void * exc_value
        cdef void * exc_traceback

        # Clear out the current tstate exception.  This is necessary
        # because main may have a previous exception set (such as
        # SchedulError from schedule_ready_events), and we don't
        # want to stomp on it.  We don't save it away because the
        # main thread doesn't need that level of exception safety.
        #
        # Store locally because DECREF can cause code to execute.
        curexc_type = _PyThreadState_Current.curexc_type
        curexc_value = _PyThreadState_Current.curexc_value
        curexc_traceback = _PyThreadState_Current.curexc_traceback
        exc_type = _PyThreadState_Current.exc_type
        exc_value = _PyThreadState_Current.exc_value
        exc_traceback = _PyThreadState_Current.exc_traceback

        _PyThreadState_Current.curexc_type = NULL
        _PyThreadState_Current.curexc_value = NULL
        _PyThreadState_Current.curexc_traceback = NULL
        _PyThreadState_Current.exc_type = NULL
        _PyThreadState_Current.exc_value = NULL
        _PyThreadState_Current.exc_traceback = NULL

        # Can't use XDECREF when casting a void in Pyrex.
        if curexc_type != NULL:
            Py_DECREF(<object>curexc_type)
        if curexc_value != NULL:
            Py_DECREF(<object>curexc_value)
        if curexc_traceback != NULL:
            Py_DECREF(<object>curexc_traceback)
        if exc_type != NULL:
            Py_DECREF(<object>exc_type)
        if exc_value != NULL:
            Py_DECREF(<object>exc_value)
        if exc_traceback != NULL:
            Py_DECREF(<object>exc_traceback)

        _PyThreadState_Current.curexc_type      = self.saved_exception_data[0]
        _PyThreadState_Current.curexc_value     = self.saved_exception_data[1]
        _PyThreadState_Current.curexc_traceback = self.saved_exception_data[2]
        _PyThreadState_Current.exc_type         = self.saved_exception_data[3]
        _PyThreadState_Current.exc_value        = self.saved_exception_data[4]
        _PyThreadState_Current.exc_traceback    = self.saved_exception_data[5]

        self.saved_exception_data[0] = NULL
        self.saved_exception_data[1] = NULL
        self.saved_exception_data[2] = NULL
        self.saved_exception_data[3] = NULL
        self.saved_exception_data[4] = NULL
        self.saved_exception_data[5] = NULL

    cdef _schedule (self, value):
        """Schedule this coroutine to run.

        :param value: The value to resume the coroutine with.  Note that
            "interrupting" the coroutine resumes it with a special
            ``exception`` value which is checked when this coro is resumed.

        :raises DeadCoroutine: The coroutine is dead (it has already exited).
        :raises ScheduleError: The coroutine is already scheduled to run.
        :raises ScheduleError: Attempted to schedule the currently running coro.
        """
        the_scheduler._schedule (self, value)

    cdef _unschedule (self):
        """Unschedule this coroutine.

        :returns: True if it was successfully unscheduled, False if not.
        """
        return the_scheduler._unschedule (self)

    def schedule (self, value=None):
        """Schedule this coroutine to run.

        :param value: The value to resume the coroutine with.  Defaults to
            None.

        :raises DeadCoroutine: The coroutine is dead (it has already exited).
        :raises ScheduleError: The coroutine is already scheduled to run.
        :raises ScheduleError: Attempted to schedule the currently running coro.
        """
        return self._schedule (value)

    def start (self):
        """Start the coroutine for the first time.

        :raises ScheduleError: The coro is already started.
        """
        if self.started:
            raise ScheduleError(self)
        return self._schedule (())

    def _resume (self, value=None):
        return self.__resume (value)

    def _yield (self):
        return self.__yield ()

    cdef _die (self):
        self.dead = 1
        del _all_threads[self.id]
        self.fun = None
        self.args = None
        if self.waiting_joiners is not None:
            self.waiting_joiners.wake_all()

    cdef __interrupt (self, the_exception):
        """Schedule the coro to resume with an exception.

        :param the_exception: The exception to raise (may be class or instance).

        :raises DeadCoroutine: The coroutine is dead (it has already exited).
        :raises ScheduleError: The coroutine is already scheduled to run.
        :raises ScheduleError: Attempted to interrupt the currently running coro.
        """
        self._schedule (exception (the_exception))

    def shutdown (self):
        """Shut down this coroutine.

        This will raise the :exc:`Shutdown` exception on this thread.

        This method will not fail.  If the thread is already dead, then it is
        ignored.  If the thread hasn't started, then it is canceled.
        """
        if not self.dead:
            self.raise_exception (Shutdown, cancel_start=True)

    def raise_exception (self, the_exception, force=True, cancel_start=False):
        """Schedule this coroutine to resume with an exception.

        :param the_exception: The exception to raise.  May be an Exception class or instance.
        :param force: If True, will force the exception to be raised, even if
              the coroutine is already scheduled.  Defaults to True.
        :param cancel_start: If True, will cancel the coroutine if it has not
              started, yet.  If False, and the couroutine has not started, then
              it will rise :exc:`NotStartedError`.  Defaults to False.

        :raises DeadCoroutine: The coroutine is dead (it has already exited).
        :raises ScheduleError: The coroutine is already scheduled to run (and
              ``force`` was set to False).
        :raises ScheduleError: Attempted to raise an exception on the currently
              running coro.
        :raises NotStartedError: The coroutine has not started, yet.
        """
        IF CORO_DEBUG:
            # Minstack coro used to take an "exception value" as the second
            # argument.  Nobody used it, though.  This can be removed someday.
            if not isinstance(force, int):
                raise AssertionError('The force argument must be a boolean.')
        if self.dead:
            raise DeadCoroutine(self)

        if self.started:
            if force and self.scheduled:
                self._unschedule()
            self.__interrupt (the_exception)
        else:
            if cancel_start:
                if self.scheduled:
                    self._unschedule()
                self._die()
            else:
                raise NotStartedError(self)

    def interrupt (self, value=None):
        warnings.warn('interrupt is deprecated, use raise_exception() or shutdown() instead.', DeprecationWarning)
        if value is None:
            self.__interrupt (Interrupted)
        else:
            self.__interrupt (Interrupted(value))

    def resume_with_exc (self, exc_type, exc_value=None):
        warnings.warn('resume_with_exc is deprecated, use raise_exception() or shutdown() instead.', DeprecationWarning)
        if exc_value is None:
            self.__interrupt (exc_type)
        else:
            if type(exc_type) is type(Exception) and exc_value.__class__ is exc_type:
                # raise SomeException, SomeException(some_value)
                self.__interrupt (exc_value)
            else:
                # raise SomeException, some_value
                self.__interrupt (exc_type(exc_value))

    def get_frame (self):
        if self.frame is NULL:
            # we're the current thread
            f = void_as_object (_PyThreadState_Current.frame)
            # I get bogus info unless I do this.  A Pyrex effect?
            return f.f_back
        else:
            return void_as_object (self.frame)

    property compress:
        def __get__ (self):
            return self.compress
        def __set__ (self, bint val):
            self.compress = val

    def setName (self, name):
        warnings.warn('setName is deprecated, use set_name instead.', DeprecationWarning)
        return self.set_name(name)

    def set_name (self, name):
        """Set the name of this coroutine thread.

        :param name: The name of the thread.
        """
        self.name = name
        return self

    def getName (self):
        warnings.warn('getName is deprecated, use get_name instead.', DeprecationWarning)
        return self.get_name()

    def get_name (self):
        """Get the name of this coroutine thread.

        If no name has been specified, then a name is generated.

        :returns: The coroutine name.
        """
        return self.name

    cdef int try_selfish (self):
        if self.selfish_acts > 0:
            self.selfish_acts = self.selfish_acts - 1
            return 1
        else:
            self.selfish_acts = self.max_selfish_acts
            return 0

    def set_max_selfish_acts (self, maximum):
        """Set the maximum number of selfish acts this coroutine is allowed to
        perform.

        When a coroutine is created, it defaults to 4.

        :param maximum: The maximum number of selfish acts.
        """
        if maximum > 32768:
            raise ValueError('Value too large.')
        elif maximum <= 0:
            raise ValueError('Value too small.')

        old_value = self.max_selfish_acts
        self.max_selfish_acts = maximum
        self.selfish_acts = self.max_selfish_acts

        return old_value

    def join(self):
        """Wait for thread termination.

        This will wait for this thread to exit.  If the thread has already
        exited, this will return immediately.

        Warning: If a thread is created, but never started, this function will
        block forever.
        """
        if the_scheduler._current is self:
            raise AssertionError('Cannot join with self.')

        if self.dead:
            return

        if self.waiting_joiners is None:
            self.waiting_joiners = condition_variable()

        self.waiting_joiners.wait()

cdef class main_stub (coro):
    """This class serves only one purpose - to catch attempts at yielding() from main,
    which almost certainly means someone forgot to run inside the event loop."""

    def __init__ (self):
        self.name = b'main/scheduler'
        self.id = -1

    cdef __yield (self):
        raise YieldFromMain ("is the event loop running?")

def get_live_coros():
    """Get the number of live coroutines.

    Note that this includes coroutines that have not started or have exited,
    but not deallocated, yet.

    :returns: The number of live coroutine objects.
    """
    global live_coros
    return live_coros

cdef int next_coro_id

next_coro_id = 1

from libc.limits cimport INT_MAX

cdef int get_coro_id() except -1:
    global next_coro_id
    while 1:
        result = next_coro_id
        next_coro_id = next_coro_id + 1
        if next_coro_id == INT_MAX:
            next_coro_id = 1
        if not _all_threads.has_key (result):
            return result

def default_exception_notifier():
    print_stderr (
        'thread %d (%s): error %s\n' % (
            the_scheduler._current.id,
            the_scheduler._current.getName(),
            tb.traceback_string()
            )
        )

exception_notifier = default_exception_notifier

def set_exception_notifier (new_func):
    """Set the exception notifier.

    The exception notifier is a function that is called when a coroutine exits
    due to an exception.  The default exception notifier simply prints the name
    of the coroutine and a traceback of where the exception was raised.

    :param new_func: The exception notifier to call.  It takes no arguments.

    :returns: The old exception notifier.
    """
    global exception_notifier
    old_func = exception_notifier
    if old_func == default_exception_notifier:
        old_func = None
    if new_func is None:
        new_func = default_exception_notifier
    exception_notifier = new_func
    return old_func

# defined in swap.c: terminates with a call to __yield().
# the extra layer of wrapper is to avoid skipping DECREF cleanup
# every time through __resume/__yield().
cdef extern void _wrap0 (void *)

from coro import tb

cdef public void _wrap1 "_wrap1" (coro co):
    try:
        try:
            co.fun (*co.args, **co.kwargs)
        except Shutdown:
            pass
        except:
            try:
                exception_notifier()
            except:
                default_exception_notifier()
    finally:
        co._die()

# ================================================================================
#                             event queue
# ================================================================================

from event_queue import event_queue, __event_queue_version__

cdef class event:
    cdef public uint64_t t
    cdef public object v
    cdef readonly int expired

    def __cinit__ (self, uint64_t t, v):
        self.t = t
        self.v = v
        self.expired = 0

    cdef expire (self):
        self.v = None
        self.expired = 1

    def __repr__ (self):
        return '<%s t=%r v=%r expired=%d at 0x%x>' % (
            self.__class__.__name__,
            self.t,
            self.v,
            self.expired,
            <long><void *>self
            )

    def __cmp__ (self, event other):
        if self.t < other.t:
            return -1
        elif self.t > other.t:
            return 1
        else:
            return 0

# ok, the issue with timebombs and with_timeout().  can we do anything?
# first off - there's *no way* around using an exception.  anything else
# would violate try/finally semantics.  so a timeout *must* propagate as
# an exception.  it's possible that we could notice when a timebomb has
# been ignored, and throw an exception or warning of some kind to stderr.

cdef class timebomb:
    cdef coro co
    cdef uint64_t when

    def __cinit__ (self, coro co, delta):
        # <delta> is in seconds, and can be either floating point or integer.
        self.co = co
        # Two lines to avoid Pyrex Python conversion.
        self.when = delta * ticks_per_sec
        self.when = self.when + c_rdtsc()

cdef class exception:
    "used to interrupt coroutines with an exception"
    cdef public object exc_value

    def __init__ (self, exc_value):
        self.exc_value = exc_value

class Interrupted (BaseException):
    """A coroutine has been interrupted unexpectedly"""
    pass

class TimeoutError (Interrupted):
    """A call to with_timeout() has expired"""
    pass

class SimultaneousError (Exception):

    """Two threads attempted a conflicting blocking operation (e.g., read() on
    the same descriptor).

    :ivar co: The coroutine that is trying to block on an event.
    :ivar other: The coroutine or function that is already waiting on the
          event.
    :ivar event: The event that it is trying to block on.  For kqueue, this
          is normally a ``kevent_key`` object.
    """

    def __init__(self, co, other, object event):
        self.co = co
        self.other = other
        self.event = event
        Exception.__init__(self, co, other, event)

    def __repr__(self):
        return '<SimultaneousError co=%r other=%r event=%r>' % (self.co, self.other, self.event)

    def __str__(self):
        return self.__repr__()

class ClosedError (Exception):
    """Another thread closed this descriptor."""

class Shutdown (Interrupted):
    """The thread is shutting down."""

class WakeUp (Exception):
    """A convenience exception used to wake up a sleeping thread."""

# choose a library for stack compression
IF COMPILE_LZ4:
    include "zstack_lz4.pyx"
ELIF COMPILE_LZO:
    include "zstack_lzo.pyx"
ELSE:
    include "zstack_zlib.pyx"

# ================================================================================
#                              scheduler
# ================================================================================

cdef public class sched [ object sched_object, type sched_type ]:
    def __init__ (self, stack_size=4*1024*1024):
        self.stack_size = stack_size
        # tried using mmap & MAP_STACK, always got ENOMEM
        self.stack_base = PyMem_Malloc (stack_size)
        if self.stack_base == NULL:
            raise MemoryError
        #W ('stack=%x-%x\n' % (
        #    <int>self.stack_base,
        #    <int>self.stack_base + stack_size
        #    ))
        self._current = the_main_coro
        self._last = None
        self.pending = []
        self.staging = []
        self.state.stack_pointer = NULL
        self.state.frame_pointer = NULL
        self.state.insn_pointer = NULL
        self.events = event_queue()
        self.profiling = 0
        self.latency_threshold = _ticks_per_sec / 5
        self.squish = zstack (stack_size)

    def current (self):
        return self._current

    # x86, stack grows down
    #
    # hi   +------+ <- stack_top
    #      |      |
    #      +------+
    #      |      |
    #      +------+
    #      |      |
    #      +------+ <- frame_pointer
    #      |      |
    # lo   +------+ <- stack_pointer
    #        ....
    #        ....
    # base +------+ <- stack_base

    cdef _preserve_last (self):
        cdef void * stack_top
        cdef size_t size
        cdef void * base
        if self._last is not None:
            # ok, we want to squirrel away the slice of stack it was using...
            # 1) identify the slice
            stack_top = self.stack_base + self.stack_size
            size = stack_top - self._last.state.stack_pointer
            base = self._last.state.stack_pointer
            # 1.5) maybe compress it
            if self._last.compress:
                size = self.squish.deflate (base, size)
                base = self.squish.buffer
                self._last.compressed = True
            else:
                self._last.compressed = False
            # 2) get some storage
            if self._last.stack_size != size:
                # XXX: more heuristics to avoid malloc
                if self._last.stack_copy:
                    IF CORO_DEBUG:
                        # clear memory to help in gdb
                        memset (self._last.stack_copy, 0, self._last.stack_size)
                    PyMem_Free (self._last.stack_copy)
                self._last.stack_copy = PyMem_Malloc (size)
                if self._last.stack_copy == NULL:
                    raise MemoryError
                self._last.stack_size = size
            # 3) copy the stack
            memcpy (self._last.stack_copy, base, size)
            self._last = None

    cdef _restore (self, coro co):
        if co is None:
            raise ValueError
        if co.stack_copy:
            if co.compressed:
                self.squish.inflate (co.state.stack_pointer, self.stack_size, co.stack_copy, co.stack_size)
            else:
                memcpy (co.state.stack_pointer, co.stack_copy, co.stack_size)

    cdef _schedule (self, coro co, object value):
        if co.dead:
            raise DeadCoroutine, self
        elif co.scheduled:
            raise ScheduleError, self
        elif co is self._current:
            raise ScheduleError, self
        else:
            co.scheduled = 1
            self.pending.append ((co, value))

    cdef _unschedule (self, coro co):
        """Unschedule this coroutine.

        :param co: The coroutine to unschedule.

        :returns: True if it was successfully unscheduled, False if not.
        """
        cdef int i
        for i from 0 <= i < len(self.pending):
            co2, v2 = self.pending[i]
            if co is co2:
                del self.pending[i]
                co.scheduled = 0
                return True
        else:
            for i from 0 <= i < len(self.staging):
                co2, v2 = self.staging[i]
                if co is co2:
                    self.staging[i] = (None, None)
                    co.scheduled = 0
                    return True
            else:
                return False

    def compress (self, coro co):
        cdef size_t size, csize
        size = co.stack_size
        if not co.compressed:
            csize = self.squish.deflate (co.stack_copy, co.stack_size)
            PyMem_Free (co.stack_copy)
            co.stack_copy = PyMem_Malloc (csize)
            if not co.stack_copy:
                raise MemoryError
            memcpy (co.stack_copy, self.squish.buffer, csize)
            co.stack_size = csize
            co.compressed = True
            return size, csize
        else:
            # idempotent
            return size, size

    cdef print_latency_warning (self, coro co, uint64_t delta):
        write_stderr (
            "%s High Latency: (%.3fs) for %r\n" % (
                tsc_time_module.now_tsc().ctime(),
                <double>delta / tsc_time_module.ticks_per_sec,
                co
                )
            )

    def set_latency_warning (self, int factor):
        """Set the latency warning threshold multiplier.

        The default latency warning threshold is 0.2 seconds.  This will allow
        you to change the threshold by multiplying the 0.2 value.

        :param factor: The latency threshold multiplier.  May be a number from
              0 to 300.  A value of 0 disables latency warnings.

        :returns: The old multipler factor.

        :raises ValueError: The factor is too small or too large.
        """
        if factor < 0 or factor > 300:
            raise ValueError('Latency factor must be a number from 0 to 300.')

        old_factor = self.latency_threshold / (_ticks_per_sec / 5)
        self.latency_threshold = (_ticks_per_sec / 5) * factor
        return old_factor

    def with_timeout (self, delta, function, *args, **kwargs):
        """Call a function with a timeout.

        Additional arguments and keyword arguments provided are passed to the
        function.  This will re-raise any exceptions raised by the function.

        If a timeout expires, but the function returns before the next pass in
        the event loop, then the timeout will be diffused.

        If a coroutine is already scheduled to run (such as if it received a
        kevent), and the timeout expires, the timeout will be put on "hold" to
        let the coroutine run and process the data.  If the function returns,
        then the timeout will be defused, otherwise the timeout will be given
        another chance to fire during the next pass through the event loop. One
        should note that due to this behavior, if a coroutine is continually
        receiving kevents, the timeout will never fire until the kevents stop.

        Nested timeouts will be handled correctly. If an outer timeout fires
        first, then only the outer ``except TimeoutError`` exception handler
        will catch it.  An exception handlers on the inside will be skipped
        becaue the actual exception is the :exc:`Interrupted` exception until it
        gets to the original ``with_timeout`` frame.

        Nested timeouts that are set to fire at the exact same time are not
        defined which one will fire first.

        Care must be taken to *never* catch the :exc:`Interrupted` exception within
        code that is wrapped with a timeout.

        :param delta: The number of seconds to wait before raising a timeout.
                       Should be >= 0. Negative value will be treated as 0.
        :param function: The function to call.

        :returns: The return value of the function.

        :raises TimeoutError: The function did not return within the specified
              timeout.
        """
        cdef timebomb tb
        cdef event e

        # Negative timeout is treated the same as 0.
        if delta < 0:
            delta = 0

        tb = timebomb (self._current, delta)
        e = event (tb.when, tb)
        self.events.insert (e.t, e)
        try:
            try:
                return function (*args, **kwargs)
            except Interrupted, value:
                # is this *my* timebomb?
                args = value.args
                if len(args) > 0 and args[0] is tb:
                    raise TimeoutError
                else:
                    raise
        finally:
            if not e.expired:
                self.events.remove (e.t, e)
            e.expire()

    cdef sleep (self, uint64_t when):
        """Sleep until a specific point in time.

        :param when: The TSC value when you want the coroutine to wake up.
        """
        cdef event e
        IF CORO_DEBUG:
            assert self._current is not None
        e = event (when, self._current)
        self.events.insert (when, e)
        try:
            (<coro>self._current).__yield ()
        finally:
            if not e.expired:
                self.events.remove (e.t, e)
            e.expire()

    def sleep_relative (self, delta):
        """Sleep for a period of time.

        If a thread is interrupted at the exact same time the sleep is
        finished, it is not defined whether the interrupt or the sleep "wins".
        Your thread may continue running (with the interrupt rescheduled to try
        again later), or it may be interrupted.

        :param delta: The number of seconds to sleep.
        """
        cdef uint64_t when
        # Two lines to avoid Pyrex Python conversion.
        when = delta * ticks_per_sec
        when = when + c_rdtsc()
        self.sleep (when)

    def sleep_absolute (self, uint64_t when):
        """Sleep until a specific point in time.

        :param when: The TSC value when you want the coroutine to wake up.
        """
        self.sleep (when)

    cdef schedule_ready_events (self, uint64_t now):
        cdef event e
        cdef timebomb tb
        cdef _fifo retry
        cdef coro c

        retry = _fifo()
        while len(self.events):
            e = self.events.top()
            if e.t <= now:
                self.events.pop()
                # two kinds of event values:
                # 1) a coro (for sleep_{relative,absolute}())
                # 2) a timebomb (for with_timeout())
                if not e.expired:
                    if isinstance (e.v, coro):
                        c = e.v
                        if not c.scheduled:
                            self._schedule (c, None)
                        e.expire()
                    elif isinstance (e.v, timebomb):
                        tb = e.v
                        try:
                            tb.co.__interrupt (Interrupted(tb))
                            e.expire()
                        except ScheduleError:
                            # we'll try this again next time...
                            retry._push (e)
                    else:
                        W ('schedule_ready_events(): unknown event type: %r\n' % (e.v,))
            else:
                break
        # retry all the timebombs that failed due to ScheduleError
        while retry.size:
            e = retry._pop()
            self.events.insert (e.t, e)

    cdef get_timeout_to_next_event (self, int default_timeout):
        cdef uint64_t delta, now
        cdef event e
        # default_timeout is in seconds
        now = c_rdtsc()
        if len(self.events):
            # 1) get time to next event
            while 1:
                e = self.events.top()
                if e.expired:
                    self.events.pop()
                else:
                    break
            if e.t < now:
                delta = 0
            else:
                delta = e.t - now
            if (default_timeout * _ticks_per_sec) < delta:
                # never wait longer than the default timeout
                return (default_timeout, 0)
            else:
                # 2) convert to timespec
                sec = delta / _ticks_per_sec
                nsec = ((delta % _ticks_per_sec) * 1000000000) / _ticks_per_sec
                return (sec, nsec)
        else:
            return (default_timeout, 0)

    def event_loop (self, timeout=30):
        """Start the event loop.

        :param timeout: The amount of time to wait for kevent to return
              events. You should probably *not* set this value.  Defaults to 30
              seconds.
        """
        global _exit, _exit_code, _print_exit_string
        cdef int i, n
        cdef coro co
        cdef uint64_t _now
        cdef object _coro_package
        cdef tuple x

        # Make a cdef reference to avoid __Pyx_GetName.
        _coro_package = coro_package
        the_poller.set_up()
        try:
            while not _exit:
                _now = c_rdtsc()
                # ugh, update these in the package namespace.
                _coro_package.now = _now
                _coro_package.now_usec = c_ticks_to_usec(_now)
                self.schedule_ready_events (_now)
                while 1:
                    if len(self.pending) > 0:
                        self.staging, self.pending = self.pending, self.staging
                        for i from 0 <= i < len (self.staging):
                            x = self.staging[i]
                            co, value = x
                            # co may be None if it was unscheduled.
                            if co is not None:
                                #W ('resuming %d: #%d\n' % (i, co.id))
                                co.scheduled = 0
                                co.__resume (value)
                                co = None
                        self.staging = []
                    else:
                        break
                if _exit:
                    sys.exit(_exit_code)
                the_poller.poll (
                    self.get_timeout_to_next_event (timeout)
                    )
        finally:
            the_poller.tear_down()
            if _print_exit_string:
                print_stderr ('Exiting...\n')


    def fork (self):
        cdef int result = posix_fork()
        if result == 0:
            the_poller.tear_down()
            the_poller.set_up()
        return result

# FOR EXTERNAL CONSUMPTION, do not call from within this file,
#    because it is declared void.  [void functions cannot propagate
#    exceptions]
cdef public void __yield "__yield"():
    (<coro>the_scheduler._current).__yield ()

cdef _YIELD():
    return (<coro>the_scheduler._current).__yield ()

def _yield ():
    return (<coro>the_scheduler._current).__yield ()

def yield_slice():
    """Yield to allow other threads to run.

    This will yield to allow other threads to run.  The coroutine will be
    rescheduled to run during the next pass through the event loop.
    """
    the_scheduler.sleep(c_rdtsc())

def schedule (coro co, value=None):
    """Schedule a coroutine to run.

    See :meth:`coro.schedule` for more detail.

    :param co: The coroutine to schedule.
    :param value: The value to resume the coroutine with.  Defaults to None.
    """
    return co._schedule (value)

IF UNAME_SYSNAME == "Linux":
    include "linux_poller.pyx"
ELSE:
    include "poller.pyx"
include "socket.pyx"
include "sync.pyx"
# extras used by ironport only
include "ironport.pyx"
include "profile.pyx"
IF UNAME_SYSNAME == "FreeBSD":
    include "aio.pyx"
IF COMPILE_LIO:
    include "lio.pyx"
include "local.pyx"

# ================================================================================

__versions__ = [
    __coro_version__,
    __socket_version__,
    __sync_version__,
    __event_queue_version__,
    __poller_version__,
    __profile_version__,
    ]

IF UNAME_SYSNAME == "FreeBSD":
    __versions__.append (__aio_version__)

IF COMPILE_LIO:
    __versions__.append (__lio_version__)

# XXX: I haven't figured out yet how to expose these globals to
# python.  'global' doesn't do the trick.  However, defining global
# functions to access them works...

# singletons
the_main_coro = main_stub()
the_scheduler = sched()
the_poller = queue_poller()
_the_scheduler = the_scheduler

def print_stderr (s):
    """Print a string to stderr with a timestamp.

    This will print the thread id, followed by a timestamp, followed by the
    string. If the string does not end with a newline, one will be added.

    :param s: A string to print.
    """
    try:
        timestamp = tsc_time_module.now_tsc().ctime()
        output = '%i:\t%s %s' % (current().thread_id(), timestamp, s)
        saved_stderr.write(output)
        if not output.endswith('\n'):
            saved_stderr.write('\n')
    except:
        # This is mainly to catch IOError when the log partition if full.
        # But in general we don't care about any errors.
        pass

def current():
    """Return the current coroutine object."""
    return the_scheduler._current

cdef _spawn (fun, args, kwargs):
    cdef coro co

    id = get_coro_id()
    co = coro (fun, args, kwargs, id)
    _all_threads[id] = co
    co._schedule (None)
    return co

def spawn (fun, *args, **kwargs):
    """Spawn a new coroutine.

    Additional arguments and keyword arguments will be passed to the given function.

    :param fun: The function to call when the coroutine starts.

    :returns: The new coroutine object.
    """
    return _spawn (fun, args, kwargs)

def new (fun, *args, **kwargs):
    """Create a new coroutine object.

    Additional arguments and keyword arguments will be passed to the given function.

    This will not start the coroutine.  Call the ``start`` method on the
    coroutine to schedule it to run.

    :param fun: The function to call when the coroutine starts.

    :returns: The new coroutine object.
    """
    id = get_coro_id()
    co = coro (fun, args, kwargs, id)
    _all_threads[id] = co
    return co

def set_exit(exit_code=0):
    """Indicate that the event loop should exit.

    Note that if any other coroutines are scheduled to run, they will be given
    a chance to run before exiting.

    :param exit_code: The exit code of the process.  Defaults to 0.
    """
    global _exit
    global _exit_code
    _exit = 1
    _exit_code = exit_code

def set_print_exit_string(val):
    """Set whether or not "Exiting" should be printed when the event loop
    exits.

    By default, the string will be printed.

    :param val: Whether or not "Exiting" should be printed when the event loop
          exits.
    """
    global _print_exit_string
    _print_exit_string = val

from libc cimport stdio

cdef void info(int sig):
    """Function to print current coroutine when SIGINFO (CTRL-T) is received."""
    cdef coro co
    cdef PyFrameObject * frame

    co = the_scheduler._current
    frame = _PyThreadState_Current.frame
    if co is not the_main_coro:
        stdio.fprintf(stdio.stderr, 'coro %i "%s" at %s: %s %i\n',
            co.id,
            co.name,
            <bytes>frame.f_code.co_filename,
            <bytes>frame.f_code.co_name,
            PyCode_Addr2Line  (frame.f_code, frame.f_lasti)
            )
    else:
        stdio.fprintf (
            stdio.stderr, 'No current coro. %s: %s %i\n',
            <bytes>frame.f_code.co_filename,
            <bytes>frame.f_code.co_name,
            PyCode_Addr2Line  (frame.f_code, frame.f_lasti)
            )

event_loop        = the_scheduler.event_loop
with_timeout      = the_scheduler.with_timeout
sleep_relative    = the_scheduler.sleep_relative
sleep_absolute    = the_scheduler.sleep_absolute
set_latency_warning = the_scheduler.set_latency_warning
fork              = the_scheduler.fork

set_handler       = the_poller.set_handler
event_map         = the_poller.event_map
wait_for          = the_poller.wait_for

saved_stderr      = sys.stderr
write_stderr      = sys.stderr.write
W = write_stderr
P = print_stderr

cdef int _exit
cdef object _exit_code
_exit = 0
_exit_code = 0

global _print_exit_string
_print_exit_string = True

from libc.signal cimport signal, SIGINFO, sighandler_t

# A convenient place to make absolutely sure the C random number generator is
# seeded.
IF UNAME_SYSNAME == "Linux":
    random()
ELSE:
    srandomdev()
    signal (SIGINFO, <sighandler_t>info)
