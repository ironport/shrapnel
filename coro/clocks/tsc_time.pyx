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

# $Header: /cvsroot/godspeed/python_modules/tsc_time.pyx,v 1.4 2007/03/20 00:51:42 ehuss Exp $

"""TSC time library.

Introduction
============
This module implements a "Time" object that is based on the TSC value of the
x86 processor. This is a monotonically increasing value that is somewhat
dependable (whereas system time may change).  It is also very high resolution
and very efficient to retrieve.

This library is designed to be as high-performance as possible.  If you use it
correctly, you can ensure your code maintains that high level of performance.

Objects
=======
There are 4 objects in this module all deriving from the base Time object.
They are:

- ``TSC``: TSC value
- ``Posix``: POSIX, seconds since 1970
- ``uPosix``: POSIX, microseconds since 1970
- ``fPosix``: POSIX, floating-point seconds since 1970

Each of these objects are relatively the same.  The main difference is when
adding or comparing the objects, they behave as their type describes.

The base Time object defines methods for converting the TSC value to another
type.  They are ``as_posix_sec``, ``as_posix_usec``, and ``as_posix_fsec``.

There are a three classes of functions in the module for creating these
objects. The ``now_*`` functions compute the current time.  The ``mktime_*``
functions convert a Python "time tuple" to a Time object.  The ``*_from_*``
functions take a raw value (TSC, Posix, etc.) and create a Time object.

Raw Conversions
===============
The module also provides methods for converting raw values from one type to
another. These are the ``*_to_*`` functions, and generally should not be needed
if your code uses Time objects throughout.

Wall Clock Synchronization
==========================
When the module is first imported, it captures the current wall-clock time and
TSC value.  This information is used for doing conversions between TSC and
Posix time. It is important to call the ``update_time_relation`` function
whenever the wall-clock is changed.  Also, it is a good idea to call it
periodically to retain accuracy.  This is necessary because the library uses
the ``ticks_per_sec`` value for conversions. This value is obtained from the
``machdep.tsc_freq`` sysctl, and may be slightly off (my system is about 0.002%
off which is about 10 minutes per year).  Long-term computations based on the
``ticks_per_sec`` value should not be trusted to be very accurate.

Accuracy and Precision
======================
The conversion functions use roughly imprecise, but faster integer arithmetic.
The reason it is inaccurate is because it uses the ticks_per_usec value which
is less accurate than ticks_per_sec.  To compute the inaccuracy, you can use
the formula::

    (1000000 / ticks_per_sec)

This is a rough estimate.  On my 3.5 GHz system, this is about 0.027% or about
2.3 hours per year.  Slower systems have less accuracy (about 0.09% for a 1 GHz
machine or about 8 hours per year).

To be more accurate, we would either need to use numbers larger than 64 bits
(bignums, Python Longs, 80-bit C doubles, etc.), but it would slow the
conversions down a little (for C doubles it was about 30% slower on my system).

TSC values that are significantly far from the current time should not be
trusted to be very accurate.

External C Access
=================
The C functions in this module are available for direct access from other C
extension modules.  For C modules, simply include "tsc_time.h" and call the
initialization function once.  For Pyrex modules, include
"tsc_time_include.pyx". See the respective files for more detail.

Signedness
==========
TSC values may be negative (to indicate a time before the computer booted). In
general, this library uses signed data types to avoid signed/unsigned
multiplication/division.  A particular exception is the `ticks_per_sec` value
because it is currently defined as a 32-bit number, and we need to support
machines with CPU's faster than 2GHz.

On most POSIX systems, time_t is a signed 32-bit integer (on some it is a
signed 64-bit integer, whose negative value extends past the beginning of the
universe). In theory, a signed 32-bit value can handle negative values from
1901 to 1970 and 1970 to 2038 positive.  Some foolish systems have attempted to
define time_t as an unsigned value to extend the overflow point to 2106, but
this is rare.

Notes
=====
The rate of the TSC value may change on systems with thermal and power
throttling. (though rumor has it some processors adjust the TSC rate when
auto-throttling to ensure it runs at a constant speed). This invalidates
assumptions made in this library, so do not use those features.

On SMP kernels, FreeBSD will synchronize the TSC value on all CPU's at
boot time, and the assumption is made that they will remain roughly in sync.
Rumor has it that some motherboards will attempt to keep the TSC value in
sync on all processors over time.  AMD CPU's are rumored to be especially
vulnerable to this.

RDTSC
=====
This is detailed low-level information about the rdtsc instruction that is used
to obtain the TSC value.

rdtsc - ReaD TimeStamp Counter

The cycle counter in the Pentium series of processors is incremented once for
every clock cycle.  It starts out as 0 on system boot. It is a 64-bit number,
and thus will wrap over in 292 years on a 2 gigahertz processor.  It should
keep counting unless the system goes into deep sleep mode.

FYI, the control registers on the Pentium can be configured to restrict RDTSC
to privileged level 0.

The RDTSC instruction is generally not synchronized.  Thus, with out of order
execution, it is possible for it to run ahead of other instructions that came
before it.  This is mainly only important if you are trying to do exact
profiling of instruction cycles.

Other Counters
==============
Most x86 systems have other hardware timers.  They all have different
frequencies, accuracies, performance characteristics, etc.  The following is a
list of alternate counters that we may want to investigate:

- Intel 8254 Interval Timer (i8254).  This was introduced in the IBM AT (the
  8253 was used in the IBM XT).
- ACPI (Advanced Configuration and Power Interface) counter (ACPI was
  introduced around 1996).
- HPET (High Precision Event Timer) introduced by Intel around 2004 as a
  replacement to the i8254.

Further Reading
===============
Some interesting papers:

- Timecounters: Efficient and precise timekeeping in SMP kernels:
  http://phk.freebsd.dk/pubs/timecounter.pdf
- TSC and Power Management Events on AMD Processors:
  http://www.opensolaris.org/os/community/performance/technical_docs/amd_tsc_power

TODO
====
- Investigate SMP drift over long periods of time.
- Find a way to detect if the current platform has thermal or power
  throttling, and whether or not it compensates the TSC rate to remain constant.
- machdep.tsc_freq is a 32-bit unsigned integer.  For systems with CPU's faster
  that 4 GHz, this is no longer sufficient.
- Get a better (more accurate) value of machdep.tsc_freq.  Investigate
  CLK_USE_TSC_CALIBRATION, CLK_USE_I8254_CALIBRATION, CLK_CALIBRATION_LOOP in
  FreeBSD kernel which use the mc146818A chip.  (CLK_USE_TSC_CALIBRATION seems
  to have disappeared, but is available in older kernels.)
- Write something that will periodically adjust the `ticks_per_sec` value to be
  more accurate, comparing against the wall clock assuming the wall clock is
  adjusted with NTP.  See djb's clockspeed for inspiration.

:Variables:
    - `ticks_per_sec`: Number of processor ticks per second.
    - `ticks_per_usec`: Number of processor ticks per microsecond.
    - `relative_usec_time`: Value of POSIX time (in microseconds) that relates
      to `relative_tsc_time`.
    - `relative_tsc_time`: Value of TSC counter that corresponds to
      `relative_usec_time`.
    - `relative_sec_time`: Value of POSIX time (in seconds) that relates to
      `relative_tsc_time`.
"""

