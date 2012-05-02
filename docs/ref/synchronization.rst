===============
Synchronization
===============
You typically do not need to use synchronization primitives with Shrapnel
because coroutines are cooperative. However, there are situations where they
can be useful.  For example, if you manipulate multiple shared data structures
that need to remain consistent, and you have potentially context-switch calls
interspersed (such as socket I/O).

Synchronization Classes
=======================
.. autoclass:: coro.condition_variable
.. autoclass:: coro.fifo
.. autoclass:: coro.inverted_semaphore
.. autoclass:: coro.LockError
.. autoclass:: coro.mutex
.. autoclass:: coro.semaphore
