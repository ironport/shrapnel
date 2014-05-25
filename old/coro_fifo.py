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

import copy
import coro

class circular_fifo:

    """circular_fifo
    This is a circular fifo.  It is just a regular FIFO with much better
    performance than a python list using append() and pop(0).
    If the FIFO becomes full, then it will automatically double the
    size to allow more data to be added.
    """

    def __init__(self, default_size=1024, data=None):
        """circular_fifo(default_size = 1024, data = None) -> circular_fifo_object
        Default size is the number of slots you want to start with.
        data can be a list of elements to seed the fifo.
        """
        self.cv = coro.condition_variable()
        if data:
            # Note that we need an extra element because
            # we need somewhere for tail to point to.
            if len(data) <= default_size:
                default_size = len(data) + 1
            self._fifo = copy.copy(data)
            self._fifo.extend([None] * (default_size - len(data)))
            self._tail = len(data)
            self._head = 0
            self._fifo_size = default_size
        else:
            self._fifo = [None] * default_size
            self._tail = 0
            self._head = 0
            self._fifo_size = default_size

    def remove(self, entry):
        """remove(entry) -> None
        Removes the given entry from the fifo.  This is an actual value
        comparison, NOT an index comparison.

        Only removes the first instance (to match list behaviour).

        Everything is shifted to fit (thus performance can be poor if
        the item is not at the head or the tail of the queue).
        Raises ValueError if it is not in the queue.
        """
        if self._tail >= self._head:
            # normal list
            end = self._tail
        else:
            # wrapping list
            end = self._fifo_size
        for x in xrange(self._head, end):
            if self._fifo[x] == entry:
                # this is the entry to remove
                self._remove(x)
                # In theory, if we want to make it remove EVERY instance,
                # then we just remove this return and put it after the for loop
                # (same for the return in the code below)
                return None
        else:
            # see if we need to wrap around
            if self._tail < self._head:
                # yes, wrap around
                for x in xrange(self._tail):
                    if self._fifo[x] == entry:
                        # this is the entry to remove
                        self._remove(x)
                        return None
        raise ValueError("x not in list")

    def _remove(self, index):
        """_remove(index) -> None
        Removes the value at the given index
        (actual index in the list, not the queue).
        Assumes you've given a valid index.
        """
        if self._tail == self._head:
            # Sanity check
            return ValueError, "fifo is empty"
        if self._tail >= self._head:
            # normal list
            del self._fifo[index]
            self._fifo.append(None)
            self._tail -= 1
            return None
        else:
            # wrapping list
            if index >= self._head:
                # towards the end
                del self._fifo[index]
                self._fifo.insert(self._head, None)
                self._head += 1
            else:
                # towards the beginning
                del self._fifo[index]
                self._fifo.insert(self._tail, None)
                self._tail -= 1

    def enqueue(self, data):
        """enqueue(data) -> None
        Adds the given element to the fifo.
        """
        self._fifo[self._tail] = data
        self._tail += 1
        if self._tail == self._fifo_size:
            self._tail = 0
        if self._tail == self._head:
            # fifo is full...expand it
            self._fifo[self._tail:self._tail] = [None] * self._fifo_size
            self._head += self._fifo_size
            self._fifo_size *= 2
        self.cv.wake_all()

    def put_on_front(self, data):
        """put_on_front(self, data) -> None
        Puts the given data on the front of the FIFO.
        """
        if self._head == 0:
            # Wrap around.
            self._head = self._fifo_size - 1
        else:
            self._head -= 1
        self._fifo[self._head] = data
        if self._head == self._tail:
            # fifo is full...expand it
            self._fifo[self._tail:self._tail] = [None] * self._fifo_size
            self._head += self._fifo_size
            self._fifo_size *= 2
        self.cv.wake_all()

    def dequeue(self):
        """dequeue() -> data
        Returns the next element in the fifo.
        Blocks if the fifo is empty until someone adds data.
        """
        if self._tail == self._head:
            self.cv.wait()
        data = self._fifo[self._head]
        self._fifo[self._head] = None
        if self._head == self._fifo_size - 1:
            self._head = 0
        else:
            self._head += 1
        return data

    def peek(self):
        """peek() -> data
        Returns the next element in the fifo without actually removing it.
        Raises IndexError if the queue is empty.
        """
        if self._tail == self._head:
            raise IndexError('peek from an empty fifo')
        return self._fifo[self._head]

    def poke(self, data):
        """poke(self, data) -> None
        Replaces the data at head of the fifo.
        """
        if self._tail == self._head:
            raise IndexError('poke on an empty fifo')
        self._fifo[self._head] = data
        self.cv.wake_all()

    def count(self, entry):
        """count(entry) -> #
        Returns the number of times entry appears in the fifo.
        """
        c = 0
        for x in self:
            if x == entry:
                c += 1
        return c

    def __len__(self):
        if self._tail >= self._head:
            return self._tail - self._head
        else:
            return (self._fifo_size - self._head) + self._tail

    def __getitem__(self, key):
        if self._tail >= self._head:
            if self._head + key >= self._tail:
                raise IndexError(key)
            return self._fifo[self._head + key]
        else:
            if self._head + key >= self._fifo_size:
                key -= (self._fifo_size - self._head)
                if key >= self._tail:
                    raise IndexError(key)
                return self._fifo[key]
            return self._fifo[self._head + key]

    def __repr__(self):
        if self._tail >= self._head:
            return str(self._fifo[self._head:self._tail])
        else:
            return str(self._fifo[self._head:self._fifo_size] + self._fifo[:self._tail])

    def as_list(self):
        """as_list() -> list
        Returns the fifo as a list (the first element is the head of
        the fifo, the last element is the tail).
        """
        if self._tail >= self._head:
            return self._fifo[self._head:self._tail]
        else:
            return self._fifo[self._head:self._fifo_size] + self._fifo[:self._tail]

    def clear(self):
        """clear(self) -> None
        Empties the fifo.
        """
        self._head = 0
        self._tail = 0