include "python.pxi"
include "pyrex_helpers.pyx"

import time
from libc.stdint cimport uint64_t, int64_t, uint32_t
from libc.stddef cimport size_t
from libc.string cimport strlen
# cython does not have a libc/time.pxd yet
from xlibc cimport time
from libc cimport stdlib

cdef extern from "rdtsc.h":
    uint64_t _c_rdtsc "rdtsc" ()

cdef extern from "sys/sysctl.h":
    int sysctlbyname(char *name, void *oldp, size_t *oldlenp, void *newp,
                      size_t newlen)

IF UNAME_SYSNAME == "Linux":
    DEF _GNU_SOURCE=1
    cdef extern from "sched.h":
       int sched_getcpu()

# This is a pointer so that the time shifting functions can replace it.
cdef uint64_t (*c_rdtsc) ()
c_rdtsc = _c_rdtsc

###########################################################################
# Helper functions.
###########################################################################

cdef int64_t c_get_kernel_usec():
    global emulation_offset_usec
    cdef time.timeval tv_now

    time.gettimeofday(&tv_now, NULL)

    return ((<int64_t>tv_now.tv_sec) * 1000000 + tv_now.tv_usec) + emulation_offset_usec


cdef uint64_t get_ticks_per_sec() except -1:
    """Gets the number of cycles per second for the TSC.

    It uses sysctl to find the value.
    Returns the ticks per second on success, -1 on failure.
    """
    cdef uint64_t value
    cdef char buffer[128]
    cdef size_t buffer_size

    IF UNAME_SYSNAME == "Linux":
        current_cpu_number = sched_getcpu()
        f = open('/proc/cpuinfo')
        try:
            lines = f.readlines()
        finally:
            f.close()

        cpu_found = False
        cpu_speed_mhz = None
        for line in lines:
            if line.startswith('processor'):
                found_cpu_number = int(line.split(':')[-1].strip())
                if found_cpu_number == current_cpu_number:
                    cpu_found = True
                continue

            if not cpu_found:
                continue

            if line.startswith('cpu MHz'):
                cpu_speed_mhz = float(line.split(':')[-1].strip())
                break

        if cpu_speed_mhz is None:
            raise RuntimeError('failed to detect CPU frequency')

        return cpu_speed_mhz * 1000000

    buffer_size = sizeof(buffer)

    IF UNAME_SYSNAME == "Darwin":
        if sysctlbyname("machdep.tsc.frequency", <void *>&buffer[0], &buffer_size, NULL, 0) == -1:
            raise SystemError
    ELSE:
        # Leave this for backwards compatibility with 32/64-bit legacy systems
        if sysctlbyname("machdep.tsc_freq_new", <void *>&buffer[0], &buffer_size, NULL, 0) == -1:
            if sysctlbyname("machdep.tsc_freq", <void *>&buffer[0], &buffer_size, NULL, 0) == -1:
                # Not all systems have this sysctl that we can build on
                if stdlib.getenv("BUILDING") == NULL:
                    raise SystemError
                else:
                    return 2793008320

    if buffer_size == 4:
        value = (<uint32_t *>buffer)[0];
    else:
        if buffer_size == 8:
            value = (<uint64_t *>buffer)[0];
        else:
            raise SystemError
    return value

cdef int64_t _relative_usec_time
cdef int64_t _relative_sec_time
cdef int64_t _relative_tsc_time
# XXX: FreeBSD currently has this as "int" via sysctl.  Is this correct?  Is
# this correct on AMD64?  What shall we do once we exceed 4GHz?
cdef unsigned int _ticks_per_sec
cdef unsigned int _ticks_per_usec

ticks_per_sec = get_ticks_per_sec()
_ticks_per_sec = ticks_per_sec
_ticks_per_usec = _ticks_per_sec / 1000000

