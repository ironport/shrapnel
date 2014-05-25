# -*- Mode: Python -*-

import sys
import unittest
W = sys.stderr.write

# exhaustively test the new generator-based read_stream

# test-driving a new buffered_stream idea here...
class buffered_stream:

    def __init__ (self, producer):
        self.producer = producer
        self.buffer = ''
        self.pos = 0

    # This version avoids repeatedly slicing/copying self.buffer in
    #   the case where a large buffer holds many 'lines'.  The final
    #   speedup is only ~25%, though, so it may not be worth folding
    #   in.  Note: I've also made a Cython version of this.
    def gen_read_until (self, delim):
        "generate pieces of input up to and including <delim>, then StopIteration"
        ld = len(delim)
        m = 0
        while True:
            if self.pos == len(self.buffer):
                self.buffer = self.producer()
                self.pos = 0
                if not self.buffer:
                    # eof
                    yield ''
                    return
            i = self.pos
            lb = len(self.buffer)
            while i < lb:
                if self.buffer[i] == delim[m]:
                    m += 1
                    if m == ld:
                        yield self.buffer[self.pos:i + 1]
                        self.pos = i + 1
                        return
                else:
                    m = 0
                i += 1
            block, self.buffer = self.buffer[self.pos:], ''
            self.pos = 0
            yield block

    def read_until (self, delim, join=True):
        "read until <delim>.  return a list of parts unless <join> is True"
        result = (x for x in self.gen_read_until (delim))
        if join:
            return ''.join (result)
        else:
            return result

    def flush (self):
        "flush this stream's buffer"
        result, self.buffer = self.buffer, ''
        self.pos = 0
        return result

    def read_line (self, delim='\r\n'):
        "read a CRLF-delimited line from this stream"
        return self.read_until (delim)

import string
from random import randrange as R

def make_delim (n):
    return string.letters[:n]

# simulate a series of 'lines'
def make_line_data (delim_size, count=10000):
    delim = make_delim (delim_size)
    r = []
    for i in range (count):
        r.append ('0' * R (20, 150))
        r.append (delim)
    return ''.join (r)

# simulate an smtp stream
# XXX write tests against this!
def make_smtp_data (count=1000):
    delim0 = '\r\n'
    delim1 = '\r\n.\r\n'
    r = []
    # count mail messages
    for i in range (count):
        # 5 to 100 header lines/commands
        for i in R (5, 100):
            # each 15 to 200 chars long
            r.append ('0' * R (15, 200))
            r.append (delim0)
        # followed by message content of 300-15k
        r.append ('1' * R (300, 15000))
        r.append (delim1)
    return ''.join (r)

def str_prod (s, lo, hi=None):
    # string producer, make chunks of size in the range lo, hi (or just <lo>)
    i = 0
    ls = len(s)
    while i < ls:
        if hi is None:
            size = lo
        else:
            size = R (lo, hi)
        yield s[i:i + size]
        i += size

import re
data_re = re.compile ('^0+$')

def read_lines (g, delim):
    r = []
    ld = len(delim)
    while True:
        line = g.read_line (delim)
        if not line:
            break
        else:
            assert line[-ld:] == delim
            assert data_re.match (line[:-ld])
            r.append (line[:-ld])
    # emulate str.split()
    r.append ('')
    return r

class Test (unittest.TestCase):

    def t_line_0 (self, lines0, delim, lo, hi):
        s = buffered_stream (str_prod (lines0, lo, hi).next)
        lines1 = read_lines (s, delim)
        lines2 = lines0.split (delim)
        self.assertEqual (lines1, lines2)

    def t_line_1 (self, delim, lines0):
        t0 = self.t_line_0
        print ' fixed size, small'
        for i in range (1, 20):
            t0 (lines0, delim, i, i + 1)
        print ' random size, small'
        for i in range (1, 20):
            t0 (lines0, delim, i, i + 20)
        print ' 1000 byte buffer'
        t0 (lines0, delim, 1000, None)
        print ' 10000 byte buffer'
        t0 (lines0, delim, 10000, None)

    def test_4 (self):
        print 'delim_size == 4'
        delim = make_delim (4)
        lines0 = make_line_data (4)
        self.t_line_1 (delim, lines0)

    def test_1 (self):
        print 'delim_size == 1'
        delim = make_delim (1)
        lines0 = make_line_data (1)
        self.t_line_1 (delim, lines0)

    def test_20 (self):
        print 'delim_size == 20'
        delim = make_delim (20)
        lines0 = make_line_data (20)
        self.t_line_1 (delim, lines0)

if __name__ == '__main__':
    unittest.main()
