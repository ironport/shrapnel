# -*- Mode: Cython -*-
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


# [this code originally from _ldap.pyx]

# XXX I'm not happy with 'just_tlv' and the code that uses it - [see
#     x509.py:der_extract()].  I think a better solution would be to
#     change the decoder to include 'location' information in its
#     output.  This would probably break existing users of that
#     facility (ldap, anyone else?).  The problem is that the decoders
#     were originally written for LDAP, which has no need for access
#     to raw encoded data.
#
#     A really nice thing to do would be to make the whole thing act
#     more like a *codec* - it'd be great if you could take the output
#     of the decoder and feed it back to the encoder and get the same
#     DER out of it.  The current decoder is 'halfway' like this - it
#     doesn't bother with tag info for SEQUENCE, SET, INTEGER,
#     etc... If we had something like this we could describe ASN1 data
#     structures with something close to the ASN1 syntax, and be able
#     to automatically decode and encode those structures via nice
#     class wrappers.

from cpython cimport PyBytes_FromStringAndSize, PyNumber_Long, PyLong_Check
from libc.string cimport memcpy

import sys
W = sys.stderr.write

# ================================================================================
#                             BER encoders
# ================================================================================

# based on the table in dumpasn1.c
TAG_TABLE = {
    0x01 : 'BOOLEAN',                   #  1: Boolean
    0x02 : 'INTEGER',                   #  2: Integer
    0x03 : 'BITSTRING',                 #  2: Bit string
    0x04 : 'OCTETSTRING',               #  4: Byte string
    0x05 : 'NULLTAG',                   #  5: NULL
    0x06 : 'OID',                       #  6: Object Identifier
    0x07 : 'OBJDESCRIPTOR',             #  7: Object Descriptor
    0x08 : 'EXTERNAL',                  #  8: External
    0x09 : 'REAL',                      #  9: Real
    0x0A : 'ENUMERATED',                # 10: Enumerated
    0x0B : 'EMBEDDED_PDV',              # 11: Embedded Presentation Data Value
    0x0C : 'UTF8STRING',                # 12: UTF8 string
    0x10 : 'SEQUENCE',                  # 16: Sequence/sequence of
    0x11 : 'SET',                       # 17: Set/set of
    0x12 : 'NUMERIC_STRING',            # 18: Numeric string
    0x13 : 'PRINTABLE_STRING',          # 19: Printable string (ASCII subset)
    0x14 : 'T61_STRING',                # 20: T61/Teletex string
    0x15 : 'VIDEOTEX_STRING',           # 21: Videotex string
    0x16 : 'IA5_STRING',                # 22: IA5/ASCII string
    0x17 : 'UTC_TIME',                  # 23: UTC time
    0x18 : 'GENERALIZED_TIME',          # 24: Generalized time
    0x19 : 'GRAPHIC_STRING',            # 25: Graphic string
    0x1A : 'VISIBLE_STRING',            # 26: Visible string (ASCII subset)
    0x1B : 'GENERAL_STRING',            # 27: General string
    0x1C : 'UNIVERSAL_STRING',          # 28: Universal string
    0x1E : 'BMP_STRING',                # 30: Basic Multilingual Plane/Unicode string
    }

cdef int length_of_length (int n):
    cdef int r
    # how long will the BER-encoded length <n> be?
    if n < 0x80:
        return 1
    else:
        r = 1
        while n:
            n = n >> 8
            r = r + 1
        return r

cdef void encode_length (int l, int n, char * buffer):
    # caller must ensure room. see length_of_length above.
    cdef int i
    if l < 0x80:
        buffer[0] = <char> l
    else:
        buffer[0] = <char> (0x80 | ((n-1) & 0x7f))
        for i from 1 <= i < n:
            buffer[n-i] = <char> (l & 0xff)
            l = l >> 8

# encode an integer, ASN1 style.
# two's complement with the minimum number of bytes.
cdef object _encode_integer (int n):
    cdef int n0, byte, i
    # 16 bytes is more than enough for int == int64_t
    cdef char result[16]
    i = 0
    n0 = n
    byte = 0x80 # for n==0
    while 1:
        n = n >> 8
        if n0 == n:
            if n == -1 and ((not byte & 0x80) or (i==0)):
                # negative, but high bit clear
                result[15-i] = <char> 0xff
                i = i + 1
            elif n == 0 and (byte & 0x80):
                # positive, but high bit set
                result[15-i] = <char> 0x00
                i = i + 1
            break
        else:
            byte = n0 & 0xff
            result[15-i] = <char> byte
            i = i + 1
            n0 = n
    return PyBytes_FromStringAndSize (&result[16-i], i)

