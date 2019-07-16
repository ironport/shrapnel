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
# ssh_random
#
# Consolidated location for getting random data.
#

from coro.sodium import randombytes
import math

def get_random_data (size):
    """get_random_data(size) -> str
    Gets <size> number of bytes of random data.
    """
    return randombytes (size)

def highest_bit(num):
    """highest_bit(num) -> n
    Determines the bit position of the highest bit in the given number.
    Example: 0x800000 returns 24.
    """
    try:
        return int(math.floor(math.log10(num) / math.log10(2))) + 1
    except OverflowError:
        assert(num == 0)
        return 0

# This was an alternate version of highest_bit, but the
# logarithm version seems to be a little faster.

highest_bit_map = {
    '0': 0,
    '1': 1,
    '2': 2,
    '3': 2,
    '4': 3,
    '5': 3,
    '6': 3,
    '7': 3,
    '8': 4,
    '9': 4,
    'A': 4,
    'B': 4,
    'C': 4,
    'D': 4,
    'E': 4,
    'F': 4,
}

def highest_bit2(num):
    """highest_bit(num) -> n
    Determines the bit position of the highest bit in the given number.
    Example: 0x800000 returns 24.
    """
    # Use a table for the high nibble, then count the number
    # of nibbles up to the highest one.  This algorithm is significantly faster
    # than shifting the number until it is zero.

    # Convert to long so that we don't have to test if it is an int or long
    # in order to accomodate for L at the end.
    h = hex(long(num))
    # Subtract 4 to accomodate for first two characters (0x) the last
    # character (L) and the high nibble character.
    return (len(h) - 4) * 4 + highest_bit_map[h[2]]

import unittest

class ssh_random_test_case(unittest.TestCase):
    pass

class highest_bit_test_case(ssh_random_test_case):

    def runTest(self):
        for x in xrange(300):
            self.assertEqual(highest_bit(x), highest_bit2(x))
        x = 144819228510396375480510966045726324197234443151241728654670685625305230385467763734653299992854300412367868856607501321634131298084648429649714452472261648519166487595581105734370788168033696455943547609540069712392591019911289209306656760054646817215504894551439102079913490941604156000063251698742214491563  # noqa
        self.assertEqual(highest_bit(x), highest_bit2(x))
        while x > 0:
            x = x / 2
            self.assertEqual(highest_bit(x), highest_bit2(x))

def suite():
    suite = unittest.TestSuite()
    suite.addTest(highest_bit_test_case())
    return suite

if __name__ == '__main__':
    unittest.main(module='ssh_random', defaultTest='suite')
