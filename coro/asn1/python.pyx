# -*- Mode: Cython; indent-tabs-mode: nil -*-

#
# python <-> asn1 codec.
#
# The idea is to have something similar to pickle, but limited to
#   simple datatypes, that can be used for networking protocols.
#
# We use a straightforward mapping between Python objects and BER,
#   with CONTEXT used to tag tuples, dicts, and sets specifically.
#
# We are aiming for compact, efficient, and fast.
#

from coro.asn1.ber cimport *
import struct

class EncodingError (Exception):
    pass

class DecodingError (Exception):
    pass

# NOTE: a streaming codec would be nice, but we would probably need to redo coro.asn1.ber
#   to achieve it.

# TODO: float/double - we'll probably use the same ASCII encoding that pickle uses.

cpdef encode (object ob):
    "BER-encode (int|long|bytes|bool|list|tuple|dict|set)*"
    if type(ob) is int:
        return _INTEGER (ob)
    elif ob is None:
        return _TLV1 (TAGS_NULL, FLAGS_UNIVERSAL, b'')
    elif type(ob) is bytes:
        return _OCTET_STRING (ob)
    elif type(ob) is unicode:
        return _UTF8_STRING (ob)
    elif type(ob) is long:
        return _TLV (TAGS_INTEGER, FLAGS_UNIVERSAL, _encode_long_integer (ob))
    elif type(ob) is bool:
        return _BOOLEAN (ob)
    elif type(ob) is list:
        return _SEQUENCE ([encode(x) for x in ob])
    elif type(ob) is tuple:
        return _TLV (0, <int>FLAGS_STRUCTURED | <int>FLAGS_CONTEXT, [encode(x) for x in ob])
    elif type(ob) is dict:
        return _TLV (1, <int>FLAGS_STRUCTURED | <int>FLAGS_CONTEXT, [encode(x) for x in ob.iteritems()])
    elif type(ob) is set:
        # Note: we can't use TAG_SET because the decoder returns it as a list
        return _TLV (2, <int>FLAGS_STRUCTURED | <int>FLAGS_CONTEXT, [encode(x) for x in ob])
    elif type(ob) is float:
        # IEEE 754 binary64
        return _TLV (3, <int>FLAGS_CONTEXT, struct.pack ('>d', ob))
    else:
        raise EncodingError (ob)

cdef _pydecode_tuple (tuple ob):
    cdef bytes kind
    cdef int tag
    (kind, tag, data) = ob
    if kind == 'context':
        if tag == 0:
            # XXX we could use PyTuple_XXX here..
            l = []
            for x in data:
                y = _pydecode (x)
                l.append (y)
            return tuple (l)
        elif tag == 1:
            # XXX likewise PyDict_XXX here...
            d = {}
            for x in data:
                k, v = _pydecode (x)
                d[k] = v
            return d
        elif tag == 2:
            return set ([_pydecode (k) for k in data])
        elif tag == 3:
            return struct.unpack ('>d', data)[0]
        else:
            raise DecodingError (ob)
    else:
        raise DecodingError (ob)

cdef _pydecode (object ob):
    if type(ob) is int:
        return ob
    elif ob is None:
        return None
    elif type(ob) is bytes:
        return ob
    elif type(ob) is unicode:
        return ob
    elif type(ob) is long:
        return ob
    elif type(ob) is bool:
        return ob
    elif type(ob) is list:
        return [_pydecode (x) for x in ob]
    elif type(ob) is tuple:
        return _pydecode_tuple (ob)
    else:
        raise DecodingError (ob)

cpdef decode (bytes s, long start = 0):
    cdef object ob0
    cdef int slen = len(s)
    cdef long pos = start
    cdef long len0 = 0
    cdef object ob1 = _decode (<unsigned char *>s, &pos, len(s), 0)
    return _pydecode (ob1), pos
