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

# -*- Mode: Pyrex -*-
# $Header: //prod/main/ap/shrapnel/coro/sync.pyx#29 $

__sync_version__ = "$Id: //prod/main/ap/shrapnel/coro/sync.pyx#29 $"

# Note: this file is included by <coro.pyx>

# ================================================================================
#                      synchronization primitives
# ================================================================================

# XXX things to think about.
#  * instead of using remove_fast(), store a flag (in the node?)
#    that says whether it's valid or not?
#  * again, think very carefully about exactly what to do in case
#    of ScheduleError, for each and every data structure.
#    In general, the level of safety is high, because the except:
#      clauses always use remove_fast(), which never throws an exception.
#    When most of this code was originally written, 'ScheduleError' was
#      thrown only when a coroutine was dead.  Nowadays, there are several
#      other types of ScheduleErrors.  Think about them all.

# condition_variable, mutex, semaphore, inverted_semaphore, rw_lock.

class LockError (Exception):
    pass

# ===========================================================================
#                              Semaphore
# ===========================================================================

cdef class semaphore:

    """
    A semaphore is a locking primitive that corresponds with a set of
    resources.  A semphore is essentially a counter.  Whenever a resource is
    aquired, the count is lowered.  If the count goes below 0, then it blocks
    until it goes above zero.  Once you are done with a resource, you raise
    the counter.

    :param value: The value to start the semaphore with (an integer).

    :ivar avail: The current value of the semaphore.  Also available via __int__.
    :ivar _waiting: A fifo of ``(value, co)`` tuples of coroutines waiting
          for the semaphore. ``value`` is the value being requested, and ``co``
          is the coroutine object. (C only.)
    """

    cdef public avail
    cdef readonly _fifo _waiting

    def __init__ (self, value):
        self.avail = value
        # fifo of waiting coroutines [(n0, co0), (n1, co1), ...]
        self._waiting = _fifo()

    def __int__ (self):
        return self.avail

    def acquire(self, int value):
        """Acquire a number of resource elements from the semaphore.

        This will subtract the given value from the semaphore.  This will block
        if the requested number of resource elements are not available (if the
        value would go negative).

        :param value: The number of resource elements.
        """
        cdef coro me
        me = the_scheduler._current
        pair = (value, me)
        # Loop because it is possible for multiple waiting threads to get
        # scheduled making self.avail go negative if release is called multiple
        # times (see comments about temp_avail below).
        while self.avail < value:
            # Not enough available, go to sleep.
            self._waiting.push (pair)
            try:
                me.__yield ()
            except:
                # Note that in the case where someone called release *after*
                # we've been interrupted, then this coro will have already been
                # removed from the list.  remove_fast will not raise an
                # exception if it can't find the entry, so we are ok.
                self._waiting._remove_fast (pair)
                # If release was called *before* we were interrupted, then we
                # need to check if any threads waiting can take our spot.
                self.release(0)
                raise
        self.avail = self.avail - value

    def release(self, int value):
        """Release a number of resource elements.

        :param value: The number of resource elements to release (add to the
              sempahore).
        """
        cdef coro ci

        # We use "temp_avail" instead of modifying the real thing because it
        # would cause a problem if a thread blocked in acquire() was
        # interrupted.  The "acquiring" thread can't tell if it was interrupted
        # before or after a "releasing" thread has scheduled it.  If we had
        # modified self.avail, then if it was interrupted *before* we scheduled
        # it, then it shouldn't call release.  If it was interrupted *after* we
        # scheduled it, then it would have to call release to re-increment it.
        # Since it can't tell the difference between "before" or "after", we
        # don't modify it here.
        #
        # This causes a subtle issue where it is possible for multiple
        # acquiring threads to get woken up too eagerly if release is called
        # multiple times.  This isn't too much of a big deal because the
        # acquiring threads will loop through the while loop, notice that
        # self.avail is not big enough, and immediately go back to sleep.
        self.avail = self.avail + value
        if self._waiting.size and self.avail > 0:
            temp_avail = self.avail
            while self._waiting.size:
                vi, ci = self._waiting._top()
                if vi <= temp_avail:
                    try:
                        ci._schedule (None)
                    except ScheduleError:
                        # we don't care if we can't schedule it.
                        # it's going to run regardless.
                        pass
                    else:
                        # In the case of ScheduleError, the other thread has
                        # most likely been interrupted.  We don't want to
                        # modify temp_avail in this case because we're certain
                        # the other thread won't be acquiring anything, so
                        # pretend it doesn't exist.
                        temp_avail = temp_avail - vi
                    # Always pop it from the list, even if there was a
                    # ScheduleError.  We don't want to make other threads
                    # attempt to schedule it because it can cause a noticeable
                    # performance problem.  Note that interrupted threads
                    # try to remove themselves from the list, but they'll
                    # ignore it if they are already removed.
                    self._waiting._pop()
                    if temp_avail <= 0:
                        break
                else:
                    break

