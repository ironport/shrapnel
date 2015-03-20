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
from cpython.unicode cimport PyUnicode_DecodeUTF8, PyUnicode_AsUTF8String
from libc.string cimport memcpy
from libc.stdint cimport uint64_t, int16_t, uint8_t

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

cdef long length_of_length (long n):
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

cdef long length_of_tag (long n):
    cdef int r
    # how long will the BER-encoded tag <n> be?
    if n < 0x1f:
        return 1
    else:
        r = 1
        while n:
            n = n >> 7
            r = r + 1
        return r

cdef void encode_length (long l, long n, uint8_t * buffer):
    # caller must ensure room. see length_of_length above.
    cdef long i
    if l < 0x80:
        buffer[0] = <char> l
    else:
        buffer[0] = <char> (0x80 | ((n-1) & 0x7f))
        for i from 1 <= i < n:
            buffer[n-i] = <char> (l & 0xff)
            l = l >> 8

cdef void encode_tag (long tag, uint8_t flags, long n, uint8_t * buffer):
    # caller must ensure room. see length_of_tag above.
    cdef long i
    cdef uint8_t b
    if tag < 0x1f:
        buffer[0] = tag | flags
    else:
        buffer[0] = 0x1f | flags
        for i from 1 <= i < n:
            if i == 1:
                b = tag & 0x7f
            else:
                b = (tag & 0x7f) | 0x80
            buffer[n-i] =b
            tag >>= 7

# encode an integer, ASN1 style.
# two's complement with the minimum number of bytes.
cdef object _encode_integer (long n):
    cdef long n0, byte, i
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
    return result[16-i:16]

# encode an integer, ASN1 style.
# two's complement with the minimum number of bytes.
cdef object _encode_long_integer (n):
    cdef long byte, i, rlen
    cdef char * rbuf
    # 1) how many bytes?
    n0 = n
    n1 = n
    # add one extra byte for negative/positive flag
    rlen = 1
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
    return result[rlen-i:]

# I believe that almost no one uses the official latest floating-point format in asn.1
#   An obviously better solution is to wrap IEEE754 with a BITSTRING, and that's what
#   I would recommend in a real-world scenario.

cdef union double_layout:
    double  as_double
    uint64_t as_uint64

# I can't put these large constants directly into the code, cython is
#   upgrading them to python objects for some reason.
cdef uint64_t NEGATIVE_BIT = (<uint64_t>1)<<63
cdef uint64_t MANTISSA_MASK = 0xfffffffffffff

# http://www.itu.int/rec/T-REC-X.690-200811-I
# XXX consider using frexp/ldexp to disassemble double,
#     but in the meanwhile assuming IEEE 754 is not a bad choice.
# http://steve.hollasch.net/cgindex/coding/ieeefloat.html
cdef _encode_double (double f):
    cdef double_layout x
    cdef uint64_t x64 = x.as_uint64
    x.as_double = f
    cdef bint negative = x64 & NEGATIVE_BIT
    cdef int16_t exp = ((x64 >> 52) & 0x7ff) - (1023 + 52)
    cdef uint64_t man = (x64 & MANTISSA_MASK)
    cdef unsigned char result[10]
    # bit 8 says binary encoding
    result[0] = 0b10000000
    if negative:
        result[0] |= 0b1000000
    # base is 2, bits 6-5 are zero
    # scaling factor and bits 4-3 are zero
    # two octets to encode exponent
    result[0] |= 0b01
    result[1] = exp >> 8
    result[2] = exp & 0xff
    cdef int i = 0
    cdef int j = 3
    # because of the implied '1' bit (bit 53), we know
    #   exactly how long the result will be.
    for i in range (7):
        result[j] = (man >> (8 * (6-i))) & 0xff
        j += 1
    # now set bit 53 - divmod(53,8)==(6,5) - so set bit 5
    result[3] |= 0b10000
    return result[:10]

cpdef encode_double (double f):
    return _TLV1 (TAGS_REAL, 0, _encode_double (f))

def encode_long_integer (n):
    return _encode_long_integer (n)

# this function is at the heart of all ASN output.
# it returns a <tag, length, value> string.

# _TLV1 (tag, flags, data)
# <tag> is an ASN1 tag
# <data> is a single string
cdef object _TLV1 (long tag, uint8_t flags, bytes data):
    cdef long rlen, i, lol, lot
    cdef bytes s
    rlen = len (data)
    lol = length_of_length (rlen)
    lot = length_of_tag (tag)
    # create result string
    result = PyBytes_FromStringAndSize (NULL, lot + lol + rlen)
    cdef uint8_t * rbuf = result
    encode_tag (tag, flags, lot, rbuf)
    rbuf += lot
    encode_length (rlen, lol, rbuf)
    rbuf += lol
    # render data
    memcpy (rbuf, <char *> data, rlen)
    return result

