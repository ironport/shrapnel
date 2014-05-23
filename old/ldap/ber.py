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

#
# Basic Encoding Rules (BER) for SMI data types
#
# Keith Dart <kdart@cosinecom.com>, 2001
# Some functions partially derived from Simon Leinen's <simon@switch.ch>
# BER PERL module (which was actually taken from the pysnmp module).

# XXX stolen from PyNMS by Sam Rushing <srushing@ironport.com>
# XXX there's a lot of stuff in here that I'm not using - clean it up!

class UnknownTag (Exception):
    pass

TRUE = 0xFF
FALSE = 0

CONTEXT = 'context'
APPLICATION = 'application'
UNKNOWN = 'unknown'

# flags for BER tags
FLAGS = {
    'UNIVERSAL'       : 0x00,
    'STRUCTURED'      : 0x20,
    'APPLICATION'     : 0x40,
    'CONTEXT'         : 0x80,
    'PRIVATE'         : 0xC0,
}

# universal BER tags
TAGS = {
    'INTEGER'                   : 0x02,
    'OCTET_STRING'              : 0x04,
    'OBJID'                     : 0x06,
    'NULL'                      : 0x05,
    'SEQUENCE'                  : 0x10 | FLAGS['STRUCTURED'],
    'BOOLEAN'                   : 0x01,
    'BITSTRING'                 : 0x03,
    'SET'                       : 0x11,
    'SETOF'                     : 0x31,
    'Enumerated'                : 0x0a,
}

# pre-compute tag encodings
TAG_ENCODINGS = {}
for _tn in TAGS.keys():
    TAG_ENCODINGS[_tn] = chr(TAGS[_tn])
del _tn

# invert TAG map to speed decoding
REVERSE_TAGS = {}
for _name, _value in TAGS.items():
    REVERSE_TAGS[_value] = _name
del _name, _value

# BER encoders / decoders
#
# BER HEADER ENCODERS / DECODERS

def encode_length(length):
    """encode BER length"""
    # if given length fits one byte
    if length < 0x80:
        return '%c' % length
    # two bytes required
    elif length < 0xFF:
        return '%c%c' % (0x81, length)
    # three bytes required
    else:
        return '%c%c%c' % (0x82, (length >> 8) & 0xFF, length & 0xFF)

# encode a native signed 32bit integer
def encode_an_integer_type (arg, ber_tag):
    # this would actually be easier in C!
    if arg == 0:
        return '%c%c%c' % (ber_tag, 1, 0)
    s = []
    shiftcount = 0
    topval = arg & 0xff800000
    while topval == 0 or topval == 0xff800000:
        arg = arg << 8
        topval = arg & 0xff800000
        shiftcount = shiftcount + 1
    __pychecker__ = 'unusednames=i'
    for i in xrange(4 - shiftcount):
        s.append(((arg & 0xff000000) >> 24) & 0xff)
        arg = arg << 8
    result = ''.join(map(chr, s))
    return ber_tag + encode_length(len(result)) +  result


# encode an unsigned 32 bit value (which is actually a python long)
def encode_an_unsigned(arg, ber_tag):
    s = []
    while arg > 0L:
        s.insert(0, chr(arg & 0xffL))
        arg = arg >> 8L
    if s and (ord(s[0]) & 0x80):
        s.insert(0, chr(0))
    result = ''.join(s)
    return ber_tag + encode_length(len(result)) +  result


def encode_tag (name):
    """encode ASN.1 data type tag"""
    # lookup the tag ID by name
    try:
        return TAG_ENCODINGS[name]
    except KeyError:
        raise UnknownTag, name

def decode_tag (tag):
    """decode ASN.1 data type tag"""
    try:
        return REVERSE_TAGS[tag]
    except KeyError:
        raise UnknownTag, tag

def encode_boolean(value):
    if value:
        return TAG_ENCODINGS['BOOLEAN'] + '%c%c' % (1, TRUE)
    else:
        return TAG_ENCODINGS['BOOLEAN'] + '%c%c' % (1, FALSE)

# encode an octets string
def encode_string(string):
    """encode ASN.1 string"""
    return TAG_ENCODINGS['OCTET_STRING'] + encode_length(len(string)) + string

def encode_a_pdu(ber_tag, *args):
    encodings = []
    for arg in args:
        if arg is None:
            encodings.append(encode_null())
        else:
            encodings.append(arg.encode())
    res = ''.join(encodings)
    return ber_tag + encode_length(len(res)) + res

# encode null
def encode_null():
    """encode ASN.1 NULL"""
    return '%c%c' % (TAGS['NULL'], 0)

