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

cdef class node:
    cdef object data
    cdef node next

    def __cinit__ (self, object data, node next):
        self.data = data
        self.next = next

cdef class _fifo:
    cdef node head, tail
    cdef readonly int size

    def __cinit__ (self):
        self.head = self.tail = None
        self.size = 0

    def __len__ (self):
        return self.size

    def __iter__ (self):
        return _fifo_iterator(self.head)

    cdef _push (self, object data):
        cdef node tail
        tail = node (data, None)
        if self.size == 0:
            self.tail = tail
            self.head = tail
        else:
            self.tail.next = tail
            self.tail = tail
        self.size += 1

    cpdef push_front (self, object data):
        cdef node head
        head = node (data, None)
        if self.size == 0:
            self.head = head
            self.tail = head
        else:
            head.next = self.head
            self.head = head
        self.size += 1

    cdef _pop (self):
        cdef node head
        if self.size == 0:
            raise IndexError
        else:
            result = self.head.data
            self.head = self.head.next
            self.size = self.size - 1
            if self.size == 0:
                self.head = self.tail = None
            return result

    cdef _top (self):
        if self.size == 0:
            raise IndexError
        else:
            return self.head.data

    cdef _remove_fast (self, data):
        cdef node n0, n1
        if self.size == 0:
            return False
        else:
            n0 = self.head
            if n0.data is data:
                self._pop()
            else:
                n1 = n0.next
                while n1 is not None:
                    if n1.data is data:
                        n0.next = n1.next
                        if n1 is self.tail:
                            self.tail = n0
                        self.size = self.size - 1
                        return True
                    else:
                        n0 = n1
                        n1 = n1.next
                else:
                    return False

    def push (self, data):
        return self._push (data)

    def pop (self):
        return self._pop()

    def top (self):
        return self._top()

    def remove_fast (self, data):
        return self._remove_fast (data)

cdef class _fifo_iterator:

    cdef node ptr

    def __cinit__(self, ptr):
        self.ptr = ptr

    def __iter__(self):
        return self

    def __next__(self):
        if self.ptr is not None:
            x = self.ptr.data
            self.ptr = self.ptr.next
            return x
        else:
            raise StopIteration