# _TLV (tag, flags, *data)
# <data> is a sequence of strings
# <tag> is an ASN1 tag
cdef object _TLV (long tag, uint8_t flags, object data):
    cdef long rlen, i, ilen, lol, lot
    cdef bytes s
    rlen = 0
    # compute length of concatenated data
    for s in data:
        rlen += len(s)
    lol = length_of_length (rlen)
    lot = length_of_tag (tag)
    # create result string
    result = PyBytes_FromStringAndSize (NULL, lot + lol + rlen)
    cdef uint8_t * rbuf = result
    encode_tag (tag, flags, lot, rbuf)
    rbuf += lot
    encode_length (rlen, lol, rbuf)
    rbuf += lol
    # render data
    for s in data:
        ilen = len(s)
        memcpy (rbuf, <char *>s, ilen)
        rbuf += ilen
    return result

cdef object _CHOICE (long n, bint structured):
    if structured:
        n = n | <int>FLAGS_STRUCTURED
    n = n | <int>FLAGS_CONTEXT
    return n

cdef object _ENUMERATED (long n):
    return _TLV1 (TAGS_ENUMERATED, 0, _encode_integer (n))

cdef object _INTEGER (long n):
    return _TLV1 (TAGS_INTEGER, 0, _encode_integer (n))

cdef object _BOOLEAN (long n):
    if n:
        b = '\xff'
    else:
        b = '\x00'
    return _TLV1 (TAGS_BOOLEAN, 0, b)

cdef object _SEQUENCE (object elems):
    return _TLV (TAGS_SEQUENCE, FLAGS_STRUCTURED, elems)

cdef object _SET (object elems):
    return _TLV (TAGS_SET, FLAGS_STRUCTURED, elems)

cdef object _OCTET_STRING (bytes s):
    return _TLV1 (TAGS_OCTET_STRING, 0, s)

cdef object _BITSTRING (uint8_t unused, bytes s):
    return _TLV1 (TAGS_BITSTRING, 0, chr(unused) + s)

cdef object _UTF8_STRING (unicode s):
    return _TLV1 (TAGS_UTF8STRING, 0, PyUnicode_AsUTF8String (s))

cdef object _OBJID (list l):
    cdef unsigned long i, list_len, one_num, temp_buf_off, temp_buf_len, done
    cdef unsigned long buf_len, first_two_as_int
    cdef char temp_buf[5]
    cdef char buf[32]

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
    return _TLV1 (TAGS_OBJID, 0, result)

# ================================================================================
# externally visible python interfaces
# ================================================================================

def TLV (long tag, uint8_t flags, *data):
    return _TLV (tag, flags, data)

def CHOICE (long n, bint structured):
    return _CHOICE (n, structured)

def APPLICATION (long n, bint structured, bytes data):
    cdef uint8_t flags = FLAGS_APPLICATION
    if structured:
        flags |= FLAGS_STRUCTURED
    return _TLV1 (n, flags, data)

def ENUMERATED (long n):
    return _ENUMERATED (n)

def INTEGER (n):
    if PyLong_Check (n):
        return _TLV (TAGS_INTEGER, 0, _encode_long_integer (n))
    else:
        return _INTEGER (n)

def BOOLEAN (long n):
    return _BOOLEAN (n)

def SEQUENCE (*elems):
    return _SEQUENCE (elems)

def SET (*elems):
    return _SET (elems)

def CONTEXT (long n, bint structured, bytes data):
    cdef uint8_t flags = FLAGS_CONTEXT
    if structured:
        flags |= FLAGS_STRUCTURED
    return _TLV1 (n, flags, data)

def OCTET_STRING (s):
    return _OCTET_STRING (s)

def BITSTRING (uint8_t unused, bytes s):
    return _BITSTRING (unused, s)

def UTF8_STRING (unicode s):
    return _UTF8_STRING (s)

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

cdef object decode_string (unsigned char * s, long * pos, long length):
    # caller guarantees sufficient data in <s>
    result = PyBytes_FromStringAndSize (<char *> (s+(pos[0])), length)
    pos[0] = pos[0] + length
    return result

cdef object decode_unicode (unsigned char * s, long * pos, long length):
    # caller guarantees sufficient data in <s>
    result = PyUnicode_DecodeUTF8 (<char *> (s+(pos[0])), length, NULL)
    pos[0] = pos[0] + length
    return result

cdef object decode_raw (unsigned char * s, long * pos, long length):
    # caller guarantees sufficient data in <s>
    result = PyBytes_FromStringAndSize (<char *> (s+(pos[0])), length)
    pos[0] = pos[0] + length
    return result

cdef object decode_bitstring (unsigned char * s, long * pos, long length):
    # caller guarantees sufficient data in <s>
    unused = <int>s[pos[0]]
    result = PyBytes_FromStringAndSize (<char *> (s+(pos[0]+1)), length-1)
    pos[0] = pos[0] + length
    return unused, result

cdef object decode_integer (unsigned char * s, long * pos, long length):
    cdef long n
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
cdef object decode_long_integer (unsigned char * s, long * pos, long length):
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

