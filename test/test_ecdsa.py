# -*- Mode: Python -*-

import hashlib
import unittest

import coro.ssl.openssl
import coro_unittest

class Test (unittest.TestCase):

    def test_gen_key (self):
        e = coro.ssl.openssl.ecdsa ("secp256k1")
        e.generate()
        h = hashlib.new ('sha256')
        h.update ('asdfasdfasdfasdfasdf')
        d = h.digest()
        sig = e.sign (d)
        self.assertEqual (e.verify (d, sig), 1)

    def test_get_keys (self):
        e = coro.ssl.openssl.ecdsa ("secp256k1")
        e.generate()
        k = e.get_privkey()
        p = e.get_pubkey()

    def test_pub_sig (self):
        e0 = coro.ssl.openssl.ecdsa ("secp256k1")
        e0.generate()
        k0 = e0.get_privkey()
        p0 = e0.get_pubkey()
        h = hashlib.new ('sha256')
        h.update ('asdfasdfasdfasdfasdf')
        d = h.digest()
        sig = e0.sign (d)
        self.assertEqual (e0.verify (d, sig), 1)
        e1 = coro.ssl.openssl.ecdsa ("secp256k1")
        e1.set_pubkey (p0)
        self.assertEqual (e1.verify (d, sig), 1)

if __name__ == '__main__':
    coro_unittest.run_tests()