# ===========================================================================
#                         Inverted Semaphore
# ===========================================================================

cdef class inverted_semaphore:

    """
    An inverted semaphore works very much like a regular semaphore, except
    threads block _until_ the value reaches zero. For example, if you want a
    thread to wait for 1 or more events to finish, you can have each event
    raise the value (always nonblocking) and have your waiter thread call
    block_till_zero.

    :param value: The value to start the semaphore with.  It defaults to 0.

    :ivar value: The value of the inverted semaphore. Also available via
          __int__.
    :ivar _waiting: A fifo of coroutine objects waiting for the semaphore to
          reach zero. (C only).
    """

    cdef public value
    cdef _fifo _waiting

    def __init__ (self, value=0):
        self.value = value
        self._waiting = _fifo()

    def __int__ (self):
        return self.value

    def acquire (self, value=1):
        """Acquire a number of resource elements.

        This never blocks.

        :param value: The number of resource elements to acquire (add to the
              semaphore).  Defaults to 1.
        """
        self.value = self.value + value

    def release (self, value=1):
        """Release a number of resource elements.

        This never blocks.  This may wake up waiting threads.

        :param value: The number of resource elements to release (subtract
              from the semaphore).  Defaults to 1.
        """
        cdef coro co
        self.value = self.value - value
        if self.value == 0:
            # wake up all the waiters
            while self._waiting.size:
                co = self._waiting._pop()
                try:
                    co._schedule (None)
                except ScheduleError:
                    # Either dead or interrupted.
                    pass

    def block_till_zero (self):
        """Block until the inverted semaphore reaches zero.

        This will return immediately if the value is already zero.
        """
        cdef coro me
        if self.value == 0:
            return
        else:
            me = the_scheduler._current
            self._waiting.push (me)
            while self.value:
                try:
                    me.__yield ()
                except:
                    self._waiting._remove_fast (me)
                    raise

# ===========================================================================
#                         Mutex
# ===========================================================================

