# -*- Mode: Pyrex -*-
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

# ================================================================================
#                        external declarations
# ================================================================================

cdef extern from "Python.h":
    # need to be careful, we can only use functions with
    # simple/standard refcount behaviors. [e.g., no borrowed refs]
    object PyString_FromStringAndSize (char * s, int len)
    int    PyList_Size (object)           except -1
    int    PyTuple_Size (object)          except -1
    object PySequence_GetItem (object, int index)
    int    PySequence_Size (object)       except -1
    int    PyList_Append (object, object) except -1
    int    PyList_Reverse (object)        except -1
    int    PyString_Size (object)         except -1
    int    PyLong_Check (object)
    object PyNumber_Long (object)
    char * PyString_AsString (object)
    void * memcpy (void *, void *, int len)

# ================================================================================
#                             BER encoders
# ================================================================================

# flags for BER tags
cdef enum FLAGS:
    FLAGS_UNIVERSAL       = 0x00
    FLAGS_STRUCTURED      = 0x20
    FLAGS_APPLICATION     = 0x40
    FLAGS_CONTEXT         = 0x80

# NULL is a pyrex keyword
# universal BER tags
cdef enum TAGS:
    TAGS_BOOLEAN          = 0x01
    TAGS_INTEGER          = 0x02
    TAGS_BITSTRING        = 0x03
    TAGS_OCTET_STRING     = 0x04
    TAGS_NULL             = 0x05
    TAGS_OBJID            = 0x06
    TAGS_OBJDESCRIPTOR    = 0x07
    TAGS_EXTERNAL         = 0x08
    TAGS_REAL             = 0x09
    TAGS_ENUMERATED       = 0x0a
    TAGS_EMBEDDED_PDV     = 0x0b
    TAGS_UTF8STRING       = 0x0c
    TAGS_SEQUENCE         = 0x10 | 0x20 # Equivalent to FLAGS_STRUCTURED
    TAGS_SET              = 0x11 | 0x20 # Equivalent to FLAGS_STRUCTURED

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

# another possibility would be to access the 'characters'
# array in stringobject.c directly.  [it's static, though]

cdef object char (int ch):
    if (ch < 0) or (ch >= 256):
        raise ValueError, "chr() arg not in range (256)"
    else:
        return PyString_FromStringAndSize (<char*>&ch, 1)

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
    return PyString_FromStringAndSize (&result[16-i], i)

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
    result = PyString_FromStringAndSize (NULL, rlen)
    rbuf = PyString_AsString (result)
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
# it emits a <tag, length, value> string.
# <data> is a sequence of strings
# <tag> is an ASN1 tag
cdef object _TLV (int tag, object data):
    # compute length of concatenated data
    cdef int dlen, rlen, i, ilen, lol
    rlen = 0
    dlen = PySequence_Size (data)
    for i from 0 <= i < dlen:
        s = PySequence_GetItem (data, i)
        rlen = rlen + PyString_Size (s)
    # compute length of length
    lol = length_of_length (rlen)
    # create result string
    result = PyString_FromStringAndSize (NULL, 1 + lol + rlen)
    cdef char * rbuf
    rbuf = PyString_AsString (result)
    # render tag
    rbuf[0] = <char> tag
    rbuf = rbuf + 1
    # render length
    encode_length (rlen, lol, rbuf)
    rbuf = rbuf + lol
    # render data
    for i from 0 <= i < dlen:
        s = PySequence_GetItem (data, i)
        ilen = PyString_Size (s)
        memcpy (rbuf, PyString_AsString (s), ilen)
        rbuf = rbuf + ilen
    # return result
    return result

cdef object _CHOICE (int n, int structured):
    if structured:
        n = n | <int>FLAGS_STRUCTURED
    n = n | <int>FLAGS_CONTEXT
    return n

cdef object _APPLICATION (int n):
    return n | <int>FLAGS_APPLICATION | <int>FLAGS_STRUCTURED

cdef object _ENUMERATED (int n):
    return _TLV (TAGS_ENUMERATED, (_encode_integer (n),))

cdef object _INTEGER (int n):
    return _TLV (TAGS_INTEGER, (_encode_integer (n),))

cdef object _BOOLEAN (int n):
    if n:
        n = 0xff
    else:
        n = 0x00
    return _TLV (TAGS_BOOLEAN, (_encode_integer (n),))

