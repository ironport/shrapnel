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

__profile_version__ = "$Id: //prod/main/ap/shrapnel/coro/profile.pyx#15 $"

cdef extern from "frameobject.h":

    cdef struct _frame:
        _frame * f_back
        void * f_code

cdef extern from "Python.h":
    int PyTrace_CALL, PyTrace_EXCEPTION, PyTrace_LINE, PyTrace_RETURN
    int PyTrace_C_CALL, PyTrace_C_EXCEPTION, PyTrace_C_RETURN
    ctypedef int (*Py_tracefunc)(object, _frame *, int, object)
    void PyEval_SetProfile (Py_tracefunc, object)
    void * PyCFunction_GetFunction (object ob)

include "rusage.pyx"

cdef struct call_count_element:
    void * callee
    unsigned long count

cdef class call_counts_object:

    """Track caller->callee call counts.

    This object represents the list of functions another function calls (a list
    of "callees").  There is a seperate ``call_counts_object`` create for each
    function being profiled.

    This contains an array of ``call_count_element`` structures. Each element
    contains the "callee" and the number of times it was called.
    """

    cdef call_count_element * buf
    cdef size_t num_alloced
    cdef size_t num_used

    def __dealloc__(self):
        cdef size_t i

        for i from 0 <= i < self.num_used:
            # Pyrex forces an INCREF when you cast to object,
            # so we can't use XDECREF here.
            Py_DECREF(<object>self.buf[i].callee)

        if self.buf != NULL:
            Pyrex_Free_SAFE(self.buf)

    cdef add_call_count(self, callee):
        cdef size_t i
        cdef size_t new_num_alloced

        for i from 0 <= i < self.num_used:
            if self.buf[i].callee is <void *>callee:
                self.buf[i].count = self.buf[i].count + 1
                return

        if self.num_used >= self.num_alloced:

            if self.num_alloced == 0:
                new_num_alloced = 1024
            else:
                new_num_alloced = self.num_alloced*2

            self.buf = <call_count_element *> Pyrex_Realloc_SAFE(self.buf, new_num_alloced * sizeof(call_count_element))
            self.num_alloced = new_num_alloced

        Py_INCREF(callee)
        self.buf[self.num_used].callee = <void *>callee
        self.buf[self.num_used].count = 1
        self.num_used = self.num_used + 1

    def get(self):
        """Get the callee data as a tuple.

        Each element in the tuple is a tuple ``(callee, count)`` where callee
        is a `function` object.
        """
        cdef size_t i

        result = PyTuple_New(self.num_used)
        for i from 0 <= i < self.num_used:
            PyTuple_SET_ITEM_SAFE(result, i, (<object>self.buf[i].callee, self.buf[i].count))
        return result

cdef class function:

    """Function representation for the profiler.

    This represents a Python function.  This abstracts the necessary handling
    if it is a pure-Python function or one written in C.

    It handles hashing and comparison (for putting into a dictionary) and as a
    principle function ``as_str`` for stringifying the function (also available
    as repr).
    """

    def __repr__(self):
        return self.as_str()


cdef class internal_function(function):

    """Internal function.

    This represents a special class of functions handled by the profiler.
    Currently this includes "main" (the time spent in the main thread which is
    primarily the scheduler) and "wait" (time spent waiting for I/O in kevent).
    """

    cdef object name

    def __hash__(self):
        return hash (self.name)

    def __cmp__(x, y):
        if not isinstance(x, function) or not isinstance(y, function):
            raise NotImplementedError

        if (isinstance(x, internal_function) and
            isinstance(y, internal_function)
           ):
            return cmp((<internal_function>x).name,
                       (<internal_function>y).name)

        if <void *>x < <void *>y:
            return -1
        elif <void *>x == <void *>y:
            assert False
        else:
            return 1

    def as_str(self):
        return self.name

cdef internal_function new_internal_function(name):
    cdef internal_function f

    f = internal_function()
    f.name = name
    return f

cdef class python_function(function):

    """Python function."""

    cdef object code

    def __hash__(self):
        return hash (self.code)

    def __cmp__(x, y):
        if not isinstance(x, function) or not isinstance(y, function):
            raise NotImplementedError

        if (isinstance(x, python_function) and
            isinstance(y, python_function)
           ):
            return cmp((<python_function>x).code,
                       (<python_function>y).code)

        if <void *>x < <void *>y:
            return -1
        elif <void *>x == <void *>y:
            assert False
        else:
            return 1

    def as_str(self):
        path, filename = os.path.split(self.code.co_filename)
        path, directory = os.path.split(path)
        if directory:
            module_name = '/'.join((directory, filename))
        else:
            module_name = filename

        return '%s:%s:%i' % (module_name,
                             self.code.co_name,
                             self.code.co_firstlineno
                            )

