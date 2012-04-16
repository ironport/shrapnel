=========
Debugging
=========

There are a variety of features available to help with debugging in Shrapnel.

Backdoor
========

A very powerful feature of Shrapnel is the ability to access a running process
via a backdoor. You can telnet to a socket (typically a unix-domain socket)
and get a Python prompt.  At this point, you can interact with anything in
your Shrapnel process.

As an example of something you can do in the backdoor is call
:func:`coro.where_all`.  This will return a dictionary of every coroutine that
is running with a string describing the call stack of  where that coroutine is
currently blocked.

To enable the backdoor, you typically start a backdoor coroutine before starting
the event loop with the following code:

.. sourcecode:: python

    import coro.backdoor
    coro.spawn(coro.backdoor.serve)

By default this will listen on all IP's on the lowest port available from 8023
to 8033. This isn't a very safe or secure thing to do.  It's best to specify a
unix-domain socket with the ``unix_path`` parameter.  See
:func:`coro.backdoor.serve` for details.

By default, the globals available in a backdoor session is a copy of the
globals from your applications ``__main__`` module.

.. autofunction:: coro.backdoor.serve

Stderr Output
=============

Shrapnel provides some functions for printing debug information to stderr. The
:func:`coro.print_stderr` function will print a string with a timestamp and
the thread number.  The :func:`coro.write_stderr` function writes the string
verbatim with no newline.

Shrapnel keeps a reference to the "real" stderr (in ``saved_stderr``) and the
``print_stderr`` and ``write_stderr`` functions always use the real stderr
value. A particular reason for doing this is the backdoor module replaces
sys.stderr and sys.stdout, but we do not want debug output to go to the
interactive session.

.. autofunction:: coro.write_stderr
.. autofunction:: coro.print_stderr

Exceptions
==========

Tracebacks
----------

As a convenience, Shrapnel has a module for printing stack traces in a
condensed format. The ``coro.tb`` module has the :func:`coro.tb.stack_string`
function for printing the current stack, and :func:`coro.tb.traceback_string`
for getting a traceback in an exception handler.

.. autofunction:: coro.tb.stack_string
.. autofunction:: coro.tb.traceback_string

Exception Notifications
-----------------------

If an exception is raised in a coroutine and is never caught, then Shrapnel
will by default display the exception to stderr.  If you want to change this
behavior, use :func:`coro.set_exception_notifier`.

.. autofunction:: coro.set_exception_notifier

Latency
=======

Shrapnel will keep track of how long a coroutine runs before it yields.
This is helpful to track down coroutines which are running for too long, or are
potentially calling blocking calls.  Here is an example of the output that would
be sent to stderr when this happens::

    Sat Apr 14 20:55:39 2012 High Latency: (3.884s) 
        for <coro #1 name='<function my_func at 0x800fd32a8>' 
             dead=0 started=1 scheduled=0 at 0x801424720>

You can change the threshold that will trigger this warning with the
:func:`coro.set_latency_warning` function.  However, doing this to silence
warnings isn't a good idea.  It is best to fix whatever code is causing the
warnings.  You can either call :func:`coro.yield_slice` periodically to let
other coroutines run, or make sure you are not calling any blocking
operations.

.. autofunction:: coro.set_latency_warning

Functions
=========
The ``coro`` module defines the following functions:

.. autofunction:: coro.where
.. autofunction:: coro.where_all
.. autofunction:: coro.get_live_coros