cdef object _SEQUENCE (object elems):
    return _TLV (TAGS_SEQUENCE, elems)

cdef object _OCTET_STRING (object s):
    return _TLV (TAGS_OCTET_STRING, (s,))

cdef object _OBJID (object l):
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

    list_len = PySequence_Size (l)
    for i from 2 <= i < list_len:
        one_num = PySequence_GetItem (l, i)
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
        memcpy(&buf[buf_len], &temp_buf[temp_buf_off], temp_buf_len)
        buf_len = buf_len + temp_buf_len

    result = PyString_FromStringAndSize (buf, buf_len)

    return _TLV (TAGS_OBJID, (result,))

# ================================================================================
# externally visible python interfaces

def TLV (int tag, *data):
    return _TLV (tag, data)

def CHOICE (int n, int structured):
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
    result = PyString_FromStringAndSize (<char *> (s+(pos[0])), length)
    pos[0] = pos[0] + length
    return result

cdef object decode_raw (unsigned char * s, int * pos, int length):
    # caller guarantees sufficient data in <s>
    result = PyString_FromStringAndSize (<char *> (s+(pos[0])), length)
    pos[0] = pos[0] + length
    return result

cdef object decode_bitstring (unsigned char * s, int * pos, int length):
    # caller guarantees sufficient data in <s>
    unused = <int>s[pos[0]]
    result = PyString_FromStringAndSize (<char *> (s+(pos[0]+1)), length-1)
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
    start = pos[0]
    end = start + length
    result = []
    if length:
        while pos[0] < end:
            #print 'structured: pos=%d end=%d remain=%d result=%r' % (pos[0], end, end - pos[0], result)
            item = _decode (s, pos, end, 0)
            PyList_Append (result, item)
    return result

cdef object decode_objid (unsigned char * s, int * pos, int length):
    cdef int i, m, n, hi, lo
    m = s[pos[0]]
    # first * 40 + second
    r = [m / 40, m % 40]
    n = 0
    pos[0] = pos[0] + 1
    for i from 1 <= i < length:
        m = s[pos[0]]
        hi = m & 0x80
        lo = m & 0x7f
        n = (n << 7) | lo
        if not hi:
            PyList_Append (r, n)
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

cdef object _decode (unsigned char * s, int * pos, int eos, int just_tlv):
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

def decode (s, int pos=0, just_tlv=0):
    return _decode (
        <unsigned char *> PyString_AsString (s),
        &pos,
        PyString_Size (s),
        just_tlv
        ), pos

# ================================================================================
#    ldap search filter language parser
# ================================================================================

# this is not yet complete. see rfc2254

class QuerySyntaxError (Exception):
    """Error parsing rfc2254 query filter"""
    def __str__(self):
        if (len(self.args) == 2) \
           and isinstance(self.args[0], str) \
           and isinstance(self.args[1], int) \
           and (self.args[1] >= 0) \
           and (self.args[1] < len(self.args[0])):
            return 'LDAP Query Syntax Error: Invalid character \'%c\' at ' \
                   'position %d of query "%s"' \
                   % (self.args[0][self.args[1]], self.args[1], self.args[0])
        else:
            return 'LDAP Query Syntax Error: %s' % Exception.__str__(self)

cdef enum:
    SCOPE_BASE      = 0
    SCOPE_ONELEVEL  = 1
    SCOPE_SUBTREE   = 2

cdef enum:
    DEREF_NEVER     = 0
    DEREF_SEARCHING = 1
    DEREF_FINDING   = 2
    DEREF_ALWAYS    = 3

cdef enum:
    FILTER_AND                = 0
    FILTER_OR                 = 1
    FILTER_NOT                = 2
    FILTER_EQUALITY_MATCH     = 3
    FILTER_SUBSTRINGS         = 4
    FILTER_GREATER_OR_EQUAL   = 5
    FILTER_LESS_OR_EQUAL      = 6
    FILTER_PRESENT            = 7
    FILTER_APPROX_MATCH       = 8
    FILTER_EXTENSIBLE_MATCH   = 9

cdef enum:
    SUBSTRING_INITIAL = 0
    SUBSTRING_ANY     = 1
    SUBSTRING_FINAL   = 2

def parse_query (s, pos=0):
    expression, pos = parse_expression (s, pos, 0)
    return expression

