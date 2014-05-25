# Copyright (c) 2002-2012 IronPort Systems and Cisco Systems
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

#
# ssh_mpint
#
# Routines to handle SSH multiple-precision integers.
#

import struct

def pack_mpint(n):
    """pack_mpint(n) -> string
    Multiple-Precision Integer
    Packs a python long into a big endian string.
    """
    # Per the spec:
    # - two's compliment
    # - big-endian
    # - negative numbers have MSB of the first byte set
    # - if MSB would be set in a positive number, then preceed with a zero byte
    # - Unnecessary leading bytes with the value 0 or 255 MUST NOT be included.
    # - Zero stored as four 0 bytes.

    # This is very inefficient.
    s = []
    x = long(n)
    if x == 0:
        return ''
    elif x < 0:
        while 1:
            s.append(struct.pack('>L', x & 0xffffffffL))
            if x == -1:
                break
            x = x >> 32
    else:
        while x > 0:
            s.append(struct.pack('>L', x & 0xffffffffL))
            x = x >> 32
    s.reverse()
    s = ''.join(s)

    if s[0] == '\0':
        # Remove extra leading zeros.
        # This is a positive number.
        count = 0
        for i in s:
            if i != '\0':
                break
            count += 1
        # If the MSB is set, pad with a zero byte.
        if ord(s[count]) & 128:
            s = s[count - 1:]
        else:
            s = s[count:]
    elif s[0] == '\377' and n < 0:
        # Remove extra leading ones.
        # This is a negative number.
        for x in xrange(len(s)):
            i = s[x]
            if i != '\377':
                break
        # If the MSB is not set, then we need to sign-extend and make sure
        # there is another byte of all ones.
        if ord(s[x]) & 128:
            s = s[x:]
        else:
            s = s[x - 1:]

    # If the MSB is set and this is a positive number, pad with a zero.
    if n > 0 and ord(s[0]) & 128:
        s = '\0' + s
    return s

def unpack_mpint(mpint):
    """unpack_mpint(mpint) -> long
    Unpacks a multiple-precision string.
    """
    if len(mpint) % 4:
        # Need to pad it so that it is a multiple of 4.
        pad = 4 - (len(mpint) % 4)
        if ord(mpint[0]) & 128:
            # Negative number
            mpint = '\377' * pad + mpint
            struct_format = '>i'
        else:
            # Positive number
            mpint = '\0' * pad + mpint
            struct_format = '>I'
    else:
        if mpint and ord(mpint[0]) & 128:
            # Negative
            struct_format = '>i'
        else:
            # Positive
            struct_format = '>I'
    result = 0L
    for x in xrange(0, len(mpint), 4):
        result = (result << 32) | struct.unpack(struct_format, mpint[x: x + 4])[0]
    return result

import unittest

class ssh_packet_test_case(unittest.TestCase):
    pass

class mpint_test_case(ssh_packet_test_case):

    def runTest(self):
        self.check(0, '')
        self.check(0x9a378f9b2e332a7L, '\x09\xa3\x78\xf9\xb2\xe3\x32\xa7')
        self.check(0x80L, '\0\x80')
        self.check(-0x1234L, '\xed\xcc')
        self.check(-0xdeadbeefL, '\xff\x21\x52\x41\x11')
        self.check(0xffffffffL, '\0\xff\xff\xff\xff')
        self.check(-0xffffffffL, '\xff\0\0\0\x01')
        self.check(-1L, '\377')

    def check(self, num, string):
        self.assertEqual(pack_mpint(num), string)
        self.assertEqual(unpack_mpint(string), num)

def suite():
    suite = unittest.TestSuite()
    suite.addTest(mpint_test_case())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