cdef python_function new_python_function(code):
    cdef python_function f

    f = python_function()
    f.code = code
    return f

cdef class c_function(function):

    """C function."""

    cdef object c_func
    cdef uintptr_t func_addr

    def __hash__(self):
        return hash (self.func_addr)

    def __cmp__(x, y):
        cdef uintptr_t a,b

        if not isinstance(x, function) or not isinstance(y, function):
            raise NotImplementedError

        if (isinstance(x, c_function) and
            isinstance(y, c_function)
           ):
            a = (<c_function>x).func_addr
            b = (<c_function>y).func_addr
        else:
            a = <uintptr_t> x
            b = <uintptr_t> y

        if <void *>a < <void *>b:
            return -1
        elif <void *>a == <void *>b:
            return 0
        else:
            return 1

    def as_str(self):
        if self.c_func.__self__ is not None:
            module = type(self.c_func.__self__).__module__
            if module is None:
                return '%s.%s' % (type(self.c_func.__self__).__name__,
                                  self.c_func.__name__
                                 )
            else:
                return '%s:%s.%s' % (module,
                                     type(self.c_func.__self__).__name__,
                                     self.c_func.__name__
                                    )
        else:
            if self.c_func.__module__ is None:
                return self.c_func.__name__
            else:
                return '%s:%s' % (self.c_func.__module__,
                                  self.c_func.__name__
                                 )

cdef c_function new_c_function(func):
    cdef c_function f

    f = c_function()
    f.c_func = func
    f.func_addr = <uintptr_t>PyCFunction_GetFunction(func)
    return f

cdef class bench:

    """Base benchmarking class.

    Bench classes are passed to the main profiler class to indicate what type
    of benchmarking you want to perform.

    This is a simple benchmarker that uses x86 TSC ticks as a measurement
    of time spent in a function.

    A bench instance is created for each unique function.  Additional bench
    objects are created for the main thread (the scheduler) and the poller.

    A special bench object, the "counter", is created in the profiler, and is
    the baseline that all other bench objects are related to.  The mark method
    is only called on the "counter" object.  All other bench objects (those for
    all the functions) are implicitly modified by the mark method.  The value
    of the bench object depends whether or not it is the "counter".  The
    "counter" object contains the absolute value of what is being monitored.
    For this discussion, we will assume TSC, but this is applicable to the
    rusage benchmarker as well.

    The "counter" ticks value contains the current TSC value whenever ``mark``
    is called.  All other bench objects contain cumulative ticks which is
    computed by comparing the current TSC value with the value in the "counter"
    object.  One way to think about this is that the "counter" object contains
    the current wall-clock time, and the other objects have the total time
    spent in that object.

    :IVariables:
        - `ticks`: The total number of ticks spent in the function (for the
          "counter" object, contains the current processor TSC value).
        - `aggregate_ticks`: The total number of ticks spent in the function
          including the functions it calls.  Not used by the "counter" object.
        - `calls`: Number of times this element/function has been called. Not
          used by the "counter" object.
    """

    cdef public uint64_t ticks
    cdef public uint64_t aggregate_ticks
    cdef public uint64_t calls

    def __init__ (self):
        self.ticks = 0
        self.aggregate_ticks = 0
        self.calls = 0

    cdef mark (self, bench other):
        """Mark time spent in an object.

        This allows you to charge time spent in a bench object. This is only
        called on the singleton "counter" object in the profiler.

        This updates both regular and aggregate time.

        :Parameters:
            - `other`: The bench object to modify the delta time spent in it.
              This is done by adding the time since the last time ``mark`` was
              called.
        """
        cdef uint64_t now
        cdef uint64_t diff
        now = c_rdtsc()
        diff = now - self.ticks
        other.ticks = other.ticks + diff
        other.aggregate_ticks = other.aggregate_ticks + diff
        self.ticks = now

    cdef mark_reset (self):
        """Reset the marker to the current time.

        Used only on the "counter" object.
        """
        self.ticks = c_rdtsc()

    cdef add (self, bench other):
        """Add cumulative time from another bench object to this bench object.

        This adds both regular and aggregate time.

        :Parameters:
            - `other`: The other bench object to add to this object.
        """
        self.ticks = self.ticks + other.ticks
        self.aggregate_ticks = self.aggregate_ticks + other.aggregate_ticks

    cdef add_aggregate (self, bench other):
        """Add only the aggregate time from the other bench object to this
        bench object.

        :Parameters:
            - `other`: The other bench object to add to this object.
        """
        self.aggregate_ticks = self.aggregate_ticks + other.aggregate_ticks

    def get_data(self):
        """Get the data for this bench object.

        :Return:
            Returns a tuple ``(calls, regular_time, aggregate_time)``. The
            values ``regular_time`` and ``aggregate_time`` are both tuples of
            values.  Call the ``get_headings`` method for a description of each
            element in the tuple.
        """
        return (self.calls, (self.ticks,), (self.aggregate_ticks,))

    def get_headings(self):
        """Get a description of the data elements.

        :Return:
            Returns a tuple of strings describing the data elements from
            ``get_data``.
        """
        return ('ticks',)

