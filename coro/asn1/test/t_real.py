# -*- Mode: Python -*-

# test asn.1 real encoding

# Note: you'll need version pyasn1-0.1.4+
from pyasn1.codec.ber import decoder
from coro.asn1.ber import *

def go (f):
    d = encode_double (f)
    r = decoder.decode (d)[0]
    f0 = float (r)
    return f, f0, r, d

print go (1.0e9)
print go (3.14159265358979323846)
print go (1e1000)
print go (-1e1000)
print go (1e300)
print go (-1e300)
print go (1e-5)
print go (-1e-5)