ticks_per_sec = _ticks_per_sec
ticks_per_usec = _ticks_per_usec

def get_kernel_usec():
    """Get the current time from the kernel in microseconds.

    Avoid using this unless absolutely necessary due to performance reasons.

    :Return:
        Returns the current time in microseconds.
    """
    return c_get_kernel_usec()

def rdtsc():
    """Return the current TSC value."""
    return c_rdtsc()

cdef object struct_time
struct_time = time.struct_time

cdef _mk_tt(time.tm * t):
    """Make a Python time tuple."""
    return struct_time((t.tm_year + 1900,
                        t.tm_mon + 1,
                        t.tm_mday,
                        t.tm_hour,
                        t.tm_min,
                        t.tm_sec,
                        (t.tm_wday + 6) % 7,
                        t.tm_yday + 1,
                        t.tm_isdst))

cdef _get_tt(tt, time.tm * t):
    """Convert a Python "time tuple" to a C tm struct."""
    if isinstance(tt, struct_time):
        # Convert to a tuple, this should be the most efficient way.
        tt = tt[:]
    elif not PyTuple_CheckExact(tt):
        raise TypeError('Expected tuple or struct_time, got %r.' % (type(tt),))

    if PyTuple_Size(tt) != 9:
        raise ValueError('Must be 9 element tuple, was %r.' % (tt,))

    t.tm_year  = PyTuple_GET_ITEM_SAFE(tt, 0)
    if t.tm_year < 1900:
        raise ValueError('2-digit years not supported.')
    t.tm_year  = t.tm_year - 1900
    t.tm_mon   = PyTuple_GET_ITEM_SAFE(tt, 1)
    t.tm_mon   = t.tm_mon - 1
    t.tm_mday  = PyTuple_GET_ITEM_SAFE(tt, 2)
    t.tm_hour  = PyTuple_GET_ITEM_SAFE(tt, 3)
    t.tm_min   = PyTuple_GET_ITEM_SAFE(tt, 4)
    t.tm_sec   = PyTuple_GET_ITEM_SAFE(tt, 5)
    t.tm_wday  = PyTuple_GET_ITEM_SAFE(tt, 6)
    t.tm_wday  = (t.tm_wday + 1) % 7
    t.tm_yday  = PyTuple_GET_ITEM_SAFE(tt, 7)
    t.tm_yday  = t.tm_yday - 1
    t.tm_isdst = PyTuple_GET_ITEM_SAFE(tt, 8)

cdef _strftime(char * format, time.tm * t):
    cdef char * buffer
    cdef size_t i
    cdef size_t buflen
    cdef size_t format_len

    format_len = strlen(format)

    i = 1024
    while 1:
        buffer = <char *> stdlib.malloc(i)
        if buffer == NULL:
            raise MemoryError
        try:
            buflen = time.strftime(buffer, i, format, t)
            if buflen > 0 or i >= 256 * format_len:
                # Copied from Python's strftime implementation.
                # If the result is 0, but we had a buffer that was 256 times
                # greater than the format len, then it's probably not
                # failing for lack of room.  It's probably just an empty
                # result.
                return PyString_FromStringAndSize(buffer, buflen)
        finally:
            stdlib.free(buffer)
        # Double the buffer size and try again.
        i = i*2

###########################################################################
# Time relativity used to keep the conversions accurate.
###########################################################################

cdef void c_update_time_relation():
    global relative_usec_time, relative_sec_time, relative_tsc_time
    global _relative_usec_time, _relative_sec_time, _relative_tsc_time
    _relative_tsc_time = <int64_t>c_rdtsc()
    _relative_usec_time = c_get_kernel_usec()
    _relative_sec_time = _relative_usec_time / 1000000
    relative_usec_time = _relative_usec_time
    relative_sec_time = _relative_sec_time
    relative_tsc_time = _relative_tsc_time

def update_time_relation():
    """Update the relative time stamps.

    You should call this whenever you think the clock has been changed. It
    should also be called periodically due to inaccuracies in the
    ``ticks_per_sec`` value.
    """
    c_update_time_relation()

c_update_time_relation()

###########################################################################
# Functions for simulating time changes.
###########################################################################
cdef int64_t emulation_offset_usec
cdef int64_t emulation_offset_tsc

cdef uint64_t _rdtsc_emulation():
    cdef int64_t s_temp
    s_temp = <int64_t>_c_rdtsc()
    s_temp + emulation_offset_tsc
    return s_temp

def set_time(posix_timestamp):
    """Emulate setting the system time to the given timestamp.

    This alters the library to behave as-if the current time is the given time.
    Note that this is different than changing the clock on the system.
    Changing the clock on the system does not affect TSC values, but this
    function does affect TSC values to behave as-if time has elapsed in the
    real world.

    :Parameters:
        - `posix_timestamp`: The POSIX timestamp (in seconds) to set the
          current time.  Pass in a value of 0 to disable emulation.
    """
    global emulation_offset_usec, emulation_offset_tsc, c_rdtsc
    cdef time.timeval tv_now
    cdef int64_t diff

    if posix_timestamp == 0:
        emulation_offset_usec = 0
        emulation_offset_tsc = 0
        c_rdtsc = _c_rdtsc
    else:
        time.gettimeofday(&tv_now, NULL)

        diff = posix_timestamp - tv_now.tv_sec
        emulation_offset_usec = diff * 1000000
        emulation_offset_tsc = diff * _ticks_per_sec
        c_rdtsc = _rdtsc_emulation

    c_update_time_relation()