cdef class mutex:

    """
    Mutual Exclusion lock object.

    A single thread may acquire the mutex multiple times, but it must release
    the lock an equal number of times.

    :ivar _locked: Count of how many locks on the mutex are currently held.
    :ivar _owner: The coroutine object that owns the lock (None if no owner).
          (C only.)
    :ivar _waiting: A fifo of coroutine objects waiting for the lock.
    """

    cdef public int _locked
    cdef readonly object _owner
    cdef readonly _fifo _waiting

    def __init__ (self):
        self._locked = 0
        self._owner = None
        self._waiting = _fifo()

    def __len__ (self):
        return self._waiting.size

    def lock (self):
        """Lock the mutex.

        This will block if another coro already owns the mutex.

        A coro thread may lock the mutex multiple times.  It must call unlock
        the same number of times to release it.

        :returns: True if it blocked, False if the mutex was acquired
            immediately.
        """
        cdef coro me
        me = the_scheduler._current
        if self._locked and self._owner is not me:
            # wait for it to unlock
            self._waiting.push (me)
            try:
                me.__yield ()
                return True
            except:
                self._waiting._remove_fast (me)
                # If unlock was called *before* we were interrupted, then we
                # need to check if any threads waiting can take our spot.
                if self._owner is me:
                    self.unlock()
                raise
        else:
            self._locked = self._locked + 1
            self._owner = me
            return False

    def trylock(self):
        """Try to lock the mutex.

        :returns: True if it is already locked by another coroutine thread.
            Returns False if the lock was successfully acquired.
        """
        cdef coro me
        me = the_scheduler._current
        if self._owner is me or self._locked == 0:
            self._locked = self._locked + 1
            self._owner = me
            return False
        else:
            return True

    def locked (self):
        """Determine if the mutex is currently locked.

        :returns: True if the mutex is locked, otherwise False.
        """
        return (self._locked > 0)

    def has_lock (self, thread=None):
        """Determine if a particular coroutine has the lock.

        :param thread: The coroutine object to check if it owns the lock. If
              not specified, defaults to the current thread.

        :returns: True if the specified thread has the lock, otherwise
            returns False.
        """
        if thread is None:
            thread = the_scheduler._current
        return (self._owner is thread)

    def unlock (self):
        """Unlock the mutex.

        The thread unlocking must be the thread that initially locked it.

        :returns: True if another thread was waiting for the lock, otherwise
            it returns False.
        """
        cdef coro me, co
        if not self._locked:
            raise LockError, 'mutex unlock when no lock acquired'
        me = the_scheduler._current
        if self._owner is not me:
            raise LockError, 'Non-owner mutex unlock.'
        self._locked = self._locked - 1
        if self._locked != 0:
            # still haven't fully unlocked
            return False
        else:
            self._owner = None
            while self._waiting.size:
                co = self._waiting._pop()
                try:
                    co._schedule (None)
                except ScheduleError:
                    # either it's already scheduled, or it's dead,
                    # regardless, we'll ignore it.
                    pass
                else:
                    self._locked = 1
                    self._owner = co
                    return True
            else:
                # nothing to schedule
                return False

    # for 'with'
    __enter__ = lock
    def __exit__ (self, t, v, tb):
        self.unlock()

# ===========================================================================
#                         Read/Write Lock
# ===========================================================================

