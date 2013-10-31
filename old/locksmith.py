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

"""locksmith.py

This is a class that manages a set of locks.
"""

import coro
import random
import tb

class DeadlockError(Exception):
    """DeadlockError

    Raised when an attempt to call lock() causes a deadlock.
    """
    pass

class LockSmith:

    """LockSmith()

    This class manages a set of locks.
    Locks are associated with a key.
    A separate thread handles detecting deadlocks.
    """

    # How often the manager thread checks for deadlocks in seconds.
    deadlock_check_period = 60

    # The coroutine object that is the thread manager.
    thread = None

    def __init__(self):
        self.locks = {}

    def __len__(self):
        return len(self.locks)

    def check_for_deadlocks(self):
        """check_for_deadlocks(self) -> None
        This will check for deadlocks.
        Deadlocks will be broken by picking one of the deadlocked threads and
        raising DeadlockError on it.
        """
        # In order to detect deadlock, we build a wait-for-graph.
        # Each node in the graph is a thread.  An edge (t1, t2) indicates
        # that thread t1 is waiting for a lock that is currently held by t2.
        # We compute the "in-degree" value for each node.  That is the number
        # of edges leading into the node.  We do a topological-order traversal
        # of the graph.  If we do not successfully visit a node, then that
        # indicates a cycle which implies a deadlock.
        if len(self.locks) <= 1:
            return
        g = self._build_graph()
        thread_ids = self._find_threads_to_break(g)
        for thread_id in thread_ids:
            thread = coro.all_threads[thread_id]
            thread.raise_exception(DeadlockError)
        if __debug__:
            # Make sure that there are no more cycles.
            for k,v in g.items():
                if v in thread_ids:
                    del g[k]
            cycle_g = self._find_cycles(g)
            assert (len(cycle_g)==0)

    def _build_graph(self):
        """_build_graph(self) -> g
        Builds a wait-for-graph based on the threads in the locks.
        """
        raise NotImplementedError

    def _in_degree(self, g):
        """_in_degree (self, g) -> indegree_dict
        Computes the in-degree for each vertex and returns a dictionary where
        the key is the vertex and the value is its in-degree.

        <g>: A graph.  Dictionary with keys as nodes and value is a list of
        nodes pointing to it.
        """
        r = {}
        # set every node's in-degree to zero
        for k, v in g.iteritems():
            r[k] = 0
            r[v] = 0
        # every time we find an edge, increment the destination
        for v in g.itervalues():
            r[v] += 1
        return r

    def _find_threads_to_break(self, g):
        """_find_threads_to_break(self, g) -> thread_id_list
        Find threads to interrupt with DeadlockError in order to break any
        cycles that exist.  In a cycle, it picks a thread at random to break
        the cycle.  There can be more than 1 thread returned if there are
        multiple cycles.
        """
        to_break = []
        cycle_g = self._find_cycles(g)
        while cycle_g:
            # Randomly pick a node to break.
            thread = random.choice(cycle_g.keys())
            del cycle_g[thread]
            to_break.append(thread)
            cycle_g = self._find_cycles(cycle_g)
        return to_break

    def _find_cycles(self, g):
        """_find_cycles(g) -> cycle_g
        Finds cycles in the given graph.

        <g>: A graph.  Dictionary with keys as nodes and value the node it is
        pointing to.

        Returns <g> with all nodes not involved in a cycle removed.
        """
        g = g.copy()
        while 1:
            in_d = self._in_degree(g)
            found = False
            for k, v in in_d.iteritems():
                if v == 0:
                    # found a node with in-degree of zero.
                    del g[k]
                    found = True
            if not found:
                return g

    def start_manager_thread(self):
        """start_manager_thread(self) -> None
        This will spawn a thread that continually monitors the locks looking
        for deadlocks.
        """
        assert (self.thread is None)
        self.thread = coro.spawn(self.thread_manager, thread_name='locksmith_cycle_manager')

    def thread_manager(self):
        """thread_manager(self) -> None
        This is the deadlock detection thread.
        """
        while 1:
            try:
                coro.sleep_relative(self.deadlock_check_period)
                self.check_for_deadlocks()
            except coro.Interrupted:
                # Exiting.
                self.thread = None
                return
            except:
                coro.print_stderr(tb.traceback_string() + '\n')

    def stop_manager_thread(self):
        """stop_manager_thread(self) -> None
        This will stop the manager thread.
        """
        if self.thread is not None:
            self.thread.shutdown()


