# -*- Mode: Python -*-

# utility to convert a modern rfc5280 rsa key file to
#  an older-style rsa-only key file (for s2n).  I expect
#  s2n to will soon handle rfc5280, so this should be temporary.

import base64
from coro.asn1.ber import *

# can't use base64 module output directly,
#   PEM requires lines of length 64.
def b64_at_width (data, width=64):
    encoded = base64.encodestring (data)
    lines = encoded.split ('\n')
    oneline = ''.join (lines)
    result = []
    for i in range (0, len(oneline), 64):
        result.append (oneline[i:i+64] + '\n')
    return ''.join (result)

lines = open ('server.key', 'rb').readlines()
assert (lines[0] == '-----BEGIN PRIVATE KEY-----\n')
assert (lines[-1] == '-----END PRIVATE KEY-----\n')
der = base64.decodestring (''.join (lines[1:-1]))
d0, size = decode (der)
assert len(der) == size
assert d0[0] == 0
assert d0[1] == [('oid', [1, 2, 840, 113549, 1, 1, 1]), None]
f = open ('server.raw.key', 'wb')
f2 = open ('/tmp/x.der', 'wb')
f.write ('-----BEGIN RSA PRIVATE KEY-----\n')
f.write (b64_at_width (d0[2]))
f2.write (d0[2])
f.write ('-----END RSA PRIVATE KEY-----\n')
f.close()
f2.close()