cdef class rw_lock:

    """
    A many-reader single-writer lock.

    This lock allows multiple "readers" to own the lock simultaneously. A
    "writer" can only acquire a lock if there are no other "readers" or
    "writers" holding the lock.  Readers block when acquiring the lock if a
    writer currently holds it.

    Readers and writers may acquire the lock multiple times, but they must
    release the lock an equal number of times.

    A thread that holds a write lock may acquire read locks, but not the other
    way around (holding a read lock and trying to acquire a write lock will
    cause a deadlock).

    :ivar _writer: Count of the number of write locks. (C only.)
    :ivar _writer_id: Thread ID of the current write lock owner (0 if there
          is no owner). (C only.)
    :ivar _reader: Count of the number of read locks. (C only.)
    :ivar _waiting_writers: A fifo of coroutine objects waiting for a write
          lock. (C only.)
    :ivar _waiting_readers: A fifo of coroutine objects waiting for a read
          lock. (C only.)
    """

    cdef int _writer
    cdef int _writer_id
    cdef int _reader
    cdef _fifo _waiting_writers
    cdef _fifo _waiting_readers

    def __init__ (self):
        self._waiting_writers = _fifo()
        self._waiting_readers = _fifo()
        self._writer = 0
        self._writer_id = 0
        self._reader = 0

    def read_lock (self):
        """Acquire a read lock.

        Blocks if a writer owns the lock, or if any writers are waiting for the
        lock.  An exception is if the writer that owns the lock is the current
        thread.

        A coro thread may acquire multiple read locks, but it must call
        :meth:`read_unlock` an equal number of times.
        """
        cdef coro me
        me = the_scheduler._current
        # if it's me, then let me lock it
        while (self._writer and self._writer_id != me.id) or self._waiting_writers:
            self._waiting_readers._push (me)
            try:
                me.__yield ()
                # Must re-run because someone could have been scheduled before me.
            except:
                # was interrupted while waiting for the lock...give up.
                self._waiting_readers._remove_fast (me)
                raise
        # no writer lock or waiting writers...grab a read lock
        self._reader = self._reader + 1

    def try_read_lock(self):
        """Attempt to acquire a read lock.

        This is the same as :meth:`read_lock` except it does not block if it cannot
        acquire the lock.

        :returns: True if it cannot acquire the lock.
            False if it successfully acquired the lock.
        """
        cdef coro me
        me = the_scheduler._current
        if (self._writer and (self._writer_id != me.id)) or self._waiting_writers:
            return True
        else:
            self.read_lock()
            return False

    def write_lock (self):
        """Acquire a write lock.

        This blocks if there are any other readers or writers holding the lock.

        A coro thread may acquire multiple write locks, but it must call
        :meth:`write_unlock` an equal number of times.

        Attempting to acquire a read lock while holding a write lock will cause
        a deadlock.
        """
        cdef coro me
        me = the_scheduler._current
        if (self._writer and self._writer_id != me.id) or self._reader:
            # there is already another writer with a lock
            # or some reader threads still running
            # wait for them to finish
            self._waiting_writers._push (me)
            try:
                me.__yield ()
                return
            except:
                # Interrupted while waiting for my lock..give up.
                # If *_unlock() is called *after* we were interrupted, we will
                # have already been removed from the list.  remove_fast will not
                # raise an exception if it can't find the entry, so we are ok.
                self._waiting_writers._remove_fast (me)
                # If *_unlock() is called *before* we were interrupted, then we
                # need to check if any threads waiting can take our spot.
                if self._writer_id == me.id:
                    self.write_unlock()
                raise
        else:
            # No other writers, no other readers...grab the lock
            self._writer = self._writer + 1
            self._writer_id = me.id

    def try_write_lock(self):
        """Attempt to acquire a write lock.

        This is the same as :meth:`write_lock` except it does not block if it cannot
        acquire the lock.

        :returns: True if it cannot acquire the lock.
            False if it successfully acquired the lock.
        """
        cdef coro me
        me = the_scheduler._current
        if (self._writer and (self._writer_id != me.id)) \
           or self._reader:
            return True
        else:
            self.write_lock()
            return False

    def write_unlock (self):
        """Release a write lock.

        The thread unlocking must be the thread that initially locked it.
        """
        cdef coro me, co
        me = the_scheduler._current
        if self._writer_id != me.id:
            raise LockError, 'unlock writer id=%r current=%r' % (self._writer_id, me.id)
        # This is a writer...first try to unlock other writers
        self._writer = self._writer - 1
        if self._writer:
            # I still own the lock (locked multiple times)
            return
        self._writer_id = 0
        while self._waiting_writers.size:
            co = self._waiting_writers._pop()
            try:
                co._schedule (None)
            except ScheduleError:
                # guy disappeared, move on to next
                pass
            else:
                self._writer_id = co.id
                self._writer = 1
                return
        # no writers waiting...try to schedule a reader
        while self._waiting_readers.size:
            co = self._waiting_readers._pop()
            try:
                co._schedule (None)
            except ScheduleError:
                pass

    def read_unlock (self):
        """Release a read lock.

        The thread unlocking must be the thread that initially locked it.
        """
        cdef coro me, co
        me = the_scheduler._current
        if not self._reader:
            raise LockError, 'unlock without acquired lock'
        if self._writer_id and self._writer_id != me.id:
            raise LockError, 'read unlock when me=%r writer lock=%r' % (me.id, self._writer_id)
        self._reader = self._reader - 1
        # if there are any writers waiting, wake one
        if self._reader==0 and self._writer==0 and self._waiting_writers.size:
            while self._waiting_writers.size:
                co = self._waiting_writers._pop()
                try:
                    co._schedule (None)
                except ScheduleError:
                    # move on to next
                    pass
                else:
                    self._writer_id = co.id
                    self._writer = 1
                    return
        # no writers waiting...nobody to wake up
        return

# ===========================================================================
#                         Condition Variable
# ===========================================================================

