======
Clocks
======

Shrapnel needs to keep track of time to manage scheduling of sleeps and
timeouts.  Because Shrapnel is intended to support thousands of coroutines,
and each coroutine may be making many timeout calls per second, Shrapnel needs
to use a timing facility that is relatively high performance.  It also needs
one that is monotonic, so it does not need to deal with system clock changes.

The ``clocks`` subpackage is intended to provide a variety of different time
facilities. Currently it only supports using the x86 TSC timer.  This is a
timer built in to the CPU, and thus is very fast.

TSC Time
========
Support for TSC time is implemented in the ``coro.clocks.tsc_time`` module.

.. automodule:: coro.clocks.tsc_time