def step_time(delta_secs):
    """Emulate changing the system time by the given number of seconds.

    See `set_time` for more detail.

    :Parameters:
        - `delta_secs`: The number of seconds to alter the current time.
    """
    global emulation_offset_usec, emulation_offset_tsc, c_rdtsc

    emulation_offset_usec = emulation_offset_usec + delta_secs*1000000
    emulation_offset_tsc = emulation_offset_tsc + delta_secs*_ticks_per_sec
    c_rdtsc = _rdtsc_emulation
    c_update_time_relation()

###########################################################################
# C raw conversion functions.
###########################################################################

cdef int64_t c_usec_to_ticks(int64_t t):
    return (t - _relative_usec_time) * _ticks_per_usec + _relative_tsc_time

cdef int64_t c_ticks_to_usec(int64_t t):
    # A more accurate, but slower version:
    # return (1000000.00 * (t-_relative_tsc_time)) / _ticks_per_sec + _relative_usec_time
    return (t - _relative_tsc_time) / _ticks_per_usec + _relative_usec_time

cdef int64_t c_sec_to_ticks(int64_t t):
    return (t - _relative_sec_time) * _ticks_per_sec + _relative_tsc_time

cdef int64_t c_ticks_to_sec(int64_t t):
    return ((t - _relative_tsc_time) / _ticks_per_usec + _relative_usec_time) / 1000000

cdef double c_ticks_to_fsec(int64_t t):
    return ((<double>(t - _relative_tsc_time)) / _ticks_per_usec + _relative_usec_time) / 1000000.0

cdef int64_t c_fsec_to_ticks(double t):
    return ((<int64_t>(t*1000000)) - _relative_usec_time) * _ticks_per_usec + _relative_tsc_time

###########################################################################
# Python-visable raw conversion functions.
###########################################################################

def usec_to_ticks(int64_t t):
    """Convert POSIX microseconds to ticks.

    :Parameters:
        - `t`: The time in POSIX microseconds.

    :Return:
        Returns the time in TSC ticks.
    """
    return c_usec_to_ticks(t)

def ticks_to_usec(int64_t t):
    """Convert ticks to POSIX microseconds.

    :Parameters:
        - `t`: The time in TSC.

    :Return:
        Returns the time in POSIX microseconds.
    """
    return c_ticks_to_usec(t)

def usec_to_ticks_safe(int64_t t):
    """Convert POSIX microseconds to ticks.

    This is "safe" in that if the value is zero, then it returns zero.

    :Parameters:
        - `t`: The time in POSIX microseconds.

    :Return:
        Returns the time in TSC ticks.
    """
    if t == 0:
        return 0
    else:
        return c_usec_to_ticks(t)

def ticks_to_usec_safe(int64_t t):
    """Convert ticks to POSIX microseconds.

    This is "safe" in that if the value is zero, then it returns zero.

    :Parameters:
        - `t`: The time in TSC.

    :Return:
        Returns the time in POSIX microseconds.
    """
    if t == 0:
        return 0
    else:
        return c_ticks_to_usec(t)

def sec_to_ticks(int64_t t):
    """Convert POSIX seconds to ticks.

    :Parameters:
        - `t`: The time in POSIX seconds (an integer).

    :Return:
        Returns the time in TSC ticks.
    """
    return c_sec_to_ticks(t)

def ticks_to_sec(int64_t t):
    """Convert ticks to POSIX seconds (an integer).

    :Parameters:
        - `t`: The time in TSC.

    :Return:
        Returns the time in POSIX microseconds.
    """
    return c_ticks_to_sec(t)

def ticks_to_fsec(int64_t t):
    """Convert ticks to POSIX seconds (a floating-point number).

    :Parameters:
        - `t`: The time in TSC.

    :Return:
        Returns the time in POSIX microseconds.
    """
    return c_ticks_to_fsec(t)

def fsec_to_ticks(double t):
    """Convert POSIX seconds (a floating-point number) to ticks.

    :Parameters:
        - `t`: The time in POSIX seconds (a float).

    :Return:
        Returns the time in TSC ticks.
    """
    return c_fsec_to_ticks(t)

###########################################################################
# Convenience functions for getting raw "now" values.
###########################################################################
def now_raw_tsc():
    """Get the current time as raw ticks."""
    return <int64_t>c_rdtsc()

def now_raw_posix_sec():
    """Get the current time as raw POSIX seconds."""
    return c_ticks_to_sec(<int64_t>c_rdtsc())

def now_raw_posix_usec():
    """Get the current time as raw POSIX microseconds."""
    return c_ticks_to_usec(<int64_t>c_rdtsc())

def now_raw_posix_fsec():
    """Get the current time as raw POSIX floating-point seconds."""
    return c_ticks_to_fsec(<int64_t>c_rdtsc())

###########################################################################
# Time objects.
###########################################################################

cdef time.time_t _asctime_cache_time
cdef object _asctime_cache_string

