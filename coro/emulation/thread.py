# Copyright (c) 2002-2011 IronPort Systems and Cisco Systems
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# $Header: //prod/main/ap/shrapnel/coro/emulation/thread.py#1 $

"""Emulation of the Python ``thread`` module.

It is best to reference the Python documentation for the ``thread`` module, but
this module will provide some cursory information.
"""

import coro

class error(Exception):

    def __init__(self, *args):
        self.args = args

def start_new_thread(function, args, kwargs={}):
    """Create a new thread.

    :Parameters:
        - `function`: The function to call in the new thread.
        - `args`: Arguments to call the function with.
        - `kwargs`: Keyword arguments to call the function with.

    :Return:
        Returns the "id" of the thread.
    """
    return coro.spawn(function, *args, **kwargs).id

class LockType(object):

    """A simple mutex lock.

    XXX NOTE: This does not behave the same way as Python's lock does. It
    behaves like the threading.RLock object.  Shrapnel does not have a
    non-reentrant lock.
    """

    def __init__(self):
        self._lock = coro.mutex()

    def acquire(self, waitflag=None):
        """Acquire the lock.

        :Parameters:
            - `waitflag`: If zero, will immediately return with False if it is
              unable to acquire the lock, True if it did.  Otherwise, this will
              block until the lock can be acquired.

        :Return:
            Returns True if it was acquired, False if not (only when waitflag
            is nonzero).
        """
        if waitflag is None or waitflag:
            self._lock.lock()
            return True
        else:
            return not self._lock.trylock()

    def release(self):
        """Release the lock.

        XXX: NOTE: This deviates from the standard Python version. This will
        fail if you try to release a lock acquired by another thread.  Standard
        Python threads allow you to do that.
        """
        self._lock.unlock()

    def locked(self):
        """Determine if the lock is locked.

        :Return:
            Returns a boolean value, True if it is locked.
        """
        return self._lock.locked()

    __enter__ = acquire

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

def interrupt_main():
    """Shrapnel does not have a concept of a "main" thread.  As a compromise,
    this will exit the process with code 1.
    """
    coro.set_exit(1)

def exit():
    """Exit the current thread by raising the `coro.Shutdown` exception."""
    raise coro.Shutdown

def allocate_lock():
    """Create a new lock.

    The lock is initially unlocked.

    :Return:
        Returns a `LockType` instance.
    """
    return LockType()

def get_ident():
    """Returns the "id" of the current thread."""
    return coro.current().id

def stack_size(size=None):
    """This method does nothing, because coro uses a dynamic stack."""
    return
