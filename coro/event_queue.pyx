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

# $Header: /cvsroot/ap/shrapnel/coro/event_queue.pyx,v 1.1 2007/01/03 00:19:50 ehuss Exp $

__event_queue_version__ = "$Id: event_queue.pyx,v 1.1 2007/01/03 00:19:50 ehuss Exp $"

include "python.pxi"
from cython.operator cimport dereference as deref, preincrement as inc
from libcpp.utility cimport pair
from libc.stdint cimport uint64_t

cdef extern from "<map>" namespace "std":
    cdef cppclass multimap[T, U]:
        cppclass iterator:
            pair[T,U]& operator*()
            iterator operator++()
            iterator operator--()
            bint operator==(iterator)
            bint operator!=(iterator)
 
        map()
        U& operator[](T&)
        U& at(T&)
        iterator begin()
        size_t count(T&)
        bint empty()
        iterator end()
        void erase(iterator)
        void erase(iterator, iterator)
        size_t erase(T&)
        iterator find(T&)
        pair[iterator, bint] insert(pair[T,U])
        size_t size()

cdef class event_queue:
    cdef multimap[uint64_t, PyObject*] *q

    def __cinit__(self):
        self.q = new multimap[uint64_t, PyObject*]()

    def __dealloc__(self):
        cdef multimap[uint64_t, PyObject*].iterator it = self.q.begin()
        while it != self.q.end():
            Py_DECREF(<object> deref(it).second)
            inc(it)
        del self.q

    cpdef insert(self, uint64_t time, value):
        """Insert a new value into the queue.

        :Parameters:
            - `time`: The uint64 time.
            - `value`: The value to insert.
        """
        cdef pair[uint64_t, PyObject*] p
        p.first, p.second = time, <PyObject *> value
        self.q.insert(p)
        Py_INCREF(value)

    def __len__(self):
        return self.q.size()

    cpdef top(self):
        """Peek at the top value of the queue.

        :Return:
            Returns value from the top of the queue.

        :Exceptions:
            - `IndexError`: The queue is empty.
        """
        if not self.q.size():
            raise IndexError('Top of empty queue')
        cdef multimap[uint64_t, PyObject*].iterator it = self.q.begin()
        return <object> deref(it).second

    cpdef pop(self):
        """Grab the top value of the queue and remove it.

        :Return:
            Returns value from the top of the queue.

        :Exceptions:
            - `IndexError`: The queue is empty.
        """
        if not self.q.size():
            raise IndexError('Top of empty queue')
        cdef multimap[uint64_t, PyObject*].iterator it = self.q.begin()
        value = <object> deref(it).second
        self.q.erase(it)
        Py_DECREF(value)
        return value

    cpdef remove(self, uint64_t time, value):
        """Delete a value from the queue.

        :Parameters:
            - `time`: The uint64 time.
            - `value`: The value to delete.
        """
        cdef PyObject *val
        cdef multimap[uint64_t, PyObject*].iterator it = self.q.find(time)
        cdef PyObject *v = <PyObject *> value
        while it != self.q.end():
            if deref(it).first != time:
                break
            val = <PyObject *> deref(it).second
            if v == val:
                self.q.erase(it)
                Py_DECREF(<object>val)
                return 0
            else:
                inc(it)
        raise IndexError('Event not found')
