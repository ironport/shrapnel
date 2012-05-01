=========
Emulation
=========

Because Shrapnel is essentially its own threading system, code written with
the intention of using Python's standard threads will not work.  Things like
Python's socket class will block and hang the entire program.  To solve this
problem, Shrapnel includes some code that will monkeypatch some of Python's
standard classes to work with Shrapnel.  You must manually enable this
behavior by calling :func:`coro.install_thread_emulation`.

.. autofunction:: coro.install_thread_emulation