cdef class Time:

    """Base time object.

    Time object support the following operations:

    - Comparison.  Comparison is done using the native time object type. For
      example, "Posix" objects compare time in POSIX seconds.  Thus, if
      comparing two Posix objects that have slightly different TSC values, but
      due to the loss of precision have the same POSIX value, they will compare
      as equal.

      Comparison between different types is OK (Posix compared to TSC).  You
      can also compare a value with Python numeric literals (int, long, float,
      etc.).

    - Hashing.  Hashing is based on the object type.

    - Addition and subtraction.  This only works between two types of the exact
      same type (Posix and Posix for example), or with a Python numeric literal
      (int, long, float, etc.).

    - int/long/float.  Calling the int, long, or float functions on the object
      will return an int, long, or float value of the object's type.

    :IVariables:
        - `tsc`: The time in TSC.
    """

    # Defined in tsc_time.pxd.
    #cdef readonly int64_t tsc

    def __repr__(self):
        return '<%s: %s>' % (type(self).__name__, self.c_ctime(),)

    def as_posix_sec(self):
        """Return the time as POSIX seconds (an integer).

        :Return:
            Returns an integer as POSIX seconds.
        """
        return c_ticks_to_sec(self.tsc)

    def as_posix_usec(self):
        """Return the time as POSIX microseconds (a long).

        :Return:
            Returns a long as POSIX microseconds.
        """
        return c_ticks_to_usec(self.tsc)

    def as_posix_fsec(self):
        """Return the time as POSIX seconds (a floating-point number).

        :Return:
            Returns a float as POSIX seconds.
        """
        return c_ticks_to_fsec(self.tsc)

    def ctime(self):
        """Return the time as a string.

        This returns the time as a classic C-style 24-character time string
        in the local timezone in the format 'Sun Jun 20 23:21:05 1993'.  This
        does *not* include a trailing newline like C does.

        :Return:
            Returns a string of the local time.
        """
        return self.c_ctime()

    cdef c_ctime(self):
        cdef char * p
        cdef time.time_t posix_sec
        global _asctime_cache_string, _asctime_cache_time

        # We only compute this once a second.  Note that this is a
        # global, so it applies to all Time objects, but the most common
        # behavior is to look at the current time.
        posix_sec = c_ticks_to_sec(self.tsc)
        if posix_sec == _asctime_cache_time and _asctime_cache_string is not None:
            return _asctime_cache_string
        else:
            p = time.ctime(&posix_sec)
            p[24] = c'\0'
            _asctime_cache_string = p
            _asctime_cache_time = posix_sec
            return _asctime_cache_string

    def localtime(self):
        """Return a Python time-tuple in the local timezone.

        :Return:
            Returns a `time.struct_time` time-tuple in the local timezone.
        """
        return self.c_localtime()

    cdef c_localtime(self):
        cdef time.tm * t
        cdef time.time_t posix_sec

        posix_sec = c_ticks_to_sec(self.tsc)

        t = time.localtime(&posix_sec)
        return _mk_tt(t)

    def gmtime(self):
        """Return a Python time-tuple in UTC.

        :Return:
            Returns a `time.struct_time` time-tuple in UTC.
        """
        return self.c_gmtime()

    cdef c_gmtime(self):
        cdef time.tm * t
        cdef time.time_t posix_sec

        posix_sec = c_ticks_to_sec(self.tsc)

        t = time.gmtime(&posix_sec)
        return _mk_tt(t)

    def mkstr_local(self, format):
        """Convert time to a string in the local timezone.

        :Parameters:
            - `format`: The format that you want the string as. See the
              ``strftime`` function in the `time` module for more details.

        :Return:
            Returns a string in the local timezone.
        """
        return self.c_mkstr_local(format)

    cdef c_mkstr_local(self, char * format):
        cdef time.tm * t
        cdef time.time_t posix_sec

        posix_sec = c_ticks_to_sec(self.tsc)

        t = time.localtime(&posix_sec)
        return _strftime(format, t)

    def mkstr_utc(self, format):
        """Convert time to a string in UTC.

        :Parameters:
            - `format`: The format that you want the string as. See the
              ``strftime`` function in the `time` module for more details.

        :Return:
            Returns a string in UTC.
        """
        return self.c_mkstr_utc(format)

    cdef c_mkstr_utc(self, char * format):
        cdef time.tm * t
        cdef time.time_t posix_sec

        posix_sec = c_ticks_to_sec(self.tsc)

        t = time.gmtime(&posix_sec)
        return _strftime(format, t)

cdef class TSC(Time):

    """Time in TSC ticks."""

    def __hash__(self):
        return <int>self.tsc

    def __richcmp__(x, y, int op):
        cdef int64_t a, b

        if isinstance(x, Time):
            a = (<Time>x).tsc
        else:
            a = PyNumber_Int(x)

        if isinstance(y, Time):
            b = (<Time>y).tsc
        else:
            b = PyNumber_Int(y)

        if op == 0:
            return a < b
        elif op == 1:
            return a <= b
        elif op == 2:
            return a == b
        elif op == 3:
            return a != b
        elif op == 4:
            return a > b
        elif op == 5:
            return a >= b
        else:
            raise AssertionError(op)

    def __add__(x, y):
        cdef TSC t
        cdef TSC self
        cdef int int_value
        cdef long long longlong_value
        cdef double double_value

        if isinstance(x, TSC):
            self = x
            other = y
        else:
            assert isinstance(y, TSC)
            self = y
            other = x

        if PyInt_CheckExact(other):
            int_value = other
            t = TSC()
            t.tsc = self.tsc + int_value
            return t
        elif PyLong_CheckExact(other):
            longlong_value = other
            t = TSC()
            t.tsc = self.tsc + longlong_value
            return t
        elif PyFloat_CheckExact(other):
            double_value = other
            t = TSC()
            t.tsc = self.tsc + <int64_t>double_value
            return t
        else:
            raise TypeError('unsupported operand type(s) for +: %r and %r' % (type(x).__name__, type(y).__name__))

    def __sub__(x, y):
        cdef TSC t
        cdef TSC self
        cdef int int_value
        cdef long long longlong_value
        cdef double double_value

        if isinstance(x, TSC):
            self = x
            other = y
        else:
            assert isinstance(y, TSC)
            self = y
            other = x

        if PyInt_CheckExact(other):
            int_value = other
            t = TSC()
            t.tsc = self.tsc - int_value
            return t
        elif PyLong_CheckExact(other):
            longlong_value = other
            t = TSC()
            t.tsc = self.tsc - longlong_value
            return t
        elif PyFloat_CheckExact(other):
            double_value = other
            t = TSC()
            t.tsc = self.tsc - <int64_t>double_value
            return t
        else:
            raise TypeError('unsupported operand type(s) for -: %r and %r' % (type(x).__name__, type(y).__name__))

    def __int__(self):
        return self.tsc

    def __long__(self):
        return self.tsc

    def __float__(self):
        return PyFloat_FromDouble(<double>self.tsc)