cdef parse_expression (object x, int pos, int depth):
    cdef char * s
    cdef char kind
    cdef int slen
    s = PyString_AsString (x)
    slen = PyString_Size (x)
    if s[pos] != c'(':
        raise QuerySyntaxError, (x, pos)
    elif depth > 50:
        raise QuerySyntaxError, "expression too complex"
    else:
        # skip the open-paren
        pos = pos + 1
        # is this a logical expression or a comparison?
        if s[pos] == c'|' or s[pos] == c'&' or s[pos] == c'!':
            # logical
            kind = s[pos]
            expressions = []
            pos = pos + 1
            while s[pos] != c')':
                expression, pos = parse_expression (x, pos, depth+1)
                PyList_Append (expressions, expression)
            if kind == c'|':
                return _TLV (_CHOICE (FILTER_OR, 1), expressions), pos + 1
            elif kind == c'&':
                return _TLV (_CHOICE (FILTER_AND, 1), expressions), pos + 1
            elif kind == c'!':
                return _TLV (_CHOICE (FILTER_NOT, 1), expressions[:1]), pos + 1
        else:
            # comparison
            attr, is_substring, pos = parse_name (x, pos)
            operator, pos = parse_operator (x, pos)
            value, is_substring, pos = parse_value (x, pos)
            attr = unescape (attr)
            # we don't unescape <value> yet, because we might need
            # some escaped splat chars to make it through parse_substring()
            # [where the pieces will be unescaped individually]
            if is_substring:
                if value == '*' and operator == FILTER_EQUALITY_MATCH:
                    # (tag=*)
                    return _TLV (
                        _CHOICE (FILTER_PRESENT, 0), # unstructured
                        (attr,)                      # tag implied by CHOICE
                        ), pos + 1
                elif operator == FILTER_EQUALITY_MATCH:
                    # (tag=sub*strin*g*)
                    return _TLV (
                        _CHOICE (FILTER_SUBSTRINGS, 1), (
                            _OCTET_STRING (attr),
                            _SEQUENCE (parse_substring (value, 0, PyString_Size (value)))
                            )
                        ), pos + 1
                else:
                    raise QuerySyntaxError, "invalid wildcard syntax"
            else:
                return _TLV (
                    _CHOICE (operator, 1), (
                        _OCTET_STRING (attr),
                        _OCTET_STRING (unescape (value)),
                        )
                    ), pos + 1

cdef parse_operator (object x, int pos):
    cdef char * s
    cdef int slen
    s = PyString_AsString (x)
    slen = PyString_Size (x)
    if (pos + 2) >= slen:
        raise QuerySyntaxError, (s, pos)
    elif s[pos] == c'=':
        return FILTER_EQUALITY_MATCH, pos + 1
    elif s[pos] == c'~' and s[pos+1] == c'=':
        return FILTER_APPROX_MATCH, pos + 2
    elif s[pos] == c'<' and s[pos+1] == c'=':
        return FILTER_LESS_OR_EQUAL, pos + 2
    elif s[pos] == c'>' and s[pos+1] == c'=':
        return FILTER_GREATER_OR_EQUAL, pos + 2
    else:
        raise QuerySyntaxError, (x, pos)

# [initial]*any*any*any*[final]

cdef object parse_substring (char * s, int pos, int slen):
    # assumes the presence of at least one splat
    cdef int i, start
    result = []
    start = 0
    i = 0
    while 1:
        if i == slen:
            if start != i:
                # final
                PyList_Append (
                    result,
                    _TLV (_CHOICE (SUBSTRING_FINAL, 0), (unescape (s[start:]),))
                    )
            return result
        elif s[i] == c'*':
            if start == 0:
                if i > 0:
                    # initial
                    PyList_Append (
                        result,
                        _TLV (_CHOICE (SUBSTRING_INITIAL, 0), (unescape (s[0:i]),))
                        )
            else:
                # any
                PyList_Append (
                    result,
                    _TLV (_CHOICE (SUBSTRING_ANY, 0), (unescape (s[start:i]),))
                    )
            # next bit will start *after* the splat
            start = i + 1
            i = i + 1
        else:
            i = i + 1

def ue (s):
    return unescape (s)

cdef int name_punc_table[256]
for i from 0 <= i < 256:
    if char (i) in '()=<>~':
        name_punc_table[i] = 1
    else:
        name_punc_table[i] = 0

