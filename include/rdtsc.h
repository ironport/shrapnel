/*
 Copyright (c) 2002-2011 IronPort Systems and Cisco Systems

 Permission is hereby granted, free of charge, to any person obtaining a copy  
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights  
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell 
 copies of the Software, and to permit persons to whom the Software is 
 furnished to do so, subject to the following conditions:

 The above copyright notice and this permission notice shall be included in 
 all copies or substantial portions of the Software.

 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
 AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 SOFTWARE.
*/

#ifndef _RDTSC_H_
#define _RDTSC_H_

/*
  rdtsc - ReaD TimeStamp Counter
  The cycle counter in the Pentium series of processors is incremented
  once for every clock cycle.  It starts out as 0 on system boot.
  It is a 64-bit number, and thus will wrap over in 292 years on a
  2 gigahertz processor.  It should keep counting unless the system
  goes into deep sleep mode.

  There is still some uncertainty about the P4 Xeon processor which
  has the ability to lower its clock cycle when a temperature
  threshold is met.  Does this also change the frequency of the TSC?

  FYI, the control registers on the Pentium can be configured to
  restrict RDTSC to privileged level 0.

  The RDTSC instruction is generally not synchronized.  Thus, with
  out of order execution, it is possible for it to run ahead of
  other instructions that came before it.  This is mainly only important
  if you are trying to do exact profiling of instruction cycles.

  I for the life of me can't find the number of actual cycles it takes
  to read the counter for the Pentium 4.  It's 11 cycles on the AMD
  Athlon.

  FreeBSD does not use the TSC for two apparent reasons: It is difficult
  to synchronize on an SMP machine, and it is difficult to account for
  time on a machine with APM enabled.  Neither of these should affect us.

  Some notes about FreeBSD and frequency counters:
  - The TSC frequency can be found via sysctl as machdep.tsc_freq.
  - FreeBSD will not bother to compute tsc_freq if you are building an SMP
    kernel, or you have APM enabled.
  - By default, FreeBSD will assume the i8254 timer frequency is 1193182
  - If you compile with CLK_USE_I8254_CALIBRATION, it will try to determine
    what the actual i8254 frequency is using the mc146818A chip.
  - If you compile with CLK_USE_TSC_CALIBRATION, it will try to determine
    what the actual TSC frequency is using the mc146818A chip.  Otherwise
    it will use a less acurate approximation using the i8254 chip.
  - If you compile with CLK_CALIBRATION_LOOP, then during bootup it will
    recompute the clock frequencies over and over again until you press
    a key on the console (debugging to see if the clock calibration
    routines are correct?).
*/

static inline
uint64_t
rdtsc(void)
{
  uint32_t a, d;

  asm volatile ("rdtsc" : "=a"(a), "=d"(d));
  return (((uint64_t) d << 32) | a);
}

#endif /* _RDTSC_H_ */