def encode_integer(value):
    return encode_an_integer_type(value, TAG_ENCODINGS['INTEGER'])

# create dictionary that maps ber_tag encodings to methods
ENCODE_METHODS = {}
ENCODE_METHODS[None] = encode_null
ENCODE_METHODS[chr(TAGS['BOOLEAN'])] = encode_boolean
ENCODE_METHODS[chr(TAGS['INTEGER'])] = encode_integer
ENCODE_METHODS[chr(TAGS['OCTET_STRING'])] = encode_string
ENCODE_METHODS[chr(TAGS['NULL'])] = encode_null
ENCODE_METHODS[chr(TAGS['Enumerated'])] = encode_integer

#
# ASN.1 DATA TYPES DECODERS

class TLV:
    def __init__(self, tag, length, value, lol):
        self.tag = tag
        self.length = length
        self.value = value
        self.lol = lol # length of length - needed for sequence decoding - kludgy
    def __str__(self):
        return '<TLV: tag=0x%x, length=%d, value=%s>' % (self.tag, self.length, repr(self.value))
    def __repr__(self):
        return '%s(0x%x, %d, %s)' % (self.__class__.__name__, self.tag, self.length, repr(self.value))
    def decode(self):
        try:
            return DECODE_METHODS[self.tag](self.length, self.value)
        except KeyError:
            # rather than barf, return CONTEXT and APPLICATION types as AST's.
            # we can check for them explicitly like this:
            #     "if x[0] is ber.APPLICATION:"
            # XXX can both be set?  Doesn't seem likely.
            if self.tag & FLAGS['CONTEXT']:
                kind = CONTEXT
            elif self.tag & FLAGS['APPLICATION']:
                kind = APPLICATION
            else:
                kind = None
            if kind:
                if self.tag & FLAGS['STRUCTURED']:
                    return (kind, self.tag & 0x1f, decode_structured (len(self.value), self.value))
                else:
                    return (kind, self.tag & 0x1f, self.value)
            else:
                return (UNKNOWN, self.tag, self.value)

def get_tlv(message):
    if len(message) > 1:
        tag = ord(message[0])
        length, inc = _decode_message_length(message)
        value = message[inc+1:length+inc+1]
        return TLV(tag, length, value, inc)
    else:
        raise ValueError, 'ber.get_tlv: message too small'

def decode (message):
    return get_tlv (message).decode()

def _decode_message_length(message):
    # message[0] is the tag
    fb = ord(message[1])
    msb = fb & 0x80
    val = fb & 0x7f
    if not msb:
        return val, 1
    else:
        return _decode_an_integer (val, message[2:2+val], signed=0), 1+val

# A SEQUENCE is implicitly a tuple
def decode_sequence(length, message):
    assert length == len(message)
    sequence = []
    index = 0
    if length:
        while index < length:
            newtlv = get_tlv(message[index:])
            index = index + newtlv.length + newtlv.lol + 1
            sequence.append(newtlv.decode())
    return tuple(sequence)

def decode_structured (length, message):
    assert length == len(message)
    sequence = []
    index = 0
    if length:
        while index < length:
            newtlv = get_tlv(message[index:])
            index = index + newtlv.length + newtlv.lol + 1
            item = newtlv.decode()
            sequence.append (item)
    return tuple(sequence)

def decode_boolean(length, message):
    __pychecker__ = 'unusednames=length'
    return ord(message[0])

# this decodes any basic integer type, and returns a long to handle
# unsigned types.
def _decode_an_integer (length, message, signed=1):
    __pychecker__ = 'unusednames=length'
    val = ord (message[0])
    if val & 0x80 and signed:
        val = val - 256
    for c in message[1:]:
        val = val << 8 | ord(c)
    return val

def _decode_an_unsigned(length, message):
    val = 0L
    for i in xrange(length):
        val = (val << 8) + ord(message[i])
    return val

def decode_integer(length, message):
    return _decode_an_integer(length, message)

def decode_string(length, message):
    __pychecker__ = 'unusednames=length'
    return message

def decode_null(length, message):
    return None

def decode_exception(length, message):
    return None

DECODE_METHODS = {}
DECODE_METHODS[TAGS['BOOLEAN']] = decode_boolean
DECODE_METHODS[TAGS['INTEGER']] = decode_integer
DECODE_METHODS[TAGS['OCTET_STRING']] = decode_string
DECODE_METHODS[TAGS['NULL']] = decode_null
DECODE_METHODS[TAGS['SEQUENCE']] = decode_sequence
DECODE_METHODS[TAGS['SETOF']] = decode_structured
DECODE_METHODS[TAGS['Enumerated']] = decode_integer
