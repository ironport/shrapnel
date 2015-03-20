# -*- Mode: Python -*-

import hashlib
import unittest

from coro.ssl.openssl import ecdsa
from coro.test import coro_unittest

test_key = (
    '30820113020101042027a4909da59e97e1854a6d5ea26575b953d72da4cf285849ff9acce0d2156c'
    '42a081a53081a2020101302c06072a8648ce3d0101022100ffffffffffffffffffffffffffffffff'
    'fffffffffffffffffffffffefffffc2f300604010004010704410479be667ef9dcbbac55a06295ce'
    '870b07029bfcdb2dce28d959f2815b16f81798483ada7726a3c4655da4fbfc0e1108a8fd17b448a6'
    '8554199c47d08ffb10d4b8022100fffffffffffffffffffffffffffffffebaaedce6af48a03bbfd2'
    '5e8cd0364141020101a144034200042c26ab996dcc1645ea103015b0a9b008c434e2cf33f3374834'
    '0747061ab9d1070f7b6884b862c78a0ccd66cc94cf80de6de33f6b7adff73dfa19328ee3d509db'
).decode ('hex')

# XXX I think FIPS mode openssl may barf on secp256k1.

class Test (unittest.TestCase):

    def test_gen_key (self):
        e = ecdsa ("prime256v1")
        e.generate()
        h = hashlib.new ('sha256')
        h.update ('asdfasdfasdfasdfasdf')
        d = h.digest()
        sig = e.sign (d)
        self.assertEqual (e.verify (d, sig), 1)

    def test_get_keys (self):
        e = ecdsa ("prime256v1")
        e.generate()
        k = e.get_privkey()
        p = e.get_pubkey()

    def test_set_get (self):
        # in an older (or FIPS?) openssl, you can let the group params come from the private key.
        e0 = ecdsa (None)
        e0.set_privkey (test_key)
        e0.set_compressed (True)
        p = e0.get_pubkey()
        self.assertEqual (
            p,
            '032c26ab996dcc1645ea103015b0a9b008c434e2cf33f33748340747061ab9d107'.decode ('hex')
        )

    def test_714 (self):
        e0 = ecdsa (None)
        e0.set_privkey (test_key)
        h = hashlib.new ('sha256')
        h.update ('asdfasdfasdfasdfasdf')
        d = h.digest()
        sig0 = e0.sign (d)
        self.assertEqual (e0.verify (d, sig0), 1)
        e1 = ecdsa (714)  # NID_secp256k1
        e1.set_privkey (test_key)
        sig1 = e1.sign (d)
        self.assertEqual (e1.verify (d, sig1), 1)

    def test_pub_sig (self):
        e0 = ecdsa ("prime256v1")
        e0.generate()
        k0 = e0.get_privkey()
        p0 = e0.get_pubkey()
        h = hashlib.new ('sha256')
        h.update ('asdfasdfasdfasdfasdf')
        d = h.digest()
        sig = e0.sign (d)
        self.assertEqual (e0.verify (d, sig), 1)
        e1 = ecdsa ("prime256v1")
        e1.set_pubkey (p0)
        self.assertEqual (e1.verify (d, sig), 1)

    def test_compressed (self):
        e = ecdsa ("prime256v1")
        e.set_compressed (True)
        e.generate()
        p = e.get_pubkey()
        self.assertTrue (p[0] in ('\x02', '\x03'))

    def test_uncompressed (self):
        e = ecdsa ("prime256v1")
        e.set_compressed (False)
        e.generate()
        p = e.get_pubkey()
        self.assertTrue (p[0] in ('\x04'))

    def test_mode_change (self):
        e = ecdsa ("secp256k1")
        p0 = (
            '04875a41657e777b0d13f89aa765f954f78eb47d25c831de472b38e2e6792792b'
            'fe4083113bb0398cfa908dc80dd8778a6af693ff605e3ea1cd2a71037424d6260'
        ).decode ('hex')
        e.set_pubkey (p0)
        e.set_compressed (True)
        p1 = e.get_pubkey()
        self.assertEquals (
            p1,
            '02875a41657e777b0d13f89aa765f954f78eb47d25c831de472b38e2e6792792bf'.decode ("hex")
        )

if __name__ == '__main__':
    coro_unittest.run_tests()