class MutexLockSmith(LockSmith):

    # Rules of the global lock:
    # To get the global lock, no other threads may have any locks.
    #   - If other threads have locks, wait for them to unlock.
    #     - During this time, all new threads attempting to lock a new var will block.
    #     - Wait for all current threads to finish, then get global lock.
    # While someone has the global lock, you are not allowed to lock anything.

    global_lock_name = '__global__'

    def __init__(self, *args):
        LockSmith.__init__(self, *args)
        # Threads waiting to acquire the global lock wait on global_cv.
        self.global_cv = coro.condition_variable()
        # Threads waiting for the global lock to be released wait on global_finished_cv.
        self.global_finished_cv = coro.condition_variable()

    def lock_global(self):
        """lock_global(self) -> None
        Acquires the global lock.
        """
        # Check if the rules are being met to acquire the global lock.
        while 1:
            if not self.locks:
                # Simple case, no other locks held.
                self._lock(self.global_lock_name)
                return

            # Check if I am the sole owner of all locks.
            for lock in self.locks.values():
                if not lock.has_lock() or lock:
                    # Don't own this lock or there are waiters for it.
                    break
            else:
                # I own all the locks, nobody waiting for them.
                self._lock(self.global_lock_name)
                return
            # Must wait for all current threads to release their locks.
            self.global_cv.wait()
            # Loop again.

    def try_lock_global(self):
        """try_lock_global(self) -> boolean
        Attempts to acquire the global lock, without blocking. Returns true
        on failure and false on success, mirroring the behavior of
        coro.mutex.trylock().
        """
        # Check if the rules are being met to acquire the global lock.
        if not self.locks:
            # Simple case, no other locks held. This should always succeed.
            rv = self._trylock(self.global_lock_name)
            assert(not rv)
            return False

        # Check if I am the sole owner of all locks.
        for lock in self.locks.values():
            if not lock.has_lock() or lock:
                # Don't own this lock or there are waiters for it.
                break
        else:
            # I own all the locks, nobody waiting for them. This should always
            # succeed.
            return self._trylock(self.global_lock_name)
            assert(not rv)
            return False

        # Must wait for all current threads to release their locks.
        return True

    def unlock_global(self):
        """unlock_global(self) -> None
        Unlock the global lock.
        """
        self._unlock(self.global_lock_name)
        # If the global lock is completely released.
        if not self.locks.has_key(self.global_lock_name):
            # See if anyone was waiting for it.
            if self.global_cv:
                # Wake them up.
                self.global_cv.wake_all()
            # People waiting for me to finish.
            elif self.global_finished_cv:
                # Wake them up.
                self.global_finished_cv.wake_all()
        else:
            # The global lock is still held.
            if __debug__:
                # Assertion check.
                lock = self.locks[self.global_lock_name]
                assert (lock.has_lock())

    def lock(self, key):
        """lock(self, key) -> None
        Aquires a lock for the given key.
        """
        # To lock the global lock, you need to use lock_global
        assert(key != self.global_lock_name)
        # Check if the rules for the global lock are met before getting a var lock.
        while 1:
            # If global lock is held.
            if self.locks.has_key(self.global_lock_name):
                lock = self.locks[self.global_lock_name]
                # And I don't hold it.
                if not lock.has_lock():
                    # Then I must wait.
                    self.global_finished_cv.wait()
                else:
                    # I own the global lock.  It is okay for me to lock other locks.
                    break
            # If someone is waiting for global lock.
            elif self.global_cv:
                # If I am a new thread.
                for lock in self.locks.values():
                    if lock.has_lock():
                        # Not a new thread.
                        break
                else:
                    # Then I must wait for the global lock to be released.
                    self.global_finished_cv.wait()
                    # Loop again.
                    continue
                # I am not a new thread, okay to lock.
                break
            else:
                # No global lock contention.
                break

        self._lock(key)

    def try_lock(self, key):
        """try_lock(self, key) -> boolean
        Attempts to acquire a lock for the given key, without blocking. Returns
        true on failure and false on success, mirroring the behavior of
        coro.mutex.trylock().
        """
        # To lock the global lock, you need to use lock_global
        assert(key != self.global_lock_name)

        # If global lock is held.
        if self.locks.has_key(self.global_lock_name):
            lock = self.locks[self.global_lock_name]
            # And I don't hold it.
            if not lock.has_lock():
                # Then I would block.
                return True
        # If someone is waiting for global lock.
        elif self.global_cv:
            # If I am a new thread.
            for lock in self.locks.values():
                if lock.has_lock():
                    # Not a new thread.
                    break
            else:
                # I am a new thread. I would have to wait for the global lock
                # to be released.
                return True

        return self._trylock(key)

    def _lock(self, key):
        # Could use setdefault, but that would mean the default argument
        # would cause a mutex object to be created every time and then thrown
        # away.
        if self.locks.has_key(key):
            lock = self.locks[key]
        else:
            lock = self.locks[key] = coro.mutex()
        lock.lock()

    def _trylock(self, key):
        # Could use setdefault, but that would mean the default argument
        # would cause a mutex object to be created every time and then thrown
        # away.
        if self.locks.has_key(key):
            lock = self.locks[key]
        else:
            lock = self.locks[key] = coro.mutex()
        return lock.trylock()

    def unlock(self, key):
        """unlock(self, key) -> None
        Releases a lock for the given key.

        Raises KeyError if no lock is being held.
        """
        # To unlock the global lock, you need to use unlock_global
        assert(key != self.global_lock_name)
        self._unlock(key)
        if not self.locks or self._global_waiter_has_all_locks():
            self.global_cv.wake_all()

    def _unlock(self, key):
        lock = self.locks[key]
        lock.unlock()
        if not lock.locked() and not lock:
            # Nobody waiting on this lock, get rid of it.
            del self.locks[key]

    def _global_waiter_has_all_locks(self):
        """_global_waiter_has_all_locks(self) -> boolean
        Returns whether or not one of the threads waiting for the global lock
        owns all locks.
        """
        for t in self.global_cv._waiting:
            for lock in self.locks.values():
                if not lock.has_lock(t):
                    # No, somebody else has this lock.
                    break
            else:
                # t owns all the current locks.
                return True
        # None of the global waiters has all the locks.
        return False

    def trylock(self, key):
        """trylock(self, key) -> boolean
        Attempts to lock the mutex.  If it is already locked, then it
        returns 1.  If it successfully acquires the lock, it returns 0.
        """
        if self.locks.has_key(key):
            lock = self.locks[key]
        else:
            lock = self.locks[key] = coro.mutex()
        return lock.trylock()

    def _build_graph(self):
        """_build_graph(self) -> g
        Builds a wait-for-graph based on the threads in the locks.
        """
        g = {}
        for lock in self.locks.values():
            owner_id = lock._owner.thread_id()
            for t in lock._waiting:
                thread_id = t.thread_id()
                # Not possible for a thread to be waiting for more than one
                # lock.
                assert (not g.has_key(thread_id))
                g[thread_id] = owner_id
        if self.global_cv:
            # Threads waiting to acquire the global lock.
            for t in self.global_cv._waiting:
                thread_id = t.thread_id()
                for lock in self.locks.values():
                    lock_owner_thread_id = lock._owner.thread_id()
                    # Do not include situation where I own an ordinary lock
                    # AND am waiting for the global lock.
                    if thread_id != lock_owner_thread_id:
                        assert (not g.has_key(thread_id))
                        g[thread_id] = lock_owner_thread_id

        if self.global_finished_cv:
            # Threads waiting for global lock to be released.
            # Rare case where we ran in between one thread unlocking the
            # global lock and another locking it can cause the global lock
            # to not exist.
            if self.locks.has_key(self.global_lock_name):
                lock = self.locks[self.global_lock_name]
                owner_thread_id = lock._owner.thread_id()
                for t in self.global_finished_cv._waiting:
                    thread_id = t.thread_id()
                    assert (not g.has_key(thread_id))
                    g[thread_id] = owner_thread_id
            # In theory, these threads are also waiting for anything
            # in self.global_cv._waiting, but that would break our
            # model a thread can only be blocked by 1 other thread.
            # This is ok, since it can't cause a deadlock, anyways.

        return g
