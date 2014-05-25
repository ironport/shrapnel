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

import struct
import operator
import sysctl
from functools import reduce

def get_current_mbufs():
    data = sysctl.sysctl ('kern.ipc.mbtypes')
    nelems = len(data) / 4
    nums = struct.unpack (nelems * 'l', data)
    free = nums[0]
    return free, reduce (operator.add, nums[1:])

def get():
    (peak_mbufs, clusters, spare, clfree,
     drops, wait, drain, mcfail, mpfail,
     msize, mclbytes, minclsize, mlen, mhlen
     ) = struct.unpack (14 * 'l', sysctl.sysctl ('kern.ipc.mbstat'))
    (max_mbufs,) = struct.unpack ('l', sysctl.sysctl ('kern.ipc.nmbufs'))
    (max_mbclusters,) = struct.unpack ('l', sysctl.sysctl ('kern.ipc.nmbclusters'))
    free_mbufs, current_mbufs = get_current_mbufs()
    return locals()
