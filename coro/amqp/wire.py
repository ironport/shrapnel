# -*- Mode: Python -*-

import struct
import sys

W = sys.stderr.write
is_a = isinstance

class ProtocolError (Exception):
    pass

def U (format, data, pos):
    n = struct.calcsize (format)
    result = struct.unpack (format, data[pos:pos+n])
    if len(result) == 1:
        result, = result
    pos += n
    return result, pos

def unpack_octet (data, pos):
    return U ('>b', data, pos)

def unpack_bool (data, pos):
    return U ('>?', data, pos)

def unpack_short (data, pos):
    return U ('>h', data, pos)

def unpack_long (data, pos):
    return U ('>l', data, pos)

def unpack_shortstr (data, pos):
    slen, = struct.unpack ('>B', data[pos])
    pos += 1
    result = data[pos:pos+slen]
    pos += slen
    return result, pos

def unpack_longstr (data, pos):
    slen, = struct.unpack ('>L', data[pos:pos+4])
    pos += 4
    result = data[pos:pos+slen]
    pos += slen
    return result, pos

def unpack_longlong (data, pos):
    return U ('>Q', data, pos)

def unpack_timestamp (data, pos):
    return U ('>Q', data, pos)

def unpack_field_array (data, pos):
    n, = struct.unpack ('>L', data[pos:pos+4])
    pos += 4
    result = []
    for i in range (n):
        fval, pos = unpack_field_value (data, pos)
        result.append (fval)
    return result, pos

def unpack_field_value (data, pos):
    # field-value := ftype <value>
    ftype = data[pos]
    pos += 1
    # most field-type indicators are directly equal to their struct letters.
    # we'll handle the exceptions first, then fall back to struct for the rest.
    if ftype == 't':
        fval, pos = U ('>?', data, pos)
    elif ftype == 'D':
        fval, pos = U ('>BL', data, pos)
    elif ftype == 's':
        fval, pos = unpack_shortstr (data, pos)
    elif ftype == 'S':
        fval, pos = unpack_longstr (data, pos)
    elif ftype == 'A':
        fval, pos = unpack_field_array (data, pos)
    elif ftype == 'T':
        fval, pos = U ('>Q', data, pos)
    elif ftype == 'F':
        fval, pos = unpack_table (data, pos)
    elif ftype == 'V':
        fval = None
    elif ftype in 'bBUuIiLlfd':
        fval, pos = U ('>'+ftype, data, pos)
    else:
        raise ProtocolError ("unknown field type octet: %r" % (ftype,))
    # print 'field value: type=%r value=%r' % (ftype, fval)
    return fval, pos

def unpack_table (data, pos):
    # long-uint *field-value-pair
    size, = struct.unpack ('>L', data[pos:pos+4])
    # print 'unpack_table, n=%d' % (size,)
    # print 'len(data) == %d' % (len(data),)
    pos += 4
    end = pos + size
    result = {}
    while pos < end:
        # field-value-pair := field-name field-value
        fname, pos = unpack_shortstr (data, pos)
        # print 'field_table, name=%r' % (fname,)
        fval, pos = unpack_field_value (data, pos)
        result[fname] = fval
    return result, pos

def pack_octet (v):
    return struct.pack ('>b', v)

def pack_bool (v):
    return struct.pack ('>?', v)

def pack_short (v):
    return struct.pack ('>h', v)

def pack_long (v):
    return struct.pack ('>l', v)

def pack_longlong (v):
    return struct.pack ('>Q', v)

def pack_timestamp (v):
    return struct.pack ('>Q', v)

def pack_shortstr (s):
    return struct.pack ('>B', len(s)) + s

def pack_longstr (s):
    return struct.pack ('>L', len(s)) + s

def pack_table (d):
    r = []
    for k, v in d.items():
        r.append (pack_shortstr (k))
        if is_a (v, bool):
            r.append ('t' + pack_octet (v))
        elif is_a (v, int):
            neg = v < 0
            if neg:
                v = -v
            if v < (1 << 8):
                spec = 'B', 'b', 'B'
            elif v < (1 << 16):
                spec = 'H', 'H', 'h'
            elif v < (1 << 32):
                spec = 'I', 'L', 'l'
            elif v < (1 << 64):
                spec = 'L', 'Q', 'q'
            if neg:
                code = spec[2]
            else:
                code = spec[1]
            r.append (spec[0] + struct.pack ('>' + code, v))
        elif is_a (v, str):
            # RabbitMQ doesn't like 's'???
            # if len(v) < 256:
            #     r.append ('s' + pack_shortstr (v))
            # else:
            #     r.append ('S' + pack_longstr (v))
            r.append ('S' + pack_longstr (v))
        elif is_a (v, dict):
            r.append ('F' + pack_table (v))
        else:
            raise ValueError ("don't know how to pack a %r yet" % (v.__class__,))
    data = ''.join (r)
    return struct.pack ('>L', len(data)) + data
