# -*- Mode: Python -*-

from coro.asn1.ber import *
import unittest

# These are mostly positive test cases, need some negative ones as well.
# Though - this code *has* been through the protos c06-ldapv3-enc-r1 test suite,
#   but it's a rather large suite (89MB).  Consider automating a download of
#   the suite here?

class ber_test_case (unittest.TestCase):
    pass

class simple_test (ber_test_case):
    def runTest (self):
        x = SEQUENCE (
            SET (INTEGER(34), INTEGER(19), OCTET_STRING('fishing line')),
            OBJID ([2, 3, 4, 5, 6, 88]),
            OCTET_STRING ("spaghetti"),
            BOOLEAN(True),
            BOOLEAN(False),
        )
        self.assertEqual (
            x, '0.1\x14\x02\x01"\x02\x01\x13\x04\x0cfishing line\x06\x05S\x04\x05\x06X\x04\tspaghetti\x01\x01\xff\x01\x01\x00')  # noqa
        self.assertEqual (
            decode (x), ([[34, 19, 'fishing line'], ('oid', [2, 3, 4, 5, 6, 88]), 'spaghetti', True, False], 48))

# www.google.com cert
google_cert = """-----BEGIN CERTIFICATE-----
MIIDITCCAoqgAwIBAgIQT52W2WawmStUwpV8tBV9TTANBgkqhkiG9w0BAQUFADBM
MQswCQYDVQQGEwJaQTElMCMGA1UEChMcVGhhd3RlIENvbnN1bHRpbmcgKFB0eSkg
THRkLjEWMBQGA1UEAxMNVGhhd3RlIFNHQyBDQTAeFw0xMTEwMjYwMDAwMDBaFw0x
MzA5MzAyMzU5NTlaMGgxCzAJBgNVBAYTAlVTMRMwEQYDVQQIEwpDYWxpZm9ybmlh
MRYwFAYDVQQHFA1Nb3VudGFpbiBWaWV3MRMwEQYDVQQKFApHb29nbGUgSW5jMRcw
FQYDVQQDFA53d3cuZ29vZ2xlLmNvbTCBnzANBgkqhkiG9w0BAQEFAAOBjQAwgYkC
gYEA3rcmQ6aZhc04pxUJuc8PycNVjIjujI0oJyRLKl6g2Bb6YRhLz21ggNM1QDJy
wI8S2OVOj7my9tkVXlqGMaO6hqpryNlxjMzNJxMenUJdOPanrO/6YvMYgdQkRn8B
d3zGKokUmbuYOR2oGfs5AER9G5RqeC1prcB6LPrQ2iASmNMCAwEAAaOB5zCB5DAM
BgNVHRMBAf8EAjAAMDYGA1UdHwQvMC0wK6ApoCeGJWh0dHA6Ly9jcmwudGhhd3Rl
LmNvbS9UaGF3dGVTR0NDQS5jcmwwKAYDVR0lBCEwHwYIKwYBBQUHAwEGCCsGAQUF
BwMCBglghkgBhvhCBAEwcgYIKwYBBQUHAQEEZjBkMCIGCCsGAQUFBzABhhZodHRw
Oi8vb2NzcC50aGF3dGUuY29tMD4GCCsGAQUFBzAChjJodHRwOi8vd3d3LnRoYXd0
ZS5jb20vcmVwb3NpdG9yeS9UaGF3dGVfU0dDX0NBLmNydDANBgkqhkiG9w0BAQUF
AAOBgQAhrNWuyjSJWsKrUtKyNGadeqvu5nzVfsJcKLt0AMkQH0IT/GmKHiSgAgDp
ulvKGQSy068Bsn5fFNum21K5mvMSf3yinDtvmX3qUA12IxL/92ZzKbeVCq3Yi7Le
IOkKcGQRCMha8X2e7GmlpdWC1ycenlbN0nbVeSv3JUMcafC4+Q==
-----END CERTIFICATE-----"""