# encode an integer, ASN1 style.
# two's complement with the minimum number of bytes.
cdef object _encode_long_integer (n):
    cdef int byte, i, rlen
    cdef char * rbuf
    # 1) how many bytes?
    n0 = n
    n1 = n
    rlen = 0
    while 1:
        n1 = n1 >> 8
        if n1 == n0:
            break
        else:
            rlen = rlen + 1
            n0 = n1
    if rlen == 0:
        rlen = 1
    # 2) create result string
    result = PyBytes_FromStringAndSize (NULL, rlen)
    rbuf = result
    # 3) render result string
    i = 0
    n0 = n
    byte = 0x80 # for n==0
    while 1:
        n = n >> 8
        if n0 == n:
            if n == -1 and ((not byte & 0x80) or (i==0)):
                # negative, but high bit clear
                rbuf[(rlen-1)-i] = <char> 0xff
                i = i + 1
            elif n == 0 and byte & 0x80:
                # positive, but high bit set
                rbuf[(rlen-1)-i] = <char> 0x00
                i = i + 1
            break
        else:
            byte = n0 & 0xff
            rbuf[(rlen-1)-i] = <char> byte
            i = i + 1
            n0 = n
    return result

def encode_long_integer (n):
    return _encode_long_integer (n)

# this function is at the heart of all ASN output.
# it returns a <tag, length, value> string.

# _TLV1 (tag, data)
# <tag> is an ASN1 tag
# <data> is a single string
cdef object _TLV1 (int tag, bytes data):
    # compute length of concatenated data
    cdef int rlen, i, lol
    cdef bytes s
    rlen = len (data)
    # compute length of length
    lol = length_of_length (rlen)
    # create result string
    result = PyBytes_FromStringAndSize (NULL, 1 + lol + rlen)
    cdef char * rbuf
    rbuf = result
    # render tag
    rbuf[0] = <char> tag
    rbuf = rbuf + 1
    # render length
    encode_length (rlen, lol, rbuf)
    rbuf = rbuf + lol
    # render data
    memcpy (rbuf, <char *> data, rlen)
    # return result
    return result

# _TLV (tag, *data)
# <data> is a sequence of strings
# <tag> is an ASN1 tag
cdef object _TLV (int tag, object data):
    # compute length of concatenated data
    cdef int rlen, i, ilen, lol
    cdef bytes s
    rlen = 0
    for s in data:
        rlen += len(s)
    # compute length of length
    lol = length_of_length (rlen)
    # create result string
    result = PyBytes_FromStringAndSize (NULL, 1 + lol + rlen)
    cdef char * rbuf
    rbuf = result
    # render tag
    rbuf[0] = <char> tag
    rbuf = rbuf + 1
    # render length
    encode_length (rlen, lol, rbuf)
    rbuf = rbuf + lol
    # render data
    for s in data:
        ilen = len(s)
        memcpy (rbuf, <char *>s, ilen)
        rbuf = rbuf + ilen
    # return result
    return result

cdef object _CHOICE (int n, bint structured):
    if structured:
        n = n | <int>FLAGS_STRUCTURED
    n = n | <int>FLAGS_CONTEXT
    return n

cdef object _APPLICATION (int n):
    return n | <int>FLAGS_APPLICATION | <int>FLAGS_STRUCTURED

cdef object _ENUMERATED (int n):
    return _TLV1 (TAGS_ENUMERATED, _encode_integer (n))

cdef object _INTEGER (int n):
    return _TLV1 (TAGS_INTEGER, _encode_integer (n))

cdef object _BOOLEAN (int n):
    if n:
        n = 0xff
    else:
        n = 0x00
    return _TLV1 (TAGS_BOOLEAN, _encode_integer (n))

cdef object _SEQUENCE (object elems):
    return _TLV (TAGS_SEQUENCE, elems)

cdef object _SET (object elems):
    return _TLV (TAGS_SET, elems)

cdef object _OCTET_STRING (bytes s):
    return _TLV1 (TAGS_OCTET_STRING, s)

