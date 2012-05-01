=======
Sockets
=======

Most Shrapnel programs make heavy use of sockets.  The ``coro`` package
implements its own socket class, which is nearly identical to the socket class
in Python.  Indeed, if you use :func:`coro.install_thread_emulation` then the
socket class will be monkey-patched into Python's socket module.

Creating Sockets
================
Though you are free to directly instantiate the :class:`coro.sock` object, there are
a variety of functions to assist in creating socket objects with a little more clarity.

.. autofunction:: coro.tcp6_sock
.. autofunction:: coro.tcp_sock
.. autofunction:: coro.udp6_sock
.. autofunction:: coro.udp_sock
.. autofunction:: coro.unix_sock
.. autofunction:: coro.socketpair
.. autofunction:: coro.has_ipv6

Socket Classes
==============
.. autoclass:: coro.sock
.. autoclass:: coro.file_sock
.. autoclass:: coro.fd_sock

Socket Functions
================
The coro module offers the following functions related to sockets.

.. autofunction:: coro.get_live_sockets

Socket Constants
================
The following classes provide a variety of constants often used with sockets.

.. autoclass:: coro.AF
.. autoclass:: coro.PF
.. autoclass:: coro.SHUT
.. autoclass:: coro.SO
.. autoclass:: coro.SOCK
.. autoclass:: coro.SOL
