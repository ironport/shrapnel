==========
Coroutines
==========

The central concept of Shrapnel is the coroutine.  You can think of a coroutine
like it is a thread.  When it runs out of work to do, it yields and allows other
coroutines to run.  Scheduling of coroutines is handled by the scheduler which
runs an "event loop".

Event Loop
==========

The event loop is a loop that runs forever until the program ends.  Every
Shrapnel program needs to start the event loop as one of the first things it
does.  A typical example would be::

    import coro

    def main():
        print 'Hello world!'
        # This will cause the process to exit.
        coro.set_exit(0)

    if __name__ == '__main__':
    	coro.spawn(main)
    	coro.event_loop()

Coroutines
========== 

Every coroutine thread is created with either the :func:`new` function (which
does NOT automatically start the thread) or the :func:`spawn` function (which
DOES automatically start it).

Every thread has a unique numeric ID.  You may also set the name of the thread
when you create it.

.. autoclass:: coro.coro

Timeouts
========
The shrapnel timeout facility allows you to execute a function which will be
interrupted if it does not finish within a specified period of time.  The
:class:`TimeoutError` exception will be raised if the timeout expires.  See the
:func:`with_timeout` docstring for more detail.

If the event loop is not running (such as in a non-coro process), a custom
version of `with_timeout` is installed that will operate using SIGALRM so that
you may use `with_timeout` in code that needs to run in non-coro processes
(though this is not recommended and should be avoided if possible).

.. autofunction:: coro.with_timeout

Parallel Execution
==================
XXX

.. autofunction:: coro.in_parallel
.. autoexception:: coro.InParallelError

Thread Local Storage
====================
There is a thread-local storage interface available for storing global data that
is thread-specific.  You instantiate a :class:`ThreadLocal` instance and you can
assign attributes to it that will be specific to that thread.  From a design
perspective, it is generally discouraged to use thread-local storage.  But
nonetheless, it can be useful at times.

.. autoclass:: coro.ThreadLocal

Functions
=========
The coro module defines the following functions:

.. autofunction:: coro.get_thread_by_id
.. autofunction:: coro.coro_is_running
.. autofunction:: coro.event_loop
.. autofunction:: coro.new
.. autofunction:: coro.spawn
.. autofunction:: coro.waitpid
.. autofunction:: coro.yield_slice
.. autofunction:: coro.schedule
.. autofunction:: coro.current
.. autofunction:: coro.set_exit
.. autofunction:: coro.set_print_exit_string
.. autofunction:: coro.sleep_absolute
.. autofunction:: coro.sleep_relative

Variables
=========
.. py:data:: coro.all_threads

	A dictionary of all live coroutine objects.  The key is the coroutine ID,
	and the value is the coroutine object.

Exceptions
==========
The coro module defines the following exceptions:

.. autoexception:: coro.ScheduleError
.. autoexception:: coro.DeadCoroutine
.. autoexception:: coro.ClosedError
.. autoexception:: coro.NotStartedError
.. autoexception:: coro.TimeoutError
.. autoexception:: coro.SimultaneousError
.. autoexception:: coro.Shutdown
.. autoexception:: coro.WakeUp