cdef object _OBJID (list l):
    cdef unsigned int i, list_len, one_num, temp_buf_off, temp_buf_len, done
    cdef unsigned int buf_len, first_two_as_int
    cdef char temp_buf[5], buf[32]

    if len(l) < 2:
        raise ValueError, "OBJID arg too short"
    if l[0] < 2:
        if l[1] >= 40:
            raise ValueError, "OBJID arg out of range"
    elif l[0] == 2:
        if l[1] > 175:
            raise ValueError, "OBJID arg out of range"
    else:
        raise ValueError, "OBJID arg out of range"

    first_two_as_int = (l[0] * 40) + l[1]

    # buf grows forwards. temp_buf grows backwards and is periodically
    # emptied (forwards) into buf.

    buf[0] = first_two_as_int
    buf_len = 1

    list_len = len (l)
    for i from 2 <= i < list_len:
        one_num = l[i]
        temp_buf_off = 5
        temp_buf_len = 0
        done = 0
        while not done:
            temp_buf_off = temp_buf_off - 1
            temp_buf_len = temp_buf_len + 1
            temp_buf[temp_buf_off] = (one_num & 0x7f) | 0x80
            one_num = one_num >> 7
            if one_num == 0:
                done = 1
        temp_buf[4] = temp_buf[4] & 0x7f
        if (buf_len + temp_buf_len) > 32:
            raise ValueError, "OBJID arg too long"
        memcpy (&buf[buf_len], &temp_buf[temp_buf_off], temp_buf_len)
        buf_len = buf_len + temp_buf_len
    result = PyBytes_FromStringAndSize (buf, buf_len)
    return _TLV1 (TAGS_OBJID, result)

# ================================================================================
# externally visible python interfaces
# ================================================================================

def TLV (int tag, *data):
    return _TLV (tag, data)

def CHOICE (int n, bint structured):
    return _CHOICE (n, structured)

def APPLICATION (int n):
    return _APPLICATION (n)

def ENUMERATED (int n):
    return _ENUMERATED (n)

def INTEGER (n):
    if PyLong_Check (n):
        return _TLV (TAGS_INTEGER, _encode_long_integer (n))
    else:
        return _INTEGER (n)

def BOOLEAN (int n):
    return _BOOLEAN (n)

def SEQUENCE (*elems):
    return _SEQUENCE (elems)

def SET (*elems):
    return _SET (elems)

def OCTET_STRING (s):
    return _OCTET_STRING (s)

def OBJID (l):
    return _OBJID (l)

# ================================================================================
#                             BER decoders
# ================================================================================

class DecodeError (Exception):
    """An ASN.1 decoding error occurred"""
    def __str__(self):
        return 'ASN.1 decoding error'

class InsufficientData (DecodeError):
    """ASN.1 encoding specifies more data than is available"""
    def __str__(self):
        return 'unexpected end of data'

class LengthTooLong (DecodeError):
    """We do not support ASN.1 data length > 32 bits"""
    def __str__(self):
        return 'length too long'

# Note: this codec was originally written for LDAP, but is now used outside of
#   that context.  We should consider implementing indefinite lengths.
class IndefiniteLength (DecodeError):
    """Quoth RFC2251 5.1: 'only the definite form of length encoding will be used' """
    def __str__(self):
        return 'indefinite length'

class MultiByteTag (DecodeError):
    """multi-byte tags not supported"""
    def __str__(self):
        return 'multi-byte tags not supported'

kind_unknown     = 'unknown'
kind_application = 'application'
kind_context     = 'context'
kind_oid         = 'oid'
kind_bitstring   = 'bitstring'

# SAFETY NOTE: it's important for each decoder to correctly handle length == zero.

cdef object decode_string (unsigned char * s, int * pos, int length):
    # caller guarantees sufficient data in <s>
    result = PyBytes_FromStringAndSize (<char *> (s+(pos[0])), length)
    pos[0] = pos[0] + length
    return result

cdef object decode_raw (unsigned char * s, int * pos, int length):
    # caller guarantees sufficient data in <s>
    result = PyBytes_FromStringAndSize (<char *> (s+(pos[0])), length)
    pos[0] = pos[0] + length
    return result

cdef object decode_bitstring (unsigned char * s, int * pos, int length):
    # caller guarantees sufficient data in <s>
    unused = <int>s[pos[0]]
    result = PyBytes_FromStringAndSize (<char *> (s+(pos[0]+1)), length-1)
    pos[0] = pos[0] + length
    return unused, result

cdef object decode_integer (unsigned char * s, int * pos, int length):
    cdef int n
    if length == 0:
        return 0
    else:
        n = s[pos[0]]
        if n & 0x80:
            # negative
            n = n - 0x100
        length = length - 1
        while length:
            pos[0] = pos[0] + 1
            n = (n << 8) | s[pos[0]]
            length = length - 1
        # advance past the last byte
        pos[0] = pos[0] + 1
        # this will do the typecast
        # XXX ensure this handles the full 32-bit signed range
        return n

# almost identical, but note the cast to long, this generates very different code
cdef object decode_long_integer (unsigned char * s, int * pos, int length):
    if length == 0:
        return 0
    else:
        n = s[pos[0]]
        if n & 0x80:
            # negative
            n = n - 0x100
        # cast to long
        n = PyNumber_Long (n)
        length = length - 1
        while length:
            pos[0] = pos[0] + 1
            n = (n << 8) | s[pos[0]]
            length = length - 1
        # advance past the last byte
        pos[0] = pos[0] + 1
        return n

