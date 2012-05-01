===========
Selfishness
===========

Shrapnel maintains a concept called "selfishness". This mechanism is used to
prevent a coroutine from yielding too often (or from running for too long).
This is currently only relevant to socket objects and socket I/O.  

Each coroutine is given a set number of "free passes" each time it tries to do
I/O on a socket.  If there is data immediately available on the socket, then
the coroutine may immediately receive that data.   If Shrapnel did not
implement any "selfishness" limits, and that coroutine is in a loop repeatedly
calling ``read`` and there is always data available to the socket, then that
coroutine would run continuously without letting its fellow coroutines a
chance to run.

By default, every coroutine has a selfishness limit of 4.  That means it is
allowed to do 4 I/O operations before it is forced to yield.  Of course, if it
attempts to do an I/O operation that would block (such as if there is no data
available on a socket), then it will yield immediately.

You can set the default selfishness limit for all new coroutines with the
:func:`coro.set_selfishness` function.  You can also change a coroutine's
limit with the :meth:`coro.coro.set_max_selfish_acts` method.

Functions
=========
The following functions are available in the ``coro`` module:

.. autofunction:: coro.set_selfishness
