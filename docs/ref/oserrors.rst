========
OSErrors
========

As a convenience, Shrapnel wraps all OSError exceptions that it raises with a
subclass that is specific to the errno code. For example, an OSError with an
errno of ENOENT will be raised as the ENOENT exception.  All exceptions derive
from OSError, so it is compatible with regular OSError handling.

All of the exceptions are defined in the ``coro.oserrors`` module.

For example, instead of doing this:

.. sourcecode:: python

    try:
        data = sock.recv(1024)
    except OSError, e:
        if e.errno == errno.ECONNRESET:
            # Handle connection reset.
        else:
            # Handle other unknown error.

You can do this:

.. sourcecode:: python

    try:
        data = sock.recv(1024):
    except ECONNRESET:
        # Handle connection reset.
