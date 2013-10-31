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

# $Header: //prod/main/ap/shrapnel/coro/emulation/threading.py#2 $

"""Emulation of the Python ``threading`` module.

It is best to reference the Python documentation for the ``threading`` module,
but this module will provide some cursory information.
"""

import sys

import coro
import coro.emulation.thread

_trace_hook = None

def settrace(func):
    global _trace_hook
    _trace_hook = func

##############################################################################
# Locking
##############################################################################
Lock = coro.emulation.thread.LockType
RLock = coro.emulation.thread.LockType

class Condition(object):

    def __init__(self, lock=None):
        if lock is None:
            lock = RLock()
        self.__lock = lock
        self.acquire = lock.acquire
        self.release = lock.release
        self.__cv = coro.condition_variable()

    def __enter__(self):
        return self.__lock.__enter__()

    def __exit__(self, *args):
        return self.__lock.__exit(*args)

    def wait(self, timeout=None):
        # This API is a little on the bizarre side.  Probably due to some
        # preemption race conditions we don't have in shrapnel.
        # XXX: This is not emulating the "save/restore" logic of the Python
        # version.  We could probably do that without too much difficulty
        # if self.lock == RLock.
        self.__lock.release()
        try:
            if timeout is None:
                self.__cv.wait()
            else:
                try:
                    coro.with_timeout(timeout, self.__cv.wait)
                except coro.TimeoutError:
                    # Seems dumb not to return an indication it timed out.
                    pass
        finally:
            self.__lock.acquire()

    def notify(self):
        self.__cv.wake_one()

    def notify_all(self):
        self.__cv.wake_all()

    notifyAll = notify_all


class Semaphore(object):

    def __init__(self, value=1):
        self._sem = coro.semaphore(value)

    def acquire(self, blocking=True):
        if blocking:
            self._sem.acquire(1)
            return True
        else:
            if len(self._sem) < 1:
                return False
            else:
                self._sem.acquire(1)
                return True

    def release(self):
        self._sem.release(1)

    __enter__ = acquire
    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

class BoundedSemaphore(Semaphore):

    def __init__(self, value=1):
        Semaphore.__init__(self, value)
        self._initial_value = value

    def release(self):
        if len(self._sem) >= self._initial_value:
            raise ValueError('Semaphore released too many times.')
        return Semaphore.release(self)

class Event(object):

    def __init__(self):
        self.__cond = coro.condition_variable()
        self.__flag = False

    def is_set(self):
        return self.__flag
    isSet = is_set

    def set(self):
        self.__flag = True
        self.__cond.wake_all()

    def clear(self):
        self.__flag = False

    def wait(self, timeout=None):
        if not self.__flag:
            if timeout is None:
                self.__cond.wait()
            else:
                try:
                    coro.with_timeout(timeout, self.__cond.wait)
                except coro.TimeoutError:
                    pass

##############################################################################
# Thread Object
##############################################################################

_active_threads = {}

class Thread(object):

    """Shrapnel emulation of Python Thread.

    XXX: Daemonic threads are not supported (yet).

    """

    daemon = False

    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None, _co=None):
        if group is not None:
            raise AssertionError('group must be None for now')
        if kwargs is None:
            kwargs = {}
        self.__target = target
        self.__args = args
        self.__kwargs = kwargs
        if _co is None:
            self.__co = coro.new(self.__bootstrap)
        else:
            self.__co = _co
        self.ident = self.__co.id
        if name:
            self.__co.set_name(name)

    def __bootstrap(self):
        _active_threads[self.__co.id] = self
        if _trace_hook:
            sys.settrace(_trace_hook)
        try:
            self.run()
        finally:
            del _active_threads[self.__co.id]

    def start(self):
        self.__co.start()

    def run(self):
        try:
            if self.__target:
                self.__target(*self.__args, **self.__kwargs)
        finally:
            del self.__target, self.__args, self.__kwargs

    def join(self, timeout=None):
        if timeout is None:
            self.__co.join()
        else:
            try:
                coro.with_timeout(timeout, self.__co.join)
            except coro.TimeoutError:
                pass

    def is_alive(self):
        return not self.__co.dead
    isAlive = is_alive

    @property
    def name(self):
        return self.__co.name

    @name.setter
    def name(self, name):
        self.__co.set_name(name)

    def getName(self):
        return self.name

    def setName(self, name):
        self.name = name

    def isDaemon(self):
        return self.daemon

    def setDaemon(self, daemonic):
        self.daemon = daemonic

##############################################################################
# Thread-Local Storage
##############################################################################
local = coro.ThreadLocal

##############################################################################
# Timer
##############################################################################

class Timer(Thread):

    def __init__(self, interval, function, args=(), kwargs={}):
        Thread.__init__(self)
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.finished = Event()

    def cancel(self):
        self.finished.set()

    def run(self):
        self.finished.wait(self.interval)
        if not self.finished.is_set():
            self.function(*self.args, **self.kwargs)
        self.finished.set()

##############################################################################
# Global API
##############################################################################
def current_thread():
    # XXX: Probably doesn't work in "main" thread.
    try:
        return _active_threads[coro.current().id]
    except KeyError:
        # Thread was probably not started by threading but by coro instead.
        # Try creating a wrapper.
        # XXX: This does not install into _active_threads because there isn't
        # a safe way to remove it when the thread dies.  Access a global from
        # __del__ isn't safe.
        return Thread(_co=coro.current())

def active_count():
    return coro.get_live_coros()
activeCount = active_count

def enumerate():
    return _active_threads.values()

##############################################################################
# Not Implemented
##############################################################################

# stack_size
# setprofile