class x509_test (ber_test_case):

    def runTest (self):
        import base64
        lines = google_cert.split ('\n')
        enc = base64.decodestring (''.join (lines[1:-1]))
        self.assertEqual (
            decode (enc),
            ([[('context', 0, [2]),
               105827261859531100510423749949966875981L,
               [('oid', [1, 2, 840, 113549, 1, 1, 5]), None],
               [[[('oid', [2, 5, 4, 6]), ('PRINTABLE_STRING', 19, 'ZA')]],
                [[('oid', [2, 5, 4, 10]),
                  ('PRINTABLE_STRING', 19, 'Thawte Consulting (Pty) Ltd.')]],
                [[('oid', [2, 5, 4, 3]), ('PRINTABLE_STRING', 19, 'Thawte SGC CA')]]],
               [('UTC_TIME', 23, '111026000000Z'), ('UTC_TIME', 23, '130930235959Z')],
               [[[('oid', [2, 5, 4, 6]), ('PRINTABLE_STRING', 19, 'US')]],
                   [[('oid', [2, 5, 4, 8]), ('PRINTABLE_STRING', 19, 'California')]],
                   [[('oid', [2, 5, 4, 7]), ('T61_STRING', 20, 'Mountain View')]],
                   [[('oid', [2, 5, 4, 10]), ('T61_STRING', 20, 'Google Inc')]],
                   [[('oid', [2, 5, 4, 3]), ('T61_STRING', 20, 'www.google.com')]]],
               [[('oid', [1, 2, 840, 113549, 1, 1, 1]), None],
                ('bitstring',
                 (0,
                  "0\x81\x89\x02\x81\x81\x00\xde\xb7&C\xa6\x99\x85\xcd8\xa7\x15\t\xb9\xcf\x0f"
                  "\xc9\xc3U\x8c\x88\xee\x8c\x8d('$K*^\xa0\xd8\x16\xfaa\x18K\xcfm`\x80\xd35@2r"
                  "\xc0\x8f\x12\xd8\xe5N\x8f\xb9\xb2\xf6\xd9\x15^Z\x861\xa3\xba\x86\xaak\xc8\xd9"
                  "q\x8c\xcc\xcd'\x13\x1e\x9dB]8\xf6\xa7\xac\xef\xfab\xf3\x18\x81\xd4$F\x7f\x01w|"
                  "\xc6*\x89\x14\x99\xbb\x989\x1d\xa8\x19\xfb9\x00D}\x1b\x94jx-i\xad\xc0z,\xfa\xd0"
                  "\xda \x12\x98\xd3\x02\x03\x01\x00\x01"))],
               ('context',
                3,
                [[[('oid', [2, 5, 29, 19]), True, '0\x00'],
                  [('oid', [2, 5, 29, 31]),
                   "0-0+\xa0)\xa0'\x86%http://crl.thawte.com/ThawteSGCCA.crl"],
                  [('oid', [2, 5, 29, 37]),
                   '0\x1f\x06\x08+\x06\x01\x05\x05\x07\x03\x01\x06\x08+\x06\x01\x05\x05\x07\x03'
                   '\x02\x06\t`\x86H\x01\x86\xf8B\x04\x01'],
                  [('oid', [1, 3, 6, 1, 5, 5, 7, 1, 1]),
                   '0d0"\x06\x08+\x06\x01\x05\x05\x070\x01\x86\x16http://ocsp.thawte.com0>\x06'
                   '\x08+\x06\x01\x05\x05\x070\x02\x862http://www.thawte.com/repository/Thawte_SGC_CA.crt']]])],
              [('oid', [1, 2, 840, 113549, 1, 1, 5]), None],
              ('bitstring',
               (0,
                "!\xac\xd5\xae\xca4\x89Z\xc2\xabR\xd2\xb24f\x9dz\xab\xee\xe6|\xd5~\xc2\\("
                "\xbbt\x00\xc9\x10\x1fB\x13\xfci\x8a\x1e$\xa0\x02\x00\xe9\xba[\xca\x19\x04"
                "\xb2\xd3\xaf\x01\xb2~_\x14\xdb\xa6\xdbR\xb9\x9a\xf3\x12\x7f|\xa2\x9c;o\x99"
                "}\xeaP\rv#\x12\xff\xf7fs)\xb7\x95\n\xad\xd8\x8b\xb2\xde \xe9\npd\x11\x08"
                "\xc8Z\xf1}\x9e\xeci\xa5\xa5\xd5\x82\xd7'\x1e\x9eV\xcd\xd2v\xd5y+\xf7%C\x1c"
                "i\xf0\xb8\xf9"))],
                805)
        )
        dec, length = decode (enc)
        public_key = dec[0][6][1][1][1]
        self.assertEqual (
            decode (public_key),
            ([156396091895984667473837837332877995558144703880815901117439532534031286131520903863087599986938779606924811933611903716377206837300122262900786662124968110191717844999183338594373129421417536020806373385428322642107305024162536996222164292639147591878860587271770855626780464602884552232097424473091745159379L, 65537], 140)  # noqa
        )

class bignum_test (ber_test_case):

    def runTest (self):
        self.assertEquals (
            decode ('\x02\x82\x04\xe3\x01' + '\x00' * 1250),
            (1 << 10000, 1255)
        )
        self.assertEquals (
            INTEGER (1 << 10000),
            '\x02\x82\x04\xe3\x01' + '\x00' * 1250,
        )

class bignum_test_2 (ber_test_case):

    def runTest (self):
        for i in range (5):
            n = 1 << (10 ** i)
            self.assertEquals (
                decode (INTEGER (n))[0],
                n
            )

class bignum_test_3 (ber_test_case):

    def runTest (self):
        import random
        n = 1
        for x in range (10000):
            n = n * 10 + random.randint (0, 10)
        print n
        self.assertEquals (decode (INTEGER (n))[0], n)

class zero_length_tests (ber_test_case):

    # tests for Issue #71.
    def runTest (self):
        self.assertEquals (
            # zero-length boolean
            decode (SEQUENCE ('\x01\x00', INTEGER (3141))),
            ([False, 3141], 8)
        )
        self.assertEquals (
            # zero-length bitstring
            decode (SEQUENCE ('\x03\x00', INTEGER (3141))),
            ([('bitstring', (0, '')), 3141], 8)
        )
        # zero-length OBJID
        with self.assertRaises (InsufficientData):
            decode ('\x06\x00')

def suite():
    suite = unittest.TestSuite()
    suite.addTest (simple_test())
    suite.addTest (x509_test())
    suite.addTest (bignum_test())
    suite.addTest (bignum_test_2())
    suite.addTest (bignum_test_3())
    suite.addTest (zero_length_tests())
    return suite

if __name__ == '__main__':
    unittest.main (defaultTest='suite')
