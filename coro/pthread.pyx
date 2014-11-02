# -*- Mode: Cython; indent-tabs-mode: nil -*-

# ok, how about a set of pthreads each attached to
#   a coro thread?  When the pthread finishes its work,
#   it schedules the coro thread?

# let's try to trace through how it might work.
#
# the coro thread wakes up (perhaps on a cv), with
#   some work to do.  This includes some data that can
#   be safely handed off to the pthread.
# it places the data in a known place, and signals the
#   pthread to wake up.

import coro

cdef extern from "pthread.h" nogil:

    ctypedef struct pthread_cond_t:
        pass
    ctypedef struct pthread_attr_t:
        pass
    ctypedef struct pthread_condattr_t:
        pass
    ctypedef struct pthread_mutex_t:
        pass
    ctypedef struct pthread_mutexattr_t:
        pass
    
    ctypedef struct pthread_t:
        pass

    int pthread_cond_wait (pthread_cond_t * cond, pthread_mutex_t * mutex)
    int pthread_cond_init (pthread_cond_t * cond, pthread_condattr_t * attr)
    int pthread_cond_signal (pthread_cond_t *cond)
    int pthread_mutex_init (pthread_mutex_t * mutex, const pthread_mutexattr_t * attr)
    int pthread_mutex_lock (pthread_mutex_t *mutex)
    int pthread_mutex_unlock (pthread_mutex_t *mutex)
    int pthread_create (pthread_t * thread, const pthread_attr_t * attr, void *(*start_routine)(void *), void * arg)

    void pthread_exit (void * value_ptr)

from posix.unistd cimport sleep
from libc.stdio cimport stdout, puts, stderr, fprintf
from cpython.ref cimport PyObject, Py_INCREF, Py_DECREF

ctypedef struct funcall_t:
    int (*fun)(void * args) nogil
    int nargs
    void * args[10]
    int result

ctypedef struct worker_state_t:
    PyObject * co
    pthread_t thread
    pthread_mutex_t mutex
    pthread_cond_t cv
    int exit_flag
    funcall_t funcall

cdef extern:
    void __schedule (void * co, int arg) nogil

cdef void * worker (void * arg) nogil:
    cdef worker_state_t * state = <worker_state_t *> arg
    cdef funcall_t * funcall
    cdef int result
    pthread_mutex_lock (&state[0].mutex)
    try:
        while not state.exit_flag:
            pthread_cond_wait (&state[0].cv, &state[0].mutex)
            result = state[0].funcall.fun (state[0].funcall.args)
            __schedule (state.co, result)
        pthread_exit (NULL)
    finally:
        pthread_mutex_unlock (&state[0].mutex)

cdef class c_function:
    def __init__ (self):
        pass

cdef check (int n):
    if n != 0:
        raise OSError

cdef int sleep_wrapper (void * args) nogil:
    cdef int secs = (<int*>args)[0]
    cdef int result = sleep (secs)
    return result

cdef class pthread:
    cdef worker_state_t state

    def __init__ (self):
        check (pthread_mutex_init (&self.state.mutex, NULL))
        check (pthread_cond_init (&self.state.cv, NULL))
        check (pthread_create (&self.state.thread, NULL, worker, &self.state))
        self.state.exit_flag = False
        # pthread_detach?
        
    cdef _go (self):
        cdef object me = coro.current()
        self.state.co = <PyObject*>me
        # wake the worker
        pthread_mutex_lock (&self.state.mutex)
        pthread_cond_signal (&self.state.cv)
        pthread_mutex_unlock (&self.state.mutex)
        me._yield()

    def sleep (self, int secs):
        self.state.funcall.fun = sleep_wrapper
        self.state.funcall.args[0] = <void*>secs
        self._go()

    def set_exit (self):
        self.state.exit_flag = True