if __name__ == '__main__':

    import coro
    import random
    import sys

    q = circular_fifo()
    finished = 0
    size = 10000

    def push_pop_test():

        def gets(i):
            for x in i:
                print x

        bob = circular_fifo(default_size=10)
        bob.enqueue(1)
        bob.enqueue(2)
        bob.enqueue(3)
        bob.enqueue(4)
        bob.enqueue(5)
        bob.enqueue(6)
        print '%i:%r' % (len(bob), bob)
        gets(bob)
        bob.dequeue()
        bob.dequeue()
        print '%i:%r' % (len(bob), bob)
        gets(bob)
        bob.enqueue(7)
        bob.enqueue(8)
        bob.enqueue(9)
        print '%i:%r' % (len(bob), bob)
        gets(bob)
        bob.enqueue(10)
        print '%i:%r' % (len(bob), bob)
        gets(bob)
        bob.enqueue(11)
        print '%i:%r' % (len(bob), bob)
        gets(bob)
        bob.enqueue(12)
        print '%i:%r' % (len(bob), bob)
        gets(bob)
        bob.enqueue(13)
        print '%i:%r' % (len(bob), bob)
        gets(bob)
        bob.enqueue(14)
        print '%i:%r' % (len(bob), bob)
        gets(bob)

        # sys.exit(0)

        coro.spawn(pusher)
        coro.spawn(popper)

    def pusher():
        global finished, q, size
        total = size
        while True:
            if total == 1:
                to_do = 1
            else:
                to_do = random.randint(1, total / 2)
            total -= to_do
            for x in xrange(to_do):
                q.enqueue('some_data')
            if total == 0:
                break
            coro.sleep_relative(0)
        finished = 1

    def popper():
        global finished, q, size
        for x in xrange(size):
            while True:
                data = q.dequeue()
                if data is not None:
                    break
                if finished:
                    break
                coro.sleep_relative(0)
            coro.sleep_relative(0)

    def remove_test():
        global q, finished, size
        for x in xrange(size):
            q.enqueue(random.randint(0, 1000))
        for x in xrange(1000):
            c = q.count(x)
            while c:
                # If this raises an error, then we know something is broken
                l = len(q)
                q.remove(x)
                if len(q) != l - 1:
                    raise Exception('didn\'t adjust size properly')
                c -= 1
            if q.count(x) != 0:
                raise Exception('failed to remove all entries for %i in %r' % (x, q))
        finished = 1

    def make_remove_test2(to_remove):
        global q, finished, size
        q = circular_fifo(10)
        for x in xrange(1, 9):
            q.enqueue(x)
        q.dequeue()
        q.dequeue()
        q.dequeue()
        q.enqueue(10)
        q.enqueue(11)
        q.enqueue(12)
        print 'before: ', to_remove, q._fifo, repr(q)
        q.remove(to_remove)
        print ' after: ', to_remove, q._fifo, repr(q)
        q.enqueue(13)
        print '    13: ', to_remove, q._fifo, repr(q)

    def remove_test2():
        global finished
        make_remove_test2(4)
        make_remove_test2(5)
        make_remove_test2(11)
        make_remove_test2(12)
        finished = 1

    def do_test(test_func):
        global q, finished
        q = circular_fifo()
        finished = 0
        coro.spawn(test_func)
        while not finished:
            coro.sleep_relative(1)

    def do_tests():
        global q, finished
        do_test(push_pop_test)
        do_test(remove_test)
        do_test(remove_test2)
        coro.set_exit()

    coro.spawn(do_tests)
    coro.event_loop()
