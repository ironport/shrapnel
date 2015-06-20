# -*- Mode: Python -*-

# based on code from here:
# https://code.google.com/p/iphone-dataprotection/
#   in python_scripts/crypto/curve25519

# based on PyCrypto.Util.number.inverse
def inverse (u0, v0):
    u3, v3 = u0, v0
    u1, v1 = 1, 0
    while v3 > 0:
        q, _   = divmod (u3, v3)
        u1, v1 = v1, u1 - v1*q
        u3, v3 = v3, u3 - v3*q
    while u1 < 0:
        u1 = u1 + v0
    return u1

def b2n (s):
    # little-endian, bytes -> number
    return int (s[::-1].encode ('hex'), 16)

def n2b (n, reverse=False):
    # little-endian, number -> bytes
    return ('%064x' % n).decode ('hex')[::-1]

P = 2**255 - 19
# this is actually (A-2)/4
A = 121665

def curve25519_mult(n, q):

    def monty (x1, z1, x2, z2, qmqp):
        a = (x1 + z1) * (x2 - z2) % P
        b = (x1 - z1) * (x2 + z2) % P
        x4 = (a + b) * (a + b) % P
        e = (a - b) * (a - b) % P
        z4 = e * qmqp % P
        a = (x1 + z1) * (x1 + z1) % P
        b = (x1 - z1) * (x1 - z1) % P
        x3 = a * b % P
        g = (a - b) % P
        h = (a + A * g) % P
        z3 = (g * h) % P
        return x3, z3, x4, z4

    nqpqx, nqpqz = q, 1
    nqx, nqz = 1, 0
    for i in range (255, -1, -1):
        if (n >> i) & 1:
            nqpqx, nqpqz, nqx, nqz = monty (nqpqx, nqpqz, nqx, nqz, q)
        else:
            nqx, nqz, nqpqx, nqpqz = monty (nqx, nqz, nqpqx, nqpqz, q)

    return (nqx * inverse (nqz, P)) % P

def adjust (k):
    a = ord(k[0])
    a &= 248
    b = ord(k[31])
    b &= 127
    b |= 64
    return chr(a) + k[1:-1] + chr(b)

def curve25519 (sk, pk):
    skn = b2n (adjust (sk))
    pkn = b2n (pk)
    return n2b (curve25519_mult (skn, pkn))

def gen_key():
    import os
    sk = adjust (os.urandom (32))
    return sk, curve25519 (sk, n2b (9))

# --------------------------------------------------------------------------------

def test():
    k0 = "62ca760c588569cc6cdaea397ddfbe8d0a04ce69c141391abbdd24f5f473f6ab".decode ('hex')
    k1 = "1cb967a181bb05edcdd2b82e1d3bcd10bf6a83739065e247ab0798d21e387520".decode ('hex')
    p0 = "162e9fac9a1ec8853463a342d125a7d378848050030d06588e5ff7d67c828e5a".decode ('hex')
    p1 = "cb624d49243142ad79452e8f37ae77fb1235609a8336c087429a2a3998681b21".decode ('hex')
    assert curve25519 (k0, p1) == curve25519 (k1, p0)
    assert curve25519 (k0, n2b (9)) == p0

if __name__ == '__main__':
    test()