cdef class Posix(Time):

    """Time in POSIX seconds."""

    def __hash__(self):
        return c_ticks_to_sec(self.tsc)

    def __richcmp__(x, y, int op):
        cdef time.time_t a, b

        if isinstance(x, Time):
            a = c_ticks_to_sec((<Time>x).tsc)
        else:
            a = PyNumber_Int(x)

        if isinstance(y, Time):
            b = c_ticks_to_sec((<Time>y).tsc)
        else:
            b = PyNumber_Int(y)

        if op == 0:
            return a < b
        elif op == 1:
            return a <= b
        elif op == 2:
            return a == b
        elif op == 3:
            return a != b
        elif op == 4:
            return a > b
        elif op == 5:
            return a >= b
        else:
            raise AssertionError(op)

    def __add__(x, y):
        cdef Posix t
        cdef Posix self
        cdef int int_value
        cdef long long longlong_value
        cdef double double_value

        if isinstance(x, Posix):
            self = x
            other = y
        else:
            assert isinstance(y, Posix)
            self = y
            other = x

        if PyInt_CheckExact(other):
            int_value = other
            t = Posix()
            t.tsc = self.tsc + int_value*_ticks_per_sec
            return t
        elif PyLong_CheckExact(other):
            longlong_value = other
            t = Posix()
            t.tsc = self.tsc + longlong_value*_ticks_per_sec
            return t
        elif PyFloat_CheckExact(other):
            double_value = other
            t = Posix()
            t.tsc = self.tsc + <int64_t>(double_value*<double>_ticks_per_sec)
            return t
        else:
            raise TypeError('unsupported operand type(s) for +: %r and %r' % (type(x).__name__, type(y).__name__))

    def __sub__(x, y):
        cdef Posix t
        cdef Posix self
        cdef int int_value
        cdef long long longlong_value
        cdef double double_value

        if isinstance(x, Posix):
            self = x
            other = y
        else:
            assert isinstance(y, Posix)
            self = y
            other = x

        if PyInt_CheckExact(other):
            int_value = other
            t = Posix()
            t.tsc = self.tsc - int_value*_ticks_per_sec
            return t
        elif PyLong_CheckExact(other):
            longlong_value = other
            t = Posix()
            t.tsc = self.tsc - longlong_value*_ticks_per_sec
            return t
        elif PyFloat_CheckExact(other):
            double_value = other
            t = Posix()
            t.tsc = self.tsc - <int64_t>(double_value*<double>_ticks_per_sec)
            return t
        else:
            raise TypeError('unsupported operand type(s) for -: %r and %r' % (type(x).__name__, type(y).__name__))

    def __int__(self):
        return c_ticks_to_sec(self.tsc)

    def __long__(self):
        return PyLong_FromLong(c_ticks_to_sec(self.tsc))

    def __float__(self):
        return PyFloat_FromDouble(<double>c_ticks_to_sec(self.tsc))

cdef class uPosix(Time):

    """Time in POSIX microseconds."""

    def __hash__(self):
        return <int>c_ticks_to_usec(self.tsc)

    def __richcmp__(x, y, int op):
        cdef int64_t a, b

        if isinstance(x, Time):
            a = c_ticks_to_usec((<Time>x).tsc)
        else:
            a = PyNumber_Int(x)

        if isinstance(y, Time):
            b = c_ticks_to_usec((<Time>y).tsc)
        else:
            b = PyNumber_Int(y)

        if op == 0:
            return a < b
        elif op == 1:
            return a <= b
        elif op == 2:
            return a == b
        elif op == 3:
            return a != b
        elif op == 4:
            return a > b
        elif op == 5:
            return a >= b
        else:
            raise AssertionError(op)

    def __add__(x, y):
        cdef uPosix t
        cdef uPosix self
        cdef int int_value
        cdef long long longlong_value
        cdef double double_value

        if isinstance(x, uPosix):
            self = x
            other = y
        else:
            assert isinstance(y, uPosix)
            self = y
            other = x

        if PyInt_CheckExact(other):
            int_value = other
            t = uPosix()
            t.tsc = self.tsc + int_value*_ticks_per_usec
            return t
        elif PyLong_CheckExact(other):
            longlong_value = other
            t = uPosix()
            t.tsc = self.tsc + longlong_value*_ticks_per_usec
            return t
        elif PyFloat_CheckExact(other):
            double_value = other
            t = uPosix()
            t.tsc = self.tsc + <int64_t>(double_value*<double>_ticks_per_usec)
            return t
        else:
            raise TypeError('unsupported operand type(s) for +: %r and %r' % (type(x).__name__, type(y).__name__))

    def __sub__(x, y):
        cdef uPosix t
        cdef uPosix self
        cdef int int_value
        cdef long long longlong_value
        cdef double double_value

        if isinstance(x, uPosix):
            self = x
            other = y
        else:
            assert isinstance(y, uPosix)
            self = y
            other = x

        if PyInt_CheckExact(other):
            int_value = other
            t = uPosix()
            t.tsc = self.tsc - int_value*_ticks_per_usec
            return t
        elif PyLong_CheckExact(other):
            longlong_value = other
            t = uPosix()
            t.tsc = self.tsc - longlong_value*_ticks_per_usec
            return t
        elif PyFloat_CheckExact(other):
            double_value = other
            t = uPosix()
            t.tsc = self.tsc - <int64_t>(double_value*<double>_ticks_per_usec)
            return t
        else:
            raise TypeError('unsupported operand type(s) for -: %r and %r' % (type(x).__name__, type(y).__name__))

    def __int__(self):
        return c_ticks_to_usec(self.tsc)

    def __long__(self):
        return c_ticks_to_usec(self.tsc)

    def __float__(self):
        return PyFloat_FromDouble(<double>c_ticks_to_usec(self.tsc))

