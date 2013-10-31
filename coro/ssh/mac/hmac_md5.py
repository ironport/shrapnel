# Copyright (c) 2002-2012 IronPort Systems and Cisco Systems
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
# ssh_hmac_md5
#
# Implements the hmac-md5 SSH MAC algorithm.

from hmac import SSH_HMAC
import hashlib

class HMAC_MD5(SSH_HMAC):

    name = 'hmac-md5'
    block_size = 64
    digest_size = 16
    key_size = 16

    def get_hash_object(self):
        return hashlib.md5()

import unittest

class ssh_hmac_md5_test_case(unittest.TestCase):
    pass

class hmac_md5_test_case(ssh_hmac_md5_test_case):

    def runTest(self):
        # From RFC2104
        a = HMAC_MD5()
        a.set_key('\x0b'*16)
        self.assertEqual(a.hmac('Hi There'), '\x92\x94\x72\x7a\x36\x38\xbb\x1c\x13\xf4\x8e\xf8\x15\x8b\xfc\x9d')

        a = HMAC_MD5()
        a.set_key('Jefe' + '\0'*12)
        self.assertEqual(a.hmac('what do ya want for nothing?'), '\x75\x0c\x78\x3e\x6a\xb0\xb5\x03\xea\xa8\x6e\x31\x0a\x5d\xb7\x38')

        a = HMAC_MD5()
        a.set_key('\xAA'*16)
        self.assertEqual(a.hmac('\xDD' * 50), '\x56\xbe\x34\x52\x1d\x14\x4c\x88\xdb\xb8\xc7\x33\xf0\xe8\xb3\xf6')

def suite():
    suite = unittest.TestSuite()
    suite.addTest(hmac_md5_test_case())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
