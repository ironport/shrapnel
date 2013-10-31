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

"""Unittests for the tsc_time module."""

import struct
#import sysctl
import time
import unittest
from coro.clocks import tsc_time

class Test(unittest.TestCase):

    # Stub test until we have a working sysctl
    #def test_ticks_per_sec(self):
    #    freq = struct.unpack('I', sysctl.sysctl('machdep.tsc_freq'))[0]
    #    self.assertEqual(freq,
    #                     tsc_time.ticks_per_sec
    #                    )
    #    self.assertEqual(freq / 1000000,
    #                     tsc_time.ticks_per_usec
    #                    )

    def _assert_close(self, a, b, diff):
        low = a - diff
        high = a + diff

        self.assert_(low <= b <= high, '%r %r ~ %r' % (a, b, diff))

    def test_raw_conversion(self):
        now_t = tsc_time.now_tsc().tsc
        now_up = tsc_time.get_kernel_usec()
        now_p = now_up / 1000000
        now_fp = float(now_up) / 1000000

        # Conversion looses some accuracy.
        ticks_close = (tsc_time.ticks_per_sec / 10.0)
        p_close = 0
        up_close = 100000
        fp_close = 0.1

        self._assert_close(now_t,
                           tsc_time.usec_to_ticks(now_up),
                           ticks_close
                          )
        self._assert_close(now_up,
                           tsc_time.ticks_to_usec(now_t),
                           up_close
                          )
        self._assert_close(now_t,
                           tsc_time.usec_to_ticks_safe(now_up),
                           ticks_close
                          )
        self._assert_close(now_up,
                           tsc_time.ticks_to_usec_safe(now_t),
                           up_close
                          )
        self._assert_close(now_t,
                           tsc_time.sec_to_ticks(now_p),
                           tsc_time.ticks_per_sec
                          )
        self._assert_close(now_p,
                           tsc_time.ticks_to_sec(now_t),
                           p_close
                          )
        self._assert_close(now_fp,
                           tsc_time.ticks_to_fsec(now_t),
                           fp_close
                          )
        self._assert_close(now_t,
                           tsc_time.fsec_to_ticks(now_fp),
                           ticks_close
                          )

    def test_time_methods(self):
        t = tsc_time.now_tsc()
        now_up = tsc_time.get_kernel_usec()
        now_fp = float(now_up) / 1000000

        self.assertEqual(time.ctime(now_fp), t.ctime())
        self.assertEqual(time.localtime(now_fp), t.localtime())
        self.assertEqual(time.gmtime(now_fp), t.gmtime())
        self.assertEqual(time.strftime('%a %b %d %H:%M:%S %Y', time.localtime(now_fp)),
                         t.mkstr_local('%a %b %d %H:%M:%S %Y'))
        self.assertEqual(time.strftime('%a %b %d %H:%M:%S %Y', time.gmtime(now_fp)),
                         t.mkstr_utc('%a %b %d %H:%M:%S %Y'))

    def test_comparison(self):
        t = tsc_time.now_tsc()
        t2 = tsc_time.now_tsc()

        self.assert_(t2 > t)
        self.assert_(t < t2)
        self.assert_(t.tsc + 1 > t)
        self.assert_(t.tsc - 1 < t)
        self.assert_(t.tsc + 1L > t)
        self.assert_(t.tsc - 1L < t)
        # Floating point uses larger numbers because of a loss in precision
        # when converting to floating point, ex:
        # >>> float(28536304964998994L)
        # 28536304964998992.0
        self.assert_(t.tsc + 1000.0 > t)
        self.assert_(t.tsc - 1000.0 < t)

        t = tsc_time.now_posix_sec()
        time.sleep(2)
        t2 = tsc_time.now_posix_sec()

        self.assert_(t2 > t)
        self.assert_(t < t2)
        self.assert_(int(t) + 1 > t)
        self.assert_(int(t) - 1 < t)
        self.assert_(int(t) + 1L > t)
        self.assert_(int(t) - 1L < t)
        self.assert_(int(t) + 1.0 > t)
        self.assert_(int(t) - 1.0 < t)

        t = tsc_time.now_posix_usec()
        time.sleep(0.1)
        t2 = tsc_time.now_posix_usec()

        self.assert_(t2 > t)
        self.assert_(t < t2)
        self.assert_(int(t) + 1 > t)
        self.assert_(int(t) - 1 < t)
        self.assert_(int(t) + 1L > t)
        self.assert_(int(t) - 1L < t)
        self.assert_(int(t) + 1.0 > t)
        self.assert_(int(t) - 1.0 < t)

        t = tsc_time.now_posix_fsec()
        time.sleep(0.1)
        t2 = tsc_time.now_posix_fsec()

        self.assert_(t2 > t)
        self.assert_(t < t2)
        self.assert_(int(t) + 1 > t)
        self.assert_(int(t) - 1 < t)
        self.assert_(int(t) + 1L > t)
        self.assert_(int(t) - 1L < t)
        self.assert_(int(t) + 1.0 > t)
        self.assert_(int(t) - 1.0 < t)

    def test_math(self):
        t = tsc_time.now_tsc()

        self.assertEqual(t + 1, t.tsc + 1)
        self.assertEqual(t - 1, t.tsc - 1)
        self.assertEqual(t + 1L, t.tsc + 1)
        self.assertEqual(t - 1L, t.tsc - 1)
        # Removing floating point comparison because large floating point
        # numbers loose precision, ex:
        # >>> float(28536304964998994L)
        # 28536304964998992.0
        #self.assertEqual(t + 1.0, t.tsc + 1)
        #self.assertEqual(t - 1.0, t.tsc - 1)
        self.assertRaises(TypeError, lambda: t + 'hi')
        self.assertRaises(TypeError, lambda: t - 'hi')

        t = tsc_time.now_posix_sec()

        self.assertEqual(t + 1, t.as_posix_sec() + 1)
        self.assertEqual(t - 1, t.as_posix_sec() - 1)
        self.assertEqual(t + 1L, t.as_posix_sec() + 1)
        self.assertEqual(t - 1L, t.as_posix_sec() - 1)
        self.assertEqual(t + 1.0, t.as_posix_sec() + 1)
        self.assertEqual(t - 1.0, t.as_posix_sec() - 1)
        self.assertRaises(TypeError, lambda: t + 'hi')
        self.assertRaises(TypeError, lambda: t - 'hi')

        t = tsc_time.now_posix_usec()

        self.assertEqual(t + 1, t.as_posix_usec() + 1)
        self.assertEqual(t - 1, t.as_posix_usec() - 1)
        self.assertEqual(t + 1L, t.as_posix_usec() + 1)
        self.assertEqual(t - 1L, t.as_posix_usec() - 1)
        self.assertEqual(t + 1.0, t.as_posix_usec() + 1)
        self.assertEqual(t - 1.0, t.as_posix_usec() - 1)
        self.assertRaises(TypeError, lambda: t + 'hi')
        self.assertRaises(TypeError, lambda: t - 'hi')

        t = tsc_time.now_posix_fsec()

        # We lose some precision with double conversions done in C versus
        # Python's conversions.
        self._assert_close(t + 1, t.as_posix_fsec() + 1, 0.001)
        self._assert_close(t - 1, t.as_posix_fsec() - 1, 0.001)
        self._assert_close(t + 1L, t.as_posix_fsec() + 1, 0.001)
        self._assert_close(t - 1L, t.as_posix_fsec() - 1, 0.001)
        self._assert_close(t + 1.0, t.as_posix_fsec() + 1, 0.001)
        self._assert_close(t - 1.0, t.as_posix_fsec() - 1, 0.001)
        self.assertRaises(TypeError, lambda: t + 'hi')
        self.assertRaises(TypeError, lambda: t - 'hi')

    def test_types(self):
        t = tsc_time.now_tsc()

        self.assertEqual(int(t), t.tsc)
        self.assertEqual(long(t), t.tsc)
        self.assertEqual(float(t), float(t.tsc))

        t = tsc_time.now_posix_sec()

        self.assertEqual(int(t), t.as_posix_sec())
        self.assertEqual(long(t), t.as_posix_sec())
        self.assertEqual(float(t), float(t.as_posix_sec()))

        t = tsc_time.now_posix_usec()

        self.assertEqual(int(t), t.as_posix_usec())
        self.assertEqual(long(t), t.as_posix_usec())
        self.assertEqual(float(t), float(t.as_posix_usec()))

        t = tsc_time.now_posix_fsec()

        self.assertEqual(int(t), t.as_posix_sec())
        self.assertEqual(long(t), t.as_posix_sec())
        self.assertEqual(float(t), t.as_posix_fsec())

    def test_mktime(self):
        for mktime_type in (tsc_time.mktime_tsc,
                            tsc_time.mktime_posix_sec,
                            tsc_time.mktime_posix_usec,
                            tsc_time.mktime_posix_fsec):
            tt = time.localtime()
            t = mktime_type(tt)
            self.assertEqual(t.localtime(), tt)

    def test_from(self):
        now_tsc = tsc_time.now_tsc()

        self.assertEqual(now_tsc.tsc,
                         tsc_time.TSC_from_ticks(now_tsc.tsc).tsc)
        self.assertEqual(tsc_time.sec_to_ticks(now_tsc.as_posix_sec()),
                         tsc_time.TSC_from_posix_sec(now_tsc.as_posix_sec()).tsc)
        self.assertEqual(tsc_time.usec_to_ticks(now_tsc.as_posix_usec()),
                         tsc_time.TSC_from_posix_usec(now_tsc.as_posix_usec()).tsc)
        self.assertEqual(tsc_time.fsec_to_ticks(now_tsc.as_posix_fsec()),
                         tsc_time.TSC_from_posix_fsec(now_tsc.as_posix_fsec()).tsc)

        self.assertEqual(now_tsc.tsc,
                         tsc_time.Posix_from_ticks(now_tsc.tsc).tsc)
        self.assertEqual(tsc_time.sec_to_ticks(now_tsc.as_posix_sec()),
                         tsc_time.Posix_from_posix_sec(now_tsc.as_posix_sec()).tsc)
        self.assertEqual(tsc_time.usec_to_ticks(now_tsc.as_posix_usec()),
                         tsc_time.Posix_from_posix_usec(now_tsc.as_posix_usec()).tsc)
        self.assertEqual(tsc_time.fsec_to_ticks(now_tsc.as_posix_fsec()),
                         tsc_time.Posix_from_posix_fsec(now_tsc.as_posix_fsec()).tsc)

        self.assertEqual(now_tsc.tsc,
                         tsc_time.uPosix_from_ticks(now_tsc.tsc).tsc)
        self.assertEqual(tsc_time.sec_to_ticks(now_tsc.as_posix_sec()),
                         tsc_time.uPosix_from_posix_sec(now_tsc.as_posix_sec()).tsc)
        self.assertEqual(tsc_time.usec_to_ticks(now_tsc.as_posix_usec()),
                         tsc_time.uPosix_from_posix_usec(now_tsc.as_posix_usec()).tsc)
        self.assertEqual(tsc_time.fsec_to_ticks(now_tsc.as_posix_fsec()),
                         tsc_time.uPosix_from_posix_fsec(now_tsc.as_posix_fsec()).tsc)

        self.assertEqual(now_tsc.tsc,
                         tsc_time.fPosix_from_ticks(now_tsc.tsc).tsc)
        self.assertEqual(tsc_time.sec_to_ticks(now_tsc.as_posix_sec()),
                         tsc_time.fPosix_from_posix_sec(now_tsc.as_posix_sec()).tsc)
        self.assertEqual(tsc_time.usec_to_ticks(now_tsc.as_posix_usec()),
                         tsc_time.fPosix_from_posix_usec(now_tsc.as_posix_usec()).tsc)
        self.assertEqual(tsc_time.fsec_to_ticks(now_tsc.as_posix_fsec()),
                         tsc_time.fPosix_from_posix_fsec(now_tsc.as_posix_fsec()).tsc)

    def test_negative_time(self):
        now_tsc = tsc_time.now_tsc()

        diff = 10 * 60 * tsc_time.ticks_per_sec
        ago = now_tsc - diff

        self._assert_close(ago.as_posix_sec(),
                           now_tsc.as_posix_sec() - 10 * 60,
                           1
                          )
        self._assert_close(ago.as_posix_usec(),
                           now_tsc.as_posix_usec() - 10 * 60 * 1000000,
                           1000000
                          )
        self._assert_close(ago.as_posix_fsec(),
                           now_tsc.as_posix_fsec() - 10 * 60,
                           0.3
                          )

        # Microseconds in 1 year.
        diff = long(365 * 24 * 60 * 60 * 1000000)
        now_usec = tsc_time.now_posix_usec()
        ago = now_usec - diff

        self._assert_close(now_usec.as_posix_usec() - diff,
                           ago.as_posix_usec(),
                           10
                          )

        year_ago = now_usec.as_posix_usec() - diff
        year_ago_tsc = tsc_time.TSC_from_posix_usec(year_ago)

        self._assert_close(year_ago_tsc.as_posix_usec(),
                           year_ago,
                           10
                          )


if __name__ == '__main__':
    unittest.main()
