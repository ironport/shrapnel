# -*- Mode: Python -*-

import unittest
import sys
from coro.asn1.ber import *
from coro.ldap.query import *

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
     ((C, 1, [(C, 3, ['a', 'b']), (C, 3, ['b', 'c']), (C, 3, ['c', 'd']), (C, 3, ['e', 'f']), (C, 3, ['f', 'g']), (C, 3, ['h', 'i'])]),
      50)),
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
    ('(a=some\\AAthing)',((C, 3, ['a', 'some\252thing']), 17)),
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
    (('('*100), QuerySyntaxError),
    # expression too complex
    (('(!' * 55) + '(x=y)' + (')' * 55), QuerySyntaxError),
    # expression not too complex
    (('(!' * 10) + '(x=y)' + (')' * 10),
     ((C, 2, [(C, 2, [(C, 2, [(C, 2, [(C, 2, [(C, 2, [(C, 2, [(C, 2, [(C, 2, [(C, 2, [(C, 3, ['x', 'y'])])])])])])])])])])]),
      28)),
    ]

class parse_query_test (unittest.TestCase):
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
    suite.addTest (parse_query_test())
    return suite

if __name__ == '__main__':
    unittest.main (defaultTest='suite')
