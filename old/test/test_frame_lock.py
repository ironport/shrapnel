# -*- Mode: Python -*-
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


import coro
import operator
import sys
from functools import reduce

W = coro.write_stderr

# These tests need to be cleaned up a bit so they make sense to
# someone other than me.  The general structure of these is to uncover
# unexpected recursive invocations of the Python VM by getting them to
# stack up; and then unwind out of order.  Several of the tests below
# do this by arranging a series of functions to wait a certain amount
# of time before returning.  If we arrange for the first-called to be
# the first to return, we'll get them out of order.

class thing:

    def __init__ (self, sleep):
        self.sleep = sleep

    def __call__ (self, *args):
        W ('%r.__call__(), depth=%d\n' % (self, sys.get_dispatcher_depth()))
        coro.sleep_relative (self.sleep)
        return reduce (operator.add, args)

class thing2:

    def __init__ (self, sleep):
        coro.sleep_relative (sleep)
        W ('%r.__init__(), depth=%d\n' % (self, sys.get_dispatcher_depth()))

def fun0 (sleep, arg0, arg1):
    fun_42(sleep)
    return arg0 + arg1

def fun_42 (sleep):
    coro.sleep_relative (sleep)

def fun1 (sleep, arg0, arg1):
    W ('fun1() sleep=%d\n' % sleep)
    result = fun0(*(sleep, arg0, arg1))
    W ('fun1() sleep=%d, result=%r\n' % (sleep, result))

# tests switching in __call__
def go (t):
    W ('before %r {%d}\n' % (t, sys.get_dispatcher_depth()))
    result = t(3, 4, 5)
    W ('after %r {%d}\n' % (t, sys.get_dispatcher_depth()))
    return result

# tests switching in __init__
def go2():
    for x in range (5):
        coro.spawn (go3, x)

# tests switching in apply()
def go4():
    for x in range (5):
        coro.spawn (fun1, x, 3, 4)

def fun2 (sleep):
    W ("fun2() sleep=%d\n" % (sleep,))
    x = thing2(*(sleep,))
    W ("fun2() sleep=%d, result=%r\n" % (sleep, x))

def go5():
    for x in range (5):
        coro.spawn (fun2, x)

all_things = []

def go3 (x):
    global all_things
    W ('before __init__\n')
    t = thing2 (x)
    W ('appending %r\n' % (t,))
    all_things.append (t)

class Plonk (Exception):
    def __init__ (*args):
        Exception.__init__ (*args)
        W ('args=%r\n' % (args,))

def fun3():
    coro.sleep_relative (5)
    raise Plonk(1, 2, 3)

def fun4():
    for i in range (50):
        x = operator.add(*(3, 4))
        assert (x == 7)
        W ('x=7 [%d]\n' % (sys.getrefcount(7)))

def fun5():
    for i in range (50):
        x = thing(*(i,))
        W ('None [%d]\n' % (sys.getrefcount(None)))

# ================================================================================
# test switching in call of unbound method
# ================================================================================

class my_fifo (coro.fifo):

    def pop (self):
        return coro.fifo.pop (self)

the_fifo = my_fifo()

def popper (n):
    global live
    W ('>%d>' % (n,))
    while True:
        x = the_fifo.pop()
        W ('[%d.%d]' % (n, x))
        coro.sleep_relative (0)
    W ('<%d<' % (n,))

def pusher():
    i = 0
    while i < 100:
        the_fifo.push (i)
        coro.sleep_relative (.005)
        i += 1
    coro._exit = 1

def fun6():
    coro.spawn (pusher)
    for i in xrange (13):
        coro.spawn (popper, i)

# ================================================================================

def fun7():
    import os
    v = os.environ.get ("HOME")
    W ('v=%r\n' % (v,))
    W ('os.environ=%r\n' % (os.environ,))

# ================================================================================

import _coro

class X:
    def m (self, arg):
        _coro.breakpoint()
        return arg + 42

class Y (X):
    def m (self, arg):
        return X.m (self, arg) + 19

def fun8():
    y = Y()
    W ('y.m(34)=%r\n' % (y.m(34),))

# ================================================================================

class A:
    def m (self, t, *args):
        W ('>> %r.m(), t=%d depth=%d\n' % (self, t, sys.get_dispatcher_depth()))
        coro.sleep_relative (t)
        W ('<< %r.m(), t=%d depth=%d\n' % (self, t, sys.get_dispatcher_depth()))
        return args + (42,)

def go9 (t):
    a = A()
    return a.m (t, 3, 4, 5)

# tests switching in fancy-args method (ext_do_call)
def fun9():
    for x in range (5):
        coro.spawn (go9, x)

# ================================================================================

if 0:
    # tests switching in __call__
    for x in range (5):
        t = thing (x)
        coro.spawn (go, t)
elif 0:
    # tests switching in __init__
    coro.spawn (go2)
elif 0:
    # tests switching in apply()
    coro.spawn (go4)
elif 0:
    # tests switching in apply(<class>, <args>)
    coro.spawn (go5)
elif 0:
    # tests exception.__init__
    coro.spawn (fun3)
elif 0:
    # tests apply (<builtin>, <args>)
    coro.spawn (fun4)
elif 0:
    # leak test __init__
    coro.spawn (fun5)
elif 0:
    # tests switching in call of unbound method
    coro.spawn (fun6)
elif 0:
    # ensure override of __repr__ doesn't get UnwindToken
    coro.spawn (fun7)
elif 0:
    # tests some other fucked-up thing
    coro.spawn (fun8)
elif 1:
    # tests switching in fancy-args method
    coro.spawn (fun9)

coro.event_loop()
