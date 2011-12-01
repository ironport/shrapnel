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

cdef extern from "sys/time.h":

    # already defined...
    #cdef struct timeval:
    #    long tv_sec
    #    long tv_usec

    void timeradd (timeval *a, timeval *b, timeval *res)
    void timersub (timeval *a, timeval *b, timeval *res)
    void timerclear (timeval *tvp)

cdef extern from "sys/resource.h":
    cdef struct _rusage "rusage":
        timeval ru_utime  # user time used
        timeval ru_stime  # system time used
        long ru_maxrss    # max resident set size
        long ru_ixrss     # integral shared text memory size
        long ru_idrss     # integral unshared data size
        long ru_isrss     # integral unshared stack size
        long ru_minflt    # page reclaims
        long ru_majflt    # page faults
        long ru_nswap     # swaps
        long ru_inblock   # block input operations
        long ru_oublock   # block output operations
        long ru_msgsnd    # messages sent
        long ru_msgrcv    # messages received
        long ru_nsignals  # signals received
        long ru_nvcsw     # voluntary context switches
        long ru_nivcsw    # involuntary context switches

    int getrusage (int who, _rusage * addr)

cdef class rusage:

    cdef _rusage r

    def __init__ (self):
        self.clear()

    cdef clear (self):
        memset (&self.r, 0, sizeof(self.r))

    def __add__ (_a, _b):
        cdef rusage a, b, c
        # XXX docs say I should test types manually, and "return NotImplemented"
        #    if I can't handle the combo.  Wonder what happens in this case...
        a = _a
        b = _b
        c = rusage()
        timeradd (&(a.r.ru_utime),&(b.r.ru_utime),&(c.r.ru_utime))
        timeradd (&(a.r.ru_stime),&(b.r.ru_stime),&(c.r.ru_stime))
        c.r.ru_maxrss    = a.r.ru_maxrss
        c.r.ru_minflt    = a.r.ru_minflt    + b.r.ru_minflt
        c.r.ru_majflt    = a.r.ru_majflt    + b.r.ru_majflt
        c.r.ru_nswap     = a.r.ru_nswap     + b.r.ru_nswap
        c.r.ru_inblock   = a.r.ru_inblock   + b.r.ru_inblock
        c.r.ru_oublock   = a.r.ru_oublock   + b.r.ru_oublock
        c.r.ru_msgsnd    = a.r.ru_msgsnd    + b.r.ru_msgsnd
        c.r.ru_msgrcv    = a.r.ru_msgrcv    + b.r.ru_msgrcv
        c.r.ru_nsignals  = a.r.ru_nsignals  + b.r.ru_nsignals
        c.r.ru_nvcsw     = a.r.ru_nvcsw     + b.r.ru_nvcsw
        c.r.ru_nivcsw    = a.r.ru_nivcsw    + b.r.ru_nivcsw
        return c

    def __sub__ (_a, _b):
        cdef rusage a, b, c
        a = _a
        b = _b
        c = rusage()
        timersub (&(a.r.ru_utime),&(b.r.ru_utime),&(c.r.ru_utime))
        timersub (&(a.r.ru_stime),&(b.r.ru_stime),&(c.r.ru_stime))
        c.r.ru_maxrss    = a.r.ru_maxrss
        c.r.ru_minflt    = a.r.ru_minflt    - b.r.ru_minflt
        c.r.ru_majflt    = a.r.ru_majflt    - b.r.ru_majflt
        c.r.ru_nswap     = a.r.ru_nswap     - b.r.ru_nswap
        c.r.ru_inblock   = a.r.ru_inblock   - b.r.ru_inblock
        c.r.ru_oublock   = a.r.ru_oublock   - b.r.ru_oublock
        c.r.ru_msgsnd    = a.r.ru_msgsnd    - b.r.ru_msgsnd
        c.r.ru_msgrcv    = a.r.ru_msgrcv    - b.r.ru_msgrcv
        c.r.ru_nsignals  = a.r.ru_nsignals  - b.r.ru_nsignals
        c.r.ru_nvcsw     = a.r.ru_nvcsw     - b.r.ru_nvcsw
        c.r.ru_nivcsw    = a.r.ru_nivcsw    - b.r.ru_nivcsw
        return c

    def get (self):
        getrusage (0, &self.r)

    def set (self, rusage other):
        memcpy (&self.r, &other.r, sizeof(_rusage))

    def __repr__ (self):
        return "<%ld.%06ld %ld.%06ld %ld %ld %ld %ld %ld %ld %ld %ld %ld %ld %ld>" % (
            self.r.ru_utime.tv_sec,
            self.r.ru_utime.tv_usec,
            self.r.ru_stime.tv_sec,
            self.r.ru_stime.tv_usec,
            self.r.ru_maxrss,
            self.r.ru_minflt,
            self.r.ru_majflt,
            self.r.ru_nswap,
            self.r.ru_inblock,
            self.r.ru_oublock,
            self.r.ru_msgsnd,
            self.r.ru_msgrcv,
            self.r.ru_nsignals,
            self.r.ru_nvcsw,
            self.r.ru_nivcsw
            )
