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

# $Header: //prod/main/ap/shrapnel/coro/local.pyx#3 $


cdef class ThreadLocal:

    """Thread Local Storage.

    This class implements a thread-local storage facility.  You create an
    instance of ThreadLocal.  You can get and set arbitrary attributes on that
    instance, and those attributes will be thread-local. For example::

        >>> local = coro.ThreadLocal()
        >>> local.foo = 1
        >>> local.foo
        1

    Now, any code that references this ``local`` object can set and get any
    variable on that object, and the value will be local to that thread.
    Imagine this running in another thread::

        >>> local.foo
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
          File "local.pyx", line 35, in coro._coro.ThreadLocal.__getattr__
        AttributeError: foo
        >>> local.foo = 2
        >>> local.foo
        2

    Now, in the original thread in the first example, imagine doing this::

        >>> local.foo
        1

    Notice how the attribute stays the same value for that thread.

    Tip: You can subclass ThreadLocal to add any logic you wish.

    Note: This API is very similar to the one in Python (threading.local)
    with 1 important difference: __slots__ are not supported.  Python's
    implementation allows you to add attributes that are not thread-local
    by defining __slots__.  This is not supported at this time.

    """

    # __slots__ notes:
    # Supporting the non-thread-local feature of standard Python's
    # thread-local object is nontrivial.  It seems like a dumb feature to
    # start with, but I'll summarize my findings:
    #
    # - Python's local object keeps an attribute "dict" which is a reference
    #   to the current thread's dictionary.  It does a lot of gymnastics to
    #   make sure it stays set.  I *think* this is because it uses
    #   PyObject_GenericGetAttr which will reference the dict.  It does this
    #   via the tp_dictoffset slot, which Pyrex does not support.
    #
    # - We would need to change __getattr__ to check if type(self) is
    #   ThreadLocal and call PyObject_GenericGetAttr if not true.  This
    #   assumes you fix the tp_dictoffset issue.
    #
    # - I don't fully understand how setattr works in the python
    #   implementation.  Too much magic.
    #
    # - We could use metaclasses like the Python implementation technique in
    #   _threading_local.py.  Yuck.

    cdef object key

    def __cinit__(self):
        self.key = 'thread.local.%i' % (<long><void *>self,)

    cdef __ldict(self):
        cdef coro co

        co = the_scheduler._current
        if co._tdict is None:
            co._tdict = {}
        _tdict = co._tdict
        ldict = PyDict_GET_ITEM_SAFE(_tdict, self.key, None)
        if ldict is None:
            ldict = {}
            _tdict[self.key] = ldict
        return ldict

    def __setattr__(self, name, value):
        ldict = self.__ldict()
        ldict[name] = value

    def __getattr__(self, name):
        ldict = self.__ldict()
        try:
            return ldict[name]
        except KeyError:
            raise AttributeError(name)

    def __delattr__(self, name):
        ldict = self.__ldict()
        try:
            del ldict[name]
        except KeyError:
            raise AttributeError(name)

    def __dealloc__(self):
        cdef coro co

        # _all_threads.itervalues() might be better here.
        for co in _all_threads.values():
            if co._tdict is not None:
                # Avoiding exceptions for performance.
                # Would be much better to just call PyDict_DelItem, but we've
                # defined it with except -1.
                if co._tdict.has_key (self.key):
                    del co._tdict[self.key]

    property __dict__:

        def __get__(self):
            return self.__ldict()
