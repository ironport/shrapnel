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

# -*- Mode: Python -*-

from _ldap import *
import sys
import tb
import pprint
import unittest

class _ldap_test_case (unittest.TestCase):
    pass

class protos_test (_ldap_test_case):

    # you need the protos c06-ldapv3-enc-r1 test suite
    # to run this test...

    def runTest (self):
        i = 0
        while True:
            try:
                data = open (('%08d' % n), 'rb').read()
                try:
                    pprint.pprint (decode (data))
                except:
                    sys.stderr.write ('%4d %r\n' % (n, tb.traceback_string()))
            except IOError:
                break
            else:
                i += 1

class integer_test (_ldap_test_case):

    def runTest (self):
        # test small integers
        for i in range (-1000, 1000):
            self.assertEqual (decode (INTEGER (i))[0], i)
        # test larger integers
        for i in range (1000000, 2000000, 50):
            self.assertEqual (decode (INTEGER (i))[0], i)
        # test larger integers
        for i in range (-2000000, -1000000, 50):
            self.assertEqual (decode (INTEGER (i))[0], i)
        # test long integers
        for i in range (1000000, 2000000, 50):
            self.assertEqual (decode (INTEGER (i))[0], i)
        big = 2038490283059834505983450695834059639085793847509834752039485034967489769487694856
        self.assertEqual (decode (INTEGER (big))[0], big)

C = 'context'

pq_tests = [
    # simple equality
    ('(xxx=yyy)',
     ((C, 3, ['xxx', 'yyy']),
      12)),
    # simple expression, plus 'present'
    ('(|(xx=y)(zz=*))',
     ((C, 1, [(C, 3, ['xx', 'y']), (C, 7, 'zz')]),
      15)),
    # nary expressions
    ('(|(a=b)(b=c)(c=d)(e=f)(f=g)(h=i))',
     ((C, 1, [(C, 3, ['a', 'b']), (C, 3, ['b', 'c']), (C, 3, ['c', 'd']), (C, 3, ['e', 'f']),
      (C, 3, ['f', 'g']), (C, 3, ['h', 'i'])]), 50)),
    ('(|(!(a=*))(&(b=c)(d=e))(x<=y))',
     ((C, 1, [(C, 2, [(C, 7, 'a')]), (C, 0, [(C, 3, ['b', 'c']), (C, 3, ['d', 'e'])]), (C, 6, ['x', 'y'])]),
      33)),
    # approximate match
    ('(zz~=yy)', ((C, 8, ['zz', 'yy']), 10)),
    # substring
    ('(a=ins*tiga*tor)', ((C, 4, ['a', [(C, 0, 'ins'), (C, 1, 'tiga'), (C, 2, 'tor')]]), 23)),
    ('(a=*y)', ((C, 4, ['a', [(C, 2, 'y')]]), 10)),
    ('(a=y*)', ((C, 4, ['a', [(C, 0, 'y')]]), 10)),
    ('(a=*y*)', ((C, 4, ['a', [(C, 1, 'y')]]), 10)),
    ('(a=*x*y)', ((C, 4, ['a', [(C, 1, 'x'), (C, 2, 'y')]]), 13)),
    ('(a=*x*y*)', ((C, 4, ['a', [(C, 1, 'x'), (C, 1, 'y')]]), 13)),
    ('(a=*x*y*z)', ((C, 4, ['a', [(C, 1, 'x'), (C, 1, 'y'), (C, 2, 'z')]]), 16)),
    # syntax errors
    ('(a=', QuerySyntaxError),
    ('(a<b)', QuerySyntaxError),
    # good hex escape
    ('(a=some\\AAthing)', ((C, 3, ['a', 'some\252thing']), 17)),
    # bad hex escape
    ('(a=some\\AZthing)', QuerySyntaxError),
    # upper/lower case hex escape
    ('(a=xy\\Aaz)', ((C, 3, ['a', 'xy\252z']), 11)),
    # escaped splat
    ('(a=x*y\\2az)', ((C, 4, ['a', [(C, 0, 'x'), (C, 2, 'y*z')]]), 15)),
    # illegal splat
    ('(a~=sam*son)', QuerySyntaxError),
    # junk/illegal
    ('junk', QuerySyntaxError),
    # lots of parens
    (('(' * 100), QuerySyntaxError),
    # expression too complex
    (('(!' * 55) + '(x=y)' + (')' * 55), QuerySyntaxError),
    # expression not too complex
    (('(!' * 10) + '(x=y)' + (')' * 10),
     ((C, 2, [(C, 2, [(C, 2, [(C, 2, [(C, 2, [(C, 2, [(C, 2, [(C, 2,
       [(C, 2, [(C, 2, [(C, 3, ['x', 'y'])])])])])])])])])])]), 28)),
]

class parse_query_test (_ldap_test_case):
    def runTest (self):
        for q, e in pq_tests:
            try:
                self.assertEqual (decode (parse_query (q)), e)
            except AssertionError:
                raise
            except:
                self.assertEqual (sys.exc_info()[0], e)

def suite():
    suite = unittest.TestSuite()
    suite.addTest (integer_test())
    suite.addTest (parse_query_test())
    return suite

if __name__ == '__main__':
    unittest.main (defaultTest='suite')