cdef class rusage_bench (bench):

    """Subclass of bench object that tracks rusage data.

    :IVariables:
        - `ru`: Rusage object value.
        - `aggregate_ru`: Aggregate (including callees) data.
    """

    cdef readonly rusage ru
    cdef readonly rusage aggregate_ru

    def __init__ (self):
        self.ru = rusage()
        self.aggregate_ru = rusage()

    def __repr__ (self):
        return self.ru.__repr__()

    cdef mark (self, bench _other):
        cdef rusage now
        cdef rusage_bench other
        cdef rusage diff
        other = _other
        now = rusage()
        now.get()
        bench.mark (self, _other)
        diff = now - self.ru
        other.ru = other.ru + diff
        other.aggregate_ru = other.aggregate_ru + diff
        self.ru.set (now)

    cdef mark_reset (self):
        self.ru = rusage()
        self.ru.get()
        bench.mark_reset(self)

    cdef add (self, bench other):
        bench.add(self, other)
        self.ru = self.ru + (<rusage_bench>other).ru
        self.aggregate_ru = self.aggregate_ru + (<rusage_bench>other).aggregate_ru

    cdef add_aggregate (self, bench other):
        bench.add_aggregate(self, other)
        self.aggregate_ru = self.aggregate_ru + (<rusage_bench>other).aggregate_ru

    def get_data(self):
        cdef _rusage * r
        cdef _rusage * ar

        r = &self.ru.r
        ar = &self.aggregate_ru.r

        return (self.calls,
                (self.ticks,
                 r.ru_utime.tv_sec + r.ru_utime.tv_usec / 1000000.0,
                 r.ru_stime.tv_sec + r.ru_stime.tv_usec / 1000000.0,
                 r.ru_maxrss,
                 r.ru_ixrss,
                 r.ru_idrss,
                 r.ru_isrss,
                 r.ru_minflt,
                 r.ru_majflt,
                 r.ru_nswap,
                 r.ru_inblock,
                 r.ru_oublock,
                 r.ru_msgsnd,
                 r.ru_msgrcv,
                 r.ru_nsignals,
                 r.ru_nvcsw,
                 r.ru_nivcsw,
                ),
                (self.aggregate_ticks,
                 ar.ru_utime.tv_sec + ar.ru_utime.tv_usec / 1000000.0,
                 ar.ru_stime.tv_sec + ar.ru_stime.tv_usec / 1000000.0,
                 ar.ru_maxrss,
                 ar.ru_ixrss,
                 ar.ru_idrss,
                 ar.ru_isrss,
                 ar.ru_minflt,
                 ar.ru_majflt,
                 ar.ru_nswap,
                 ar.ru_inblock,
                 ar.ru_oublock,
                 ar.ru_msgsnd,
                 ar.ru_msgrcv,
                 ar.ru_nsignals,
                 ar.ru_nvcsw,
                 ar.ru_nivcsw,
                )
               )

    def get_headings(self):
        return ('ticks',
                'utime',
                'stime',
                'maxrss',
                'ixrss',
                'idrss',
                'isrss',
                'minflt',
                'majflt',
                'nswap',
                'inblock',
                'oublock',
                'msgsnd',
                'msgrcv',
                'nsignals',
                'nvcsw',
                'nivcsq')


