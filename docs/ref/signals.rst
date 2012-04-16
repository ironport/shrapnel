=======
Signals
=======

Shrapnel provides a way to handle signals.  Youn can register a function to
receive signals with :func:`coro.signal_handler.register`.

By default when you start the event loop, two signal handlers are installed
(for SIGTERM and SIGINT). The default signal handler will exit the event loop.
You can change this behavior by setting ``coro.install_signal_handlers`` to False
before starting the event loop.

Additionally, there is a signal handler installed for SIGINFO.  It prints the
name of the coroutine that is currently running.  On a typical terminal, you
can trigger this with CTRL-T.

.. autofunction:: coro.signal_handler.register
