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

import os
import coro
from coro import aio_read

def t1():
    print 'expect [1024] * 10...'
    fd = os.open ('/kernel', os.O_RDONLY)
    # 10 1KB read requests
    requests = [
        (aio_read, (fd, 1024, int64(i * 102400)))
        for i in range (10)
    ]
    results = coro.in_parallel (requests)
    print [len(x) for x in results]
    print 'expect one OSError at the end...'
    fd = os.open ('/kernel', os.O_RDONLY)
    # 10 1KB read requests
    requests = [
        (aio_read, (fd, 1024, int64(i * 102400)))
        for i in range (10)
    ]
    requests.append (
        (aio_read, (-1, 1024, 1024))
    )
    try:
        coro.in_parallel (requests)
    except coro.InParallelError as e:
        for i in xrange (len(e.partial_results)):
            status, result = e.partial_results[i]
            if status is coro.SUCCESS:
                print 'job %2d:' % i, status, len(result)
            else:
                print 'job %2d:' % i, status, result
    else:
        raise SystemError("expected an exception")

if __name__ == '__main__':
    import backdoor
    coro.spawn (backdoor.serve)
    coro.spawn (t1)
    coro.event_loop (30.0)