cdef class fPosix(Time):

    """Time in POSIX seconds as a floating-point number."""

    def __hash__(self):
        return c_ticks_to_sec(self.tsc)

    def __richcmp__(x, y, int op):
        cdef double a, b

        if isinstance(x, Time):
            a = c_ticks_to_fsec((<Time>x).tsc)
        else:
            a = PyNumber_Float(x)

        if isinstance(y, Time):
            b = c_ticks_to_fsec((<Time>y).tsc)
        else:
            b = PyNumber_Float(y)

        if op == 0:
            return a < b
        elif op == 1:
            return a <= b
        elif op == 2:
            return a == b
        elif op == 3:
            return a != b
        elif op == 4:
            return a > b
        elif op == 5:
            return a >= b
        else:
            raise AssertionError(op)

    def __add__(x, y):
        cdef fPosix t
        cdef fPosix self
        cdef int int_value
        cdef long long longlong_value
        cdef double double_value

        if isinstance(x, fPosix):
            self = x
            other = y
        else:
            assert isinstance(y, fPosix)
            self = y
            other = x

        if PyInt_CheckExact(other):
            int_value = other
            t = fPosix()
            t.tsc = self.tsc + int_value*_ticks_per_sec
            return t
        elif PyLong_CheckExact(other):
            longlong_value = other
            t = fPosix()
            t.tsc = self.tsc + longlong_value*_ticks_per_sec
            return t
        elif PyFloat_CheckExact(other):
            double_value = other
            t = fPosix()
            t.tsc = self.tsc + <int64_t>(double_value*<double>_ticks_per_sec)
            return t
        else:
            raise TypeError('unsupported operand type(s) for +: %r and %r' % (type(x).__name__, type(y).__name__))

    def __sub__(x, y):
        cdef fPosix t
        cdef fPosix self
        cdef int int_value
        cdef long long longlong_value
        cdef double double_value

        if isinstance(x, fPosix):
            self = x
            other = y
        else:
            assert isinstance(y, fPosix)
            self = y
            other = x

        if PyInt_CheckExact(other):
            int_value = other
            t = fPosix()
            t.tsc = self.tsc - int_value*_ticks_per_sec
            return t
        elif PyLong_CheckExact(other):
            longlong_value = other
            t = fPosix()
            t.tsc = self.tsc - longlong_value*_ticks_per_sec
            return t
        elif PyFloat_CheckExact(other):
            double_value = other
            t = fPosix()
            t.tsc = self.tsc - <int64_t>(double_value*<double>_ticks_per_sec)
            return t
        else:
            raise TypeError('unsupported operand type(s) for -: %r and %r' % (type(x).__name__, type(y).__name__))

    def __int__(self):
        return c_ticks_to_sec(self.tsc)

    def __long__(self):
        return PyLong_FromLong(c_ticks_to_sec(self.tsc))

    def __float__(self):
        return c_ticks_to_fsec(self.tsc)


###########################################################################
# "Now" constructors
###########################################################################

def now_tsc():
    """Return a TSC object of the current time."""
    return c_now_tsc()

def now_posix_sec():
    """Return a Posix object of the current time."""
    return c_now_posix_sec()

def now_posix_usec():
    """Return a uPosix object of the current time."""
    return c_now_posix_usec()

def now_posix_fsec():
    """Return an fPosix object of the current time."""
    return c_now_posix_fsec()

cdef TSC c_now_tsc():
    cdef TSC t

    t = TSC()
    t.tsc = <int64_t>c_rdtsc()
    return t

cdef Posix c_now_posix_sec():
    cdef Posix t

    t = Posix()
    t.tsc = <int64_t>c_rdtsc()
    return t

cdef uPosix c_now_posix_usec():
    cdef uPosix t

    t = uPosix()
    t.tsc = <int64_t>c_rdtsc()
    return t

cdef fPosix c_now_posix_fsec():
    cdef fPosix t

    t = fPosix()
    t.tsc = <int64_t>c_rdtsc()
    return t

###########################################################################
# "mktime" constructors
###########################################################################

def mktime_tsc(tt):
    """Convert a Python time-tuple to a TSC object."""
    cdef TSC t
    cdef time.time_t posix
    cdef time.tm tm_st

    _get_tt(tt, &tm_st)
    posix = time.mktime(&tm_st)
    t = TSC()
    t.tsc = c_sec_to_ticks(posix)
    return t

