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
# ssh.keys.ber
#
# Very simple ASN.1 BER decoder used for SSH private keys.
# This implements more than is necessary for SSH, but not the entire
# ASN.1 standard.
#

import sys
sys.stderr.write ('FIX ber.py to use coro.asn1.ber\n')

__version__ = '$Revision: #1 $'

# flags for BER tags
FLAGS_UNIVERSAL       = 0x00
FLAGS_STRUCTURED      = 0x20
FLAGS_APPLICATION     = 0x40
FLAGS_CONTEXT         = 0x80
FLAGS_PRIVATE         = 0xC0

# universal BER tags
TAGS_INTEGER                   = 0x02
TAGS_OCTET_STRING              = 0x04
TAGS_SEQUENCE                  = 0x10 | FLAGS_STRUCTURED

class DecodeError (Exception):
    pass

class InsufficientData (DecodeError):
    pass

class InvalidData (DecodeError):
    pass

class UnknownTag (DecodeError):
    pass

# SAFETY NOTE: it's important for each decoder to correctly handle length == zero.

def decode_string(s, pos, length):
    # caller guarantees sufficient data in <s>
    result = s[pos:pos+length]
    pos += length
    return result, pos

def decode_integer(s, pos, length):
    if length == 0:
        return 0, pos
    else:
        n = long(ord(s[pos]))
        if n & 0x80:
            # negative
            n = n - 0x100
        length -= 1
        while length:
            pos += 1
            n = (n << 8) | ord(s[pos])
            length -= 1
        # advance past the last byte
        pos += 1
        return n, pos

def decode_structured(s, pos, length):
    start = pos
    end = start + length
    result = []
    if length:
        while pos < end:
            item, pos = decode (s, pos, end)
            result.append(item)
    return result, pos

# can an asn1 string *end* with a length?  i.e., can we just do the
# length check once, at the front, and assume at least three bytes?

def decode(s, pos=0, eos=-1):
    """decode(s, pos=0, eos=-1) -> (value, pos)
    Decodes a BER-encoded string.
    Return value includes the position where decoding stopped.
    <pos> start of scanning position.
    <eos> end of scanning.
    """
    if eos == -1:
        eos = len(s)
    # 1) get tag
    tag = ord(s[pos])
    pos += 1
    # 2) get length
    if pos > eos:
        # assure at least one byte [valid for length == 0]
        raise InsufficientData, pos

    a = ord(s[pos])
    if a < 0x80:
        # one-byte length
        length = a
        pos += 1
    elif pos + 1 >= eos:
        # assure at least two bytes
        raise InsufficientData, pos
    elif a == 0x81:
        # one-byte length (0x80 <= x <= 0xff)
        length = ord(s[pos+1])
        pos += 2
    elif pos + 2 >= eos:
        # assure at least three bytes
        raise InsufficientData, pos
    elif a == 0x82:
        # two-byte length (0x80 <= x <= 0xffff)
        length = ord(s[pos+1])
        length = (length << 8) | ord(s[pos+2])
        pos += 3
    else:
        # longer lengths allowed? >0x82?
        raise InvalidData, pos
    # 3) get value
    # assure at least <length> bytes
    if (pos + length) > eos:
        raise InsufficientData, pos
    elif tag == TAGS_OCTET_STRING:
        return decode_string (s, pos, length)
    elif tag == TAGS_INTEGER:
        return decode_integer (s, pos, length)
    elif tag == TAGS_SEQUENCE:
        return decode_structured (s, pos, length)
    else:
        raise UnknownTag, tag