cdef object parse_name (object x, int pos):
    cdef int slen, is_substring, rpos, start
    cdef unsigned char * s
    s = <unsigned char *>PyString_AsString (x)
    slen = PyString_Size (x)
    rpos = 0
    start = pos
    if name_punc_table[s[pos]]:
        raise QuerySyntaxError, (x, pos)
    else:
        is_substring = 0
        # we expect names to be delimited by an operator or a close-paren
        while pos < slen:
            if not name_punc_table[s[pos]]:
                if s[pos] == c'*':
                    is_substring = 1
                rpos = rpos + 1
                if rpos == 4096:
                    raise QuerySyntaxError, (x, pos)
                pos = pos + 1
            else:
                return PyString_FromStringAndSize (<char *>(s + start), rpos), is_substring, pos
        else:
            raise QuerySyntaxError, (x, pos)

cdef object parse_value (object x, int pos):
    cdef int slen, is_substring, rpos, start
    cdef unsigned char * s
    s = <unsigned char *>PyString_AsString (x)
    slen = PyString_Size (x)
    rpos = 0
    start = pos
    is_substring = 0
    # we expect values to be delimited by a close-paren
    while pos < slen:
        if s[pos] != c')':
            if s[pos] == c'*':
                is_substring = 1
            rpos = rpos + 1
            if rpos == 4096:
                raise QuerySyntaxError, (x, pos)
            pos = pos + 1
        else:
            return PyString_FromStringAndSize (<char *>(s + start), rpos), is_substring, pos
    else:
        raise QuerySyntaxError, (x, pos)

cdef object unescape (object x):
    cdef int slen, rpos, flag, pos
    cdef char * s
    s = PyString_AsString (x)
    slen = PyString_Size (x)
    cdef char buffer[4096]
    pos = 0
    rpos = 0
    flag = 0
    while pos < slen:
        if s[pos] == c'\\':
            flag = 1
            pos = pos + 1
            ch, pos = parse_hex_escape (s, pos, slen)
        else:
            ch = s[pos]
            pos = pos + 1
        buffer[rpos] = ch
        rpos = rpos + 1
        if rpos == 4096:
            raise QuerySyntaxError, (x, pos)
    if flag:
        # return a new, unescaped string
        return PyString_FromStringAndSize (buffer, rpos)
    else:
        # return the original string
        return x

cdef int parse_hex_digit (int ch):
    if (ch >= 48 and ch <= 57):
        return (ch - 48)
    elif (ch >= 97 and ch <= 102):
        return (ch - 97) + 10
    elif (ch >= 65 and ch <= 70):
        return (ch - 65) + 10
    else:
        return -1

cdef object parse_hex_escape (char * s, int pos, int len):
    cdef int ch, result
    if pos + 2 > len:
        raise QuerySyntaxError, (s, pos)
    else:
        ch = parse_hex_digit (s[pos])
        if ch == -1:
            raise QuerySyntaxError, (s, pos)
        else:
            result = ch << 4
        pos = pos + 1
        ch = parse_hex_digit (s[pos])
        if ch == -1:
            raise QuerySyntaxError, (s, pos)
        else:
            result = result | ch
        pos = pos + 1
    return result, pos

cdef int escape_table[256]
for i from 0 <= i < 256:
    if char (i) in '\\()=<>~*':
        escape_table[i] = 1
    else:
        escape_table[i] = 0

cdef char hex_digits[16]
for i from 0 <= i < 16:
    # not sure why this works
    hex_digits[i] = "0123456789abcdef"[i]

# 525486/sec
def query_escape (s):
    cdef int slen, rlen, i, j
    cdef unsigned char ch
    cdef char * sbuf, * rbuf
    slen = PyString_Size (s)
    sbuf = PyString_AsString (s)
    rlen = slen
    # compute length of result
    for i from 0 <= i < slen:
        if escape_table[<unsigned char>sbuf[i]]:
            rlen = rlen + 2
    # create result string
    r = PyString_FromStringAndSize (NULL, rlen)
    rbuf = PyString_AsString (r)
    # fill result string
    j = 0
    for i from 0 <= i < slen:
        ch = sbuf[i]
        if escape_table[ch]:
            rbuf[j+0] = <char> 92
            rbuf[j+1] = <char> hex_digits[ch >> 4]
            rbuf[j+2] = <char> hex_digits[ch & 0xf]
            j = j + 3
        else:
            rbuf[j] = ch
            j = j + 1
    return r