def mktime_posix_sec(tt):
    """Convert a Python time-tuple to a Posix object."""
    cdef Posix t
    cdef time.time_t posix
    cdef time.tm tm_st

    _get_tt(tt, &tm_st)
    posix = time.mktime(&tm_st)
    t = Posix()
    t.tsc = c_sec_to_ticks(posix)
    return t

def mktime_posix_usec(tt):
    """Convert a Python time-tuple to a uPosix object."""
    cdef uPosix t
    cdef time.time_t posix
    cdef time.tm tm_st

    _get_tt(tt, &tm_st)
    posix = time.mktime(&tm_st)
    t = uPosix()
    t.tsc = c_sec_to_ticks(posix)
    return t

def mktime_posix_fsec(tt):
    """Convert a Python time-tuple to an fPosix object."""
    cdef fPosix t
    cdef time.time_t posix
    cdef time.tm tm_st

    _get_tt(tt, &tm_st)
    posix = time.mktime(&tm_st)
    t = fPosix()
    t.tsc = c_sec_to_ticks(posix)
    return t

###########################################################################
# "numeric" constructors
###########################################################################

def TSC_from_ticks(int64_t t):
    """Convert a raw TSC value to a TSC object."""
    cdef TSC v

    v = TSC()
    v.tsc = t
    return v

def TSC_from_posix_sec(time.time_t t):
    """Convert a raw POSIX seconds value to a TSC object."""
    cdef TSC v

    v = TSC()
    v.tsc = c_sec_to_ticks(t)
    return v

def TSC_from_posix_usec(int64_t t):
    """Convert a raw POSIX microseconds value to a TSC object."""
    cdef TSC v

    v = TSC()
    v.tsc = c_usec_to_ticks(t)
    return v

def TSC_from_posix_fsec(double t):
    """Convert a raw POSIX floating-point seconds value to a TSC object."""
    cdef TSC v

    v = TSC()
    v.tsc = c_usec_to_ticks(<int64_t>(t*1000000.0))
    return v

###########################################################################

def Posix_from_ticks(int64_t t):
    """Convert a raw TSC value to a Posix object."""
    cdef Posix v

    v = Posix()
    v.tsc = t
    return v

def Posix_from_posix_sec(time.time_t t):
    """Convert a raw POSIX seconds value to a Posix object."""
    cdef Posix v

    v = Posix()
    v.tsc = c_sec_to_ticks(t)
    return v

def Posix_from_posix_usec(int64_t t):
    """Convert a raw POSIX microseconds value to a Posix object."""
    cdef Posix v

    v = Posix()
    v.tsc = c_usec_to_ticks(t)
    return v

def Posix_from_posix_fsec(double t):
    """Convert a raw POSIX floating-point seconds value to a Posix object."""
    cdef Posix v

    v = Posix()
    v.tsc = c_usec_to_ticks(<int64_t>(t*1000000.0))
    return v

###########################################################################

def uPosix_from_ticks(int64_t t):
    """Convert a raw TSC value to a uPosix object."""
    cdef uPosix v

    v = uPosix()
    v.tsc = t
    return v

def uPosix_from_posix_sec(time.time_t t):
    """Convert a raw POSIX seconds value to a uPosix object."""
    cdef uPosix v

    v = uPosix()
    v.tsc = c_sec_to_ticks(t)
    return v

def uPosix_from_posix_usec(int64_t t):
    """Convert a raw POSIX microseconds value to a uPosix object."""
    cdef uPosix v

    v = uPosix()
    v.tsc = c_usec_to_ticks(t)
    return v

def uPosix_from_posix_fsec(double t):
    """Convert a raw POSIX floating-point seconds value to a uPosix object."""
    cdef uPosix v

    v = uPosix()
    v.tsc = c_usec_to_ticks(<int64_t>(t*1000000.0))
    return v

###########################################################################

def fPosix_from_ticks(int64_t t):
    """Convert a raw TSC value to an fPosix object."""
    cdef fPosix v

    v = fPosix()
    v.tsc = t
    return v

def fPosix_from_posix_sec(time.time_t t):
    """Convert a raw POSIX seconds value to an fPosix object."""
    cdef fPosix v

    v = fPosix()
    v.tsc = c_sec_to_ticks(t)
    return v

def fPosix_from_posix_usec(int64_t t):
    """Convert a raw POSIX microseconds value to an fPosix object."""
    cdef fPosix v

    v = fPosix()
    v.tsc = c_usec_to_ticks(t)
    return v

def fPosix_from_posix_fsec(double t):
    """Convert a raw POSIX floating-point seconds value to an fPosix object."""
    cdef fPosix v

    v = fPosix()
    v.tsc = c_usec_to_ticks(<int64_t>(t*1000000.0))
    return v

###########################################################################
# Provide access to other C modules.
###########################################################################

cdef void * __ptr_array[12]

__ptr_array[0] = &c_usec_to_ticks
__ptr_array[1] = &c_ticks_to_usec
__ptr_array[2] = &c_sec_to_ticks
__ptr_array[3] = &c_ticks_to_sec
__ptr_array[4] = &c_ticks_to_fsec
__ptr_array[5] = &c_fsec_to_ticks
__ptr_array[6] = &c_update_time_relation
__ptr_array[7] = &c_now_tsc
__ptr_array[8] = &c_now_posix_sec
__ptr_array[9] = &c_now_posix_usec
__ptr_array[10] = &c_now_posix_fsec
__ptr_array[11] = c_rdtsc

_extern_pointers = PyCObject_FromVoidPtr(<void *>__ptr_array, NULL)
