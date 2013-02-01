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

# This include file makes it possible to directly access the C functions from
# the tsc_time module.  To use it, you need to put this at the top of your
# Pyrex file:
#
#     cimport libc
#     include "python.pxi"
#     include "tsc_time_include.pyx"
#
# This will also implicitly cimport the tsc_time module so that you can have
# direct access to the type objects.  This allows you to do something like this:
#
#     cdef tsc_time.TSC t
#     t = now_tsc()
#     print t.tsc
#
# This will allow direct C access to the member variables of the Time objects.

cimport coro.clocks.tsc_time as tsc_time
from libc.stdint cimport int64_t

cdef extern from "tsc_time.h":

    # Raw conversion functions.
    int64_t  c_usec_to_ticks "usec_to_ticks" (int64_t)
    int64_t  c_ticks_to_usec "ticks_to_usec" (int64_t)
    int64_t  c_sec_to_ticks  "sec_to_ticks"  (int64_t)
    int64_t  c_ticks_to_sec  "ticks_to_sec"  (int64_t)
    double   c_ticks_to_fsec "ticks_to_fsec" (int64_t)
    int64_t  c_fsec_to_ticks "fsec_to_ticks" (double)
    void     c_update_time_relation "update_time_relation" ()
    int64_t  c_rdtsc         "rdtsc"         ()

    # Constructors.
    tsc_time.TSC now_tsc()
    tsc_time.Posix now_posix_sec()
    tsc_time.uPosix now_posix_usec()
    tsc_time.fPosix now_posix_fsec()

    int init_tsc_time_pointers() except -1

init_tsc_time_pointers()
