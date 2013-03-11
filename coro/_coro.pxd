# -*- Mode: Cython -*-

from cpython.ref cimport PyObject

# Only import things from libc that are very common and have unique names.
from libc.stdint cimport intptr_t, uintptr_t, uint64_t
from libc.string cimport memcpy, memset
from posix.unistd cimport off_t
from xlibc.time cimport timeval

cdef extern from "Python.h":

    ctypedef struct PyCodeObject:
        int       co_argcount
        int       co_nlocals
        int       co_stacksize
        int       co_flags
        PyObject *co_code
        PyObject *co_consts
        PyObject *co_names
        PyObject *co_varnames
        PyObject *co_freevars
        PyObject *co_cellvars
        PyObject *co_filename
        PyObject *co_name
        int       co_firstlineno
        PyObject *co_lnotab

    int PyCode_Addr2Line(PyCodeObject *, int)

cdef extern from "frameobject.h":
    ctypedef struct PyFrameObject:
        PyFrameObject *f_back
        PyCodeObject  *f_code
        PyObject *f_builtins
        PyObject *f_globals
        PyObject *f_locals
        PyObject *f_trace
        PyObject *f_exc_type
        PyObject *f_exc_value
        PyObject *f_exc_traceback
        int f_lasti
        int f_lineno
        int f_restricted
        int f_iblock
        int f_nlocals
        int f_ncells
        int f_nfreevars
        int f_stacksize

cdef enum:
    EVENT_SCALE = 16384

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

cdef int default_selfishness

cdef int live_coros

cdef public class coro [ object _coro_object, type _coro_type ]:

    """The coroutine object.

    Do not create this object directly.  Use either :func:`new` or
    :func:`spawn` to create one.
    """

    cdef machine_state state
    cdef object fun
    cdef object args, kwargs
    cdef readonly bytes name
    cdef public int id
    # XXX think about doing these as a bitfield/property
    cdef public unsigned char dead, started, scheduled
    cdef public object value
    cdef void * stack_copy
    cdef size_t stack_size
    cdef PyFrameObject * frame
    cdef void * saved_exception_data[6]
    # used only by the profiler, a call_stack object. NULL if the profiler is
    # not enabled or if this is the first call of the coroutine.
    cdef call_stack * top
    cdef int saved_recursion_depth
    cdef int selfish_acts, max_selfish_acts
    cdef bint compress, compressed
    cdef object waiting_joiners
    # Used for thread-local-storage.
    cdef dict _tdict
    cdef __create (self)
    cdef __destroy (self)
    cdef __yield (self)
    cdef __resume (self, value)
    cdef save_exception_data (self)
    cdef restore_exception_data (self)
    cdef _schedule (self, value)
    cdef _unschedule (self)
    cdef _die (self)
    cdef __interrupt (self, the_exception)
    cdef int try_selfish (self)

# choose a library for stack compression
IF COMPILE_LZ4:
    include "zstack_lz4.pxd"
ELIF COMPILE_LZO:
    include "zstack_lzo.pxd"
ELSE:
    include "zstack_zlib.pxd"

cdef public class sched [ object sched_object, type sched_type ]:
    cdef machine_state state
    # this is the stack that all coroutines run on
    cdef void * stack_base
    cdef int stack_size
    cdef public list pending, staging
    cdef public object _current
    cdef coro _last
    cdef int profiling
    cdef uint64_t latency_threshold
    cdef zstack squish
    cdef object events
    cdef _preserve_last (self)
    cdef _restore (self, coro co)
    cdef _schedule (self, coro co, object value)
    cdef _unschedule (self, coro co)
    cdef print_latency_warning (self, coro co, uint64_t delta)
    cdef sleep (self, uint64_t when)
    cdef schedule_ready_events (self, uint64_t now)
    cdef get_timeout_to_next_event (self, int default_timeout)

include "socket.pxd"
# XXX need pxd files for sync.pyx, poller.pyx, etc...