cdef object decode_structured (unsigned char * s, int * pos, int length):
    cdef int start, end
    cdef list result = []
    start = pos[0]
    end = start + length
    if length:
        while pos[0] < end:
            #print 'structured: pos=%d end=%d remain=%d result=%r' % (pos[0], end, end - pos[0], result)
            item = _decode (s, pos, end, 0)
            result.append (item)
    return result

cdef object decode_objid (unsigned char * s, int * pos, int length):
    cdef int i, m, n, hi, lo
    cdef list r
    m = s[pos[0]]
    # first * 40 + second
    r = [m // 40, m % 40]
    n = 0
    pos[0] = pos[0] + 1
    for i from 1 <= i < length:
        m = s[pos[0]]
        hi = m & 0x80
        lo = m & 0x7f
        n = (n << 7) | lo
        if not hi:
            r.append (n)
            n = 0
        pos[0] = pos[0] + 1
    return r

cdef object decode_boolean (unsigned char * s, int * pos, int length):
    pos[0] = pos[0] + 1
    if s[pos[0]-1] == 0xff:
        return True
    else:
        return False

cdef int _decode_length (unsigned char * s, int * pos, int lol):
    # actually supports only up to 32-bit lengths
    cdef unsigned int i, n
    n = 0
    for i from 0 <= i < lol:
        n = (n << 8) | s[pos[0]]
        pos[0] = pos[0] + 1
    return n

cdef object _decode (unsigned char * s, int * pos, int eos, bint just_tlv):
    cdef int tag, lol
    cdef unsigned int length
    # 1) get tag
    tag = <int> s[pos[0]]
    if tag & 0x1f == 0x1f:
        raise MultiByteTag, pos[0]
    else:
        pos[0] = pos[0] + 1
        # 2) get length
        if (pos[0]) > eos:
            # assure at least one byte [valid for length == 0]
            raise InsufficientData, pos[0]
        elif s[pos[0]] < 0x80:
            # one-byte length
            length = s[pos[0]]
            pos[0] = pos[0] + 1
        elif s[pos[0]] == 0x80:
            raise IndefiniteLength, pos[0]
        else:
            # long definite length form, lower 7 bits
            # give us the number of bytes of length
            lol = s[pos[0]] & 0x7f
            pos[0] = pos[0] + 1
            if lol > 4:
                # we don't support lengths > 32 bits
                raise LengthTooLong, pos[0]
            elif pos[0] + lol > eos:
                raise InsufficientData, pos[0]
            else:
                length = _decode_length (s, pos, lol)
        #print '_decode(), pos=%d length=%d eos=%d' % (pos[0], length, eos)
        # 3) get value
        # assure at least <length> bytes
        if (<int> length) < 0:
            # length > 2GB... hmmm... thuggery...
            raise InsufficientData, pos[0]
        elif (pos[0] + length) > eos:
            raise InsufficientData, pos[0]
        elif just_tlv:
            return (tag & 0x1f, tag & 0xe0, length)
        elif tag == TAGS_OCTET_STRING:
            return decode_string (s, pos, length)
        elif tag == TAGS_INTEGER:
            if length > 4:
                return decode_long_integer (s, pos, length)
            else:
                return decode_integer (s, pos, length)
        elif tag == TAGS_BOOLEAN:
            return decode_boolean (s, pos, length)
        elif tag == TAGS_SEQUENCE:
            return decode_structured (s, pos, length)
        elif tag == TAGS_SET:
            return decode_structured (s, pos, length)
        elif tag == TAGS_ENUMERATED:
            return decode_integer (s, pos, length)
        elif tag == TAGS_OBJID:
            return (kind_oid, decode_objid (s, pos, length))
        elif tag == TAGS_BITSTRING:
            return (kind_bitstring, decode_bitstring (s, pos, length))
        elif tag == TAGS_NULL:
            return None
        else:
            if tag & <int>FLAGS_CONTEXT:
                kind = kind_context
            elif tag & <int>FLAGS_APPLICATION:
                kind = kind_application
            elif TAG_TABLE.has_key (tag & 0x1f):
                kind = TAG_TABLE[tag & 0x1f]
            else:
                kind = kind_unknown
            if tag & <int>FLAGS_STRUCTURED:
                return (kind, tag & 0x1f, decode_structured (s, pos, length))
            else:
                return (kind, tag & 0x1f, decode_raw (s, pos, length))

def decode (bytes s, int pos=0, just_tlv=0):
    return _decode (
        <unsigned char *> s,
        &pos,
        len (s),
        just_tlv
        ), pos

