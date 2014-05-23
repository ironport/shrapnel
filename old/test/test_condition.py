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

wait1 = coro.condition_variable()
wait2 = coro.condition_variable()

def func1():
    print "func1 entering into wait."
    wait1.wait()
    print "func1 broke out of wait."

def func1_2():
    print "func1_2 entering into wait."
    wait1.wait()
    print "func1_2 broke out of wait."

def func2():
    print "func2 entering into wait."
    wait2.wait()
    print "func2 broke out of wait."

def func2_2():
    print "func2_2 entering into wait."
    wait2.wait()
    print "func2_2 broke out of wait."

def func3():
    wait1.wake_one()
    wait2.wake_all()

coro.spawn(func1)
coro.spawn(func1_2)
coro.spawn(func2)
coro.spawn(func2_2)
coro.spawn(func3)
coro.event_loop(30.0)
