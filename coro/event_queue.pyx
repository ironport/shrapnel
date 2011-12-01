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

cdef extern from "event_queue.h":

    ctypedef void * cpp_event_queue "event_queue"

    cpp_event_queue * event_queue_new()
    void              event_queue_dealloc(cpp_event_queue * q)
    object            event_queue_top(cpp_event_queue * q, uint64_t * time)
    object            event_queue_pop(cpp_event_queue * q, uint64_t * time)
    int               event_queue_insert(cpp_event_queue * q, uint64_t time, object) except -1
    int               event_queue_delete(cpp_event_queue * q, uint64_t time, object) except -1
    int               event_queue_len(cpp_event_queue * q)

    ctypedef void * cpp_event_queue_iter "event_queue_iter"

    cpp_event_queue_iter event_queue_new_iter(cpp_event_queue * q)
    object               event_queue_iter_next(cpp_event_queue * q, cpp_event_queue_iter * iter, uint64_t * time)

cdef class event_queue_iter

cdef class event_queue:

    cdef cpp_event_queue * q

    def __cinit__(self):
        self.q = event_queue_new()

    def __dealloc__(self):
        event_queue_dealloc(self.q)

    def __len__(self):
        return event_queue_len(self.q)

    cdef int len(self):
        return event_queue_len(self.q)

    cdef c_top(self, uint64_t * time):
        return event_queue_top(self.q, time)

    def top(self):
        """Peek at the top value of the queue.

        :Return:
            Returns a ``(time, value)`` tuple from the top of the queue.

        :Exceptions:
            - `IndexError`: The queue is empty.
        """
        cdef uint64_t time

        value = event_queue_top(self.q, &time)
        return (time, value)

    cdef c_pop(self, uint64_t * time):
        return event_queue_pop(self.q, time)

    def pop(self):
        """Grab the top value of the queue and remove it.

        :Return:
            Returns a ``(time, value)`` tuple from the top of the queue.

        :Exceptions:
            - `IndexError`: The queue is empty.
        """
        cdef uint64_t time

        value = event_queue_pop(self.q, &time)
        return (time, value)

    cdef c_insert(self, uint64_t time, value):
        event_queue_insert(self.q, time, value)

    def insert(self, uint64_t time, value):
        """Insert a new value into the queue.

        :Parameters:
            - `time`: The uint64 time.
            - `value`: The value to insert.
        """
        event_queue_insert(self.q, time, value)

    cdef c_delete(self, uint64_t time, value):
        event_queue_delete(self.q, time, value)

    def delete(self, uint64_t time, value):
        """Delete a value from the queue.

        :Parameters:
            - `time`: The uint64 time.
            - `value`: The value to delete.
        """
        event_queue_delete(self.q, time, value)

    def __iter__(self):
        cdef event_queue_iter i

        i = event_queue_iter()
        i.q = self.q
        i.iter = event_queue_new_iter(self.q)
        return i

cdef class event_queue_iter:

    cdef cpp_event_queue * q
    cdef cpp_event_queue_iter iter

    def __iter__(self):
        return self

    def __next__(self):
        cdef uint64_t time

        value = event_queue_iter_next(self.q, &self.iter, &time)
        return (time, value)