cdef class condition_variable:

    """
    This locking primitive provides a method to "trigger" an event for other
    threads.

    :ivar _waiting: A fifo of coroutine objects waiting for the lock. (C only.)
    """

    cdef readonly _fifo _waiting

    def __init__ (self):
        self._waiting = _fifo()

    def __len__ (self):
        return self._waiting.size

    cdef _wait (self):
        cdef coro me
        me = the_scheduler._current
        IF CORO_DEBUG:
            assert me is not None
        self._waiting.push (me)
        try:
            return me.__yield ()
        except:
            self._waiting._remove_fast (me)
            raise

    def wait (self):
        """Wait for the condition variable to be triggered.

        :returns: The arguments given to the wake call (defaults to the empty
            tuple).
        """
        return self._wait()

    def wait_timeout (self, timeout):
        """Deprecated."""
        warnings.warn('condition_variable.wait_timeout is deprecated, use with_timeout(timeout, cv.wait) instead.', DeprecationWarning)
        return with_timeout (timeout, self.wait)

    cdef _wake_one (self, args):
        cdef coro co
        while self._waiting.size:
            co = self._waiting._pop()
            try:
                co._schedule (args)
            except ScheduleError:
                pass
            else:
                return True
        else:
            return False

    def wake_one (self, args=()):
        """Wake only 1 thread.

        If there are no threads waiting, this does nothing.

        :param args: The arguments to wake the thread with.  Defaults to the
              empty tuple.

        :returns: True if a thread was awoken, False if not.
        """
        return self._wake_one (args)

    def wake_all (self, args=()):
        """Wake all waiting threads.

        :param args: The arguments to wake the thread with.  Defaults to the
              empty tuple.
        """
        cdef coro co
        while self._waiting.size:
            co = self._waiting._pop()
            try:
                co._schedule (args)
            except ScheduleError:
                pass

    def wake_n (self, int count, args=()):
        """Wake a specific number of threads.

        :param count: The number of threads to wake up.
        :param args: The arguments to wake the thread with.  Defaults to the
              empty tuple.

        :returns: The total number of threads actually awoken.
        """
        cdef coro co
        cdef int total
        total = 0
        while count and self._waiting.size:
            co = self._waiting._pop()
            try:
                co._schedule (args)
            except ScheduleError:
                pass
            else:
                total = total + 1
                count = count - 1
        return total

    def raise_all (self, the_exception):
        """Raise an exception on all waiting threads.

        :param the_exception: The exception to raise on all waiting threads.
        """
        cdef coro co
        while self._waiting.size:
            co = self._waiting._pop()
            try:
                co.__interrupt (the_exception)
            except ScheduleError:
                pass

# ===========================================================================
#                         fifo
# ===========================================================================

# XXX why not inherit from _fifo?

cdef class fifo:

    """
    First-in First-Out container.

    This uses a linked list.

    :ivar fifo: The fifo object. (C only.)
    :ivar cv: A condition variable. (C only.)
    """

    cdef _fifo fifo
    cdef readonly condition_variable cv

    def __init__ (self):
        self.fifo = _fifo()
        self.cv = condition_variable()

    def __len__ (self):
        return self.fifo.size

    def __iter__ (self):
        return self.fifo.__iter__()

    def push (self, thing):
        """Push an object to the end of the FIFO.

        :param thing: The thing to add to the FIFO.
        """
        self.fifo._push (thing)
        self.cv.wake_one()

    def pop (self):
        """Pop an object from the head of the FIFO.

        This blocks if the FIFO is empty.

        :returns: The next object from the FIFO.
        """
        while self.fifo.size == 0:
            self.cv._wait()
        return self.fifo._pop()

    def pop_all (self):
        """Pop all objects from the FIFO.

        This will block if the fifo is empty and wait until there is an element
        to pop.

        :returns: A list of objects.  Returns an empty list if the FIFO is
            empty.
        """
        cdef int i
        cdef list result
        while self.fifo.size == 0:
            self.cv.wait()
        result = [None] * self.fifo.size
        i = 0
        while self.fifo.size:
            result[i] = self.fifo._pop()
            i = i + 1
        return result

    def top (self):
        """Return the top object from FIFO, or raise IndexError

        :returns: The first object from the FIFO.
        """
        return self.fifo._top()

    def push_front (self, thing):
        """Push an object to the front of the FIFO.

        :param thing: The thing to add.
        """
        self.fifo.push_front (thing)
        self.cv.wake_one()
