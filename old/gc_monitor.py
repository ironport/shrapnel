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
import gc
import types

monitor_sleep_interval = 60 * 60

def safe_repr (x):
    if isinstance (x, types.InstanceType):
        return '<%s object at %x>' % (x.__class__.__name__, id(x))
    else:
        return '<%s object at %x>' % (str(type(x)), id(x))

def monitor_thread():
    while True:
        if gc.garbage:
            coro.print_stderr (
                "Warning: possible memory leak: len(gc.garbage)=%d\n" % (len(gc.garbage),)
            )
            coro.print_stderr (
                "\tFirst %d objects in gc.garbage:\n" % (len(gc.garbage[:5]))
            )
            for x in gc.garbage[:5]:
                coro.print_stderr ("\t  %s\n" % (safe_repr (x),))
        coro.sleep_relative (monitor_sleep_interval)