cdef object decode_structured (unsigned char * s, long * pos, long length):
    cdef long start, end
    cdef list result = []
    start = pos[0]
    end = start + length
    if length:
        while pos[0] < end:
            #print 'structured: pos=%d end=%d remain=%d result=%r' % (pos[0], end, end - pos[0], result)
            item = _decode (s, pos, end, 0)
            result.append (item)
    return result

cdef object decode_objid (unsigned char * s, long * pos, long length):
    cdef long i, m, n, hi, lo
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

cdef object decode_boolean (unsigned char * s, long * pos, long length):
    pos[0] = pos[0] + 1
    if s[pos[0]-1] == 0xff:
        return True
    else:
        return False

cdef long _decode_length (unsigned char * s, long * pos, long lol) except? -1:
    # actually supports only up to 32-bit lengths
    cdef unsigned long i, n
    n = 0
    for i from 0 <= i < lol:
        n = (n << 8) | s[pos[0]]
        pos[0] = pos[0] + 1
    return n

cdef check_pos (long * pos, long eos):
    if pos[0] > eos:
        raise InsufficientData (pos[0], eos)

cdef inc_pos (long * pos, unsigned int n, long eos):
    if pos[0] + n > eos:
        raise InsufficientData (pos[0], n, eos)
    else:
        pos[0] += n

cdef check_has (long * pos, unsigned int n, long eos):
    if pos[0] + n > eos:
        raise InsufficientData (pos[0], n, eos)

cdef long _decode_tag (unsigned char * s, long * pos, long eos, uint8_t * flags) except? -1:
    cdef unsigned long r = 0
    cdef uint8_t b = s[pos[0]]
    inc_pos (pos, 1, eos)
    flags[0] = b & 0b11100000
    if b & 0x1f < 0x1f:
        return b & 0x1f
    else:
        while s[pos[0]] & 0x80:
            r = (r << 7) | s[pos[0]] & 0x7f
            inc_pos (pos, 1, eos)
        r = (r << 7) | s[pos[0]]
        inc_pos (pos, 1, eos)
        return r

cdef object _decode (unsigned char * s, long * pos, long eos, bint just_tlv):
    cdef long tag, lol
    cdef unsigned long length
    cdef uint8_t flags
    # 1) get tag
    tag = _decode_tag (s, pos, eos, &flags)
    # 2) get length
    check_pos (pos, eos)
    if s[pos[0]] < 0x80:
        # one-byte length
        length = s[pos[0]]
        inc_pos (pos, 1, eos)
    elif s[pos[0]] == 0x80:
        raise IndefiniteLength, pos[0]
    else:
        # long definite length form, lower 7 bits
        # give us the number of bytes of length
        lol = s[pos[0]] & 0x7f
        inc_pos (pos, 1, eos)
        if lol > 4:
            # we don't support lengths > 32 bits
            raise LengthTooLong, pos[0]
        else:
            check_has (pos, lol, eos)
            length = _decode_length (s, pos, lol)
    # 3) get value
    # assure at least <length> bytes
    if length > 2147483648:
        # length > 2GB... hmmm... thuggery...
        raise InsufficientData, pos[0]
    elif (pos[0] + length) > eos:
        raise InsufficientData, pos[0]
    elif just_tlv:
        return (tag, flags, length)
    elif flags == FLAGS_UNIVERSAL:
        if tag == TAGS_OCTET_STRING:
            return decode_string (s, pos, length)
        elif tag == TAGS_UTF8STRING:
            return decode_unicode (s, pos, length)
        elif tag == TAGS_INTEGER:
            if length > sizeof (long):
                return decode_long_integer (s, pos, length)
            else:
                return decode_integer (s, pos, length)
        elif tag == TAGS_BOOLEAN:
            return decode_boolean (s, pos, length)
        elif tag == TAGS_ENUMERATED:
            return decode_integer (s, pos, length)
        elif tag == TAGS_OBJID:
            return (kind_oid, decode_objid (s, pos, length))
        elif tag == TAGS_BITSTRING:
            return (kind_bitstring, decode_bitstring (s, pos, length))
        elif tag == TAGS_NULL:
            return None
        elif TAG_TABLE.has_key (tag):
            return (TAG_TABLE[tag], tag, decode_raw (s, pos, length))
        else:
            return (kind_unknown, tag, decode_raw (s, pos, length))
    else:
        if tag == TAGS_SEQUENCE and flags == FLAGS_STRUCTURED:
            return decode_structured (s, pos, length)
        elif tag == TAGS_SET and flags == FLAGS_STRUCTURED:
            return decode_structured (s, pos, length)
        else:
            if flags & FLAGS_CONTEXT:
                kind = kind_context
            elif flags & FLAGS_APPLICATION:
                kind = kind_application
            else:
                kind = kind_unknown
            if flags & FLAGS_STRUCTURED:
                return (kind, tag, decode_structured (s, pos, length))
            else:
                return (kind, tag, decode_raw (s, pos, length))

def decode (bytes s, long pos=0, just_tlv=0):
    return _decode (
        <unsigned char *> s,
        &pos,
        len (s),
        just_tlv
        ), pos