cdef class _profiler:

    """The profiler object.

    This object manages profiling in the system.

    Typically, you enable profiling with the ``start`` method, and stop it with
    the ``stop`` method. The profile data can be found in the ``charges``
    and ``call_counts`` instance variables.

    The profiler tracks aggregate and non-aggregate time (aggregate being time
    spent in the function plus all the functions it calls).  It also tracks how
    many times a function is called, and how many times it makes a call to a
    particular function.

    The `bench` and `call_counts_object` docstrings describe a little bit about
    how the profiler works.  (An important element to understand is that the
    global "counter" bench object is unique and is different than other bench
    objects, and is the baseline from which all values are computed.)

    For each coroutine, there is a linked-list of the call stack for that
    coroutine (a ``call_stack`` structure assigned to the ``top`` value of the
    coroutine).  Each element on the call stack has a seperate bench object
    that is used for tracking time spent in that function at that level of the
    call stack for that coroutine.

    There is a global "charges" dictionary which tracks time spent in each
    function in the program.

    When calling a new function, the time spent in the previous function (as
    accumulated in the "counter") is added to its bench object on the call
    stack.  A new bench object is then created and pushed onto the call stack.

    When returning from a function, the bench object from the call stack is
    added to the global "charges" dictionary for that function, as well as
    updating call counts.  Additionally, the caller's bench object from the
    call stack has the aggregate time from the callee added to it.

    When yielding, the time spent so-far is added to the top of the call stack
    of the current coroutine (and thus resets the "counter" object to start the
    timer for the next coroutine to be resumed).

    :IVariables:
        - `counter`: The base `bench` class instance that is used to provide a
          baseline that all other bench instance deltas are computed from.
        - `main_bench`: Bench instance tracking the time spent in the main
          thread (the scheduler).
        - `wait_bench`: Bench instance tracking the time spent waiting in the
          poller (kqueue).
        - `charges`: The profile data as a dictionary.  The key is a `function`
          object, the value is a bench instance.
        - `bench_class`: The bench class object the user passed in to indicate
          the type of benchmarking to perform.
        - `start_ticks`: TSC value when profiling started.
        - `call_counts`: A dictionary of call counts.  The key is the caller
          `function` object.  The value is a `call_counts_object` which is
          essentially an array of callees (as `function` objects) and the
          number of times the function has called each of those callees.
        - `func_cache`: A cache of `function` objects.  The key is a pointer to
          the actual code object (or the C pointer for C functions) and the
          value is a `function` object.
    """

    cdef bench counter, main_bench, wait_bench
    cdef public dict charges, call_counts, func_cache
    cdef public object bench_class
    cdef uint64_t start_ticks

    def __init__ (self, bench_class):
        self.charges = {}
        self.call_counts = {}
        self.func_cache = {}
        self.bench_class = bench_class
        self.counter = bench_class()
        self.main_bench = bench_class()
        self.wait_bench = bench_class()
        self.charges[new_internal_function('<main>')] = self.main_bench
        self.charges[new_internal_function('<wait>')] = self.wait_bench

    cdef call_stack * charge_enter (self, function func, call_stack * top) except NULL:
        """Indicate a function is being called.

        :Parameters:
            - `func`: The function being called.
            - `top`: The current call stack for the current coroutine.

        :Return:
            Returns the new pointer for the coroutine call stack.
        """
        cdef call_stack * link
        cdef bench b

        if top:
            self.counter.mark(<bench>top.b)
        else:
            # First call for this coroutine.
            self.counter.mark_reset()

        link = <call_stack *>Pyrex_Malloc_SAFE (sizeof (call_stack))
        Py_INCREF(func)
        link.func = <void *>func
        b = self.bench_class()
        Py_INCREF(b)
        link.b = <void *>b
        link.next = top
        return link

    cdef call_stack * charge_exit (self, call_stack * top) except? NULL:
        """Indicate a function has returned.

        :Parameters:
            - `top`: The current call stack for the current coroutine.  The
              value this points to is the function that is returning.

        :Return:
            Returns the new pointer for the coroutine call stack. May return
            NULL if the call stack is now empty (either the coroutine is
            exiting or it has reached the call level when profiling started).
        """
        cdef bench b
        cdef call_stack * link
        cdef call_counts_object cc

        self.counter.mark(<bench>top.b)

        if self.charges.has_key (<function>top.func):
            b = self.charges[<function>top.func]
        else:
            b = self.bench_class()
            self.charges[<function>top.func] = b

        b.add (<bench>top.b)
        b.calls = b.calls + 1

        # This will be NULL if it's the first call for this coroutine.
        if top.next:
            cc = self._get_call_counts(<function> top.next.func)
            cc.add_call_count(<function>top.func)
            (<bench>top.next.b).add_aggregate(<bench>top.b)

        link = top.next
        Py_DECREF(<object>top.func)
        Py_DECREF(<object>top.b)
        Pyrex_Free_SAFE (top)
        return link

    cdef charge_yield (self, call_stack * top):
        """Indicate the current coroutine is yielding.

        :Parameters:
            - `top`: The current call stack for the current coroutine.
        """
        self.counter.mark(<bench>top.b)

    cdef call_counts_object _get_call_counts (self, object func):
        """Get a call counts object for a particular function.

        This will create a new call counts object if one does not exist, yet.

        :Parameters:
            - `func`: The `function` object to get.

        :Return:
            Returns a `call_counts_object`.
        """
        if not self.call_counts.has_key (func):
            cc = call_counts_object()
            self.call_counts[func] = cc
            return cc
        else:
            return self.call_counts[func]

    cdef charge_main (self):
        """Charge time to the main thread."""
        self.counter.mark (self.main_bench)

    cdef charge_wait (self):
        """Charge time to the "waiting" bench object (time spent in kqueue)."""
        self.counter.mark (self.wait_bench)

    cdef _get_python_function (self, code):
        """Get a python function from the cache.

        This creates a new `function` object if one is not already in the cache.

        :Parameters:
            - `code`: The Python code object.

        :Return:
            Returns a `python_function` object.
        """
        code_ptr = <intptr_t><void *> code
        if self.func_cache.has_key (code_ptr):
            return self.func_cache[code_ptr]
        else:
            func = new_python_function(code)
            self.func_cache[code_ptr] = func
            return func

    cdef _get_c_function (self, c_func):
        """Get a C function from the cache.

        This creates a new `function` object if one is not already in the cache.

        :Parameters:
            - `c_func`: A pointer to the C function being called.

        :Return:
            Returns a `c_function` object.
        """
        c_func_ptr = <intptr_t>PyCFunction_GetFunction(c_func)
        if self.func_cache.has_key (c_func_ptr):
            return self.func_cache[c_func_ptr]
        else:
            func = new_c_function(c_func)
            self.func_cache[c_func_ptr] = func
            return func

    cdef int dispatch (self, _frame * frame, int what, void * arg) except -1:
        """The main profiler dispatch called by Python."""
        cdef call_stack * top
        cdef call_stack * link
        # top may be NULL when a coro first starts.
        top = (<coro>the_scheduler._current).top
        if what == PyTrace_CALL:
            func = self._get_python_function(<object>frame.f_code)
            link = self.charge_enter(func, top)
            (<coro>the_scheduler._current).top = link
        elif what == PyTrace_RETURN:
            # When profiling is turned on, we'll get a RETURN
            # with no matching CALL.  Ignore it.
            if top:
                link = self.charge_exit(top)
                (<coro>the_scheduler._current).top = link
        elif what == PyTrace_C_CALL:
            func = self._get_c_function (<object>arg)
            link = self.charge_enter(func, top)
            (<coro>the_scheduler._current).top = link
        elif what == PyTrace_C_RETURN or what == PyTrace_C_EXCEPTION:
            # When profiling is turned on, we'll get a RETURN
            # with no matching CALL.  Ignore it.
            if top:
                link = self.charge_exit(top)
                (<coro>the_scheduler._current).top = link

    def start (self):
        """Start the profiler."""
        cdef uint64_t now
        now = c_rdtsc()
        self.counter.ticks = now
        self.start_ticks = now
        the_scheduler.profiling = 1
        PyEval_SetProfile (<Py_tracefunc>profiler_dispatch, self)

    def stop (self):
        """Stop the profiler.

        :Return:
            Returns the total TSC ticks spent during the profile session.
        """
        global the_profiler
        cdef uint64_t now
        now = c_rdtsc()
        the_scheduler.profiling = 0
        PyEval_SetProfile (NULL, None)
        the_profiler = None
        #W ('start=%r stop=%r\n' % (self.start_ticks, now))
        return now - self.start_ticks

cdef int profiler_dispatch (_profiler self, _frame * frame, int what, void * arg) except -1:
    return self.dispatch (frame, what, arg)

# This is global so that the scheduler can access it.
cdef public _profiler the_profiler
the_profiler = None

def new_profiler (bench_class):
    global the_profiler

    if the_scheduler.profiling:
        raise SystemError('Another profiler is already active.')
    the_profiler = _profiler(bench_class)
    return the_profiler

def get_the_profiler():
    return the_profiler
