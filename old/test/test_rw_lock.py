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

rw_lock = coro.rw_lock()

def test_rw_lock():
    rw_lock.read_lock()
    rw_lock.read_lock()
    # since write_lock will block, let's get someone to unlock the readers
    coro.spawn(unlocker)
    rw_lock.write_lock()
    coro.spawn(reader)
    coro.spawn(writer)
    coro.yield_and_schedule()
    rw_lock.write_unlock()
    coro._exit = 1

def writer():
    rw_lock.write_lock()
    rw_lock.write_unlock()

def reader():
    print 'reader locking'
    rw_lock.read_lock()
    print 'reader got lock'
    rw_lock.read_unlock()
    print 'reader done'

def unlocker():
    print 'unlocker'
    rw_lock.read_unlock()
    rw_lock.read_unlock()

coro.spawn(test_rw_lock)
coro.event_loop()
