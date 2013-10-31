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
# ssh.keys.rsa
#
# Encapsulates the RSA key.

import hashlib
import public_private_key
from coro.ssh.util import packet
from Crypto.PublicKey import RSA
from Crypto.Util import number

# This is the DER encoding of the SHA1 identifier.
SHA1_Digest_Info = '\x30\x21\x30\x09\x06\x05\x2b\x0e\x03\x02\x1a\x05\x00\x04\x14'

class SSH_RSA(public_private_key.SSH_Public_Private_Key):

    # Features of this key type.
    supports_signature = 1
    supports_encryption = 0
    name = 'ssh-rsa'
    private_key = (0L, 0L, 0L, 0L, 0L)  # n, e, d, p, q
    public_key = (0L, 0L)       # e, n

    def set_public_key(self, public_key):
        rsa, e, n = packet.unpack_payload(RSA_PUBLIC_KEY_PAYLOAD, public_key)
        if rsa != 'ssh-rsa':
            raise ValueError, rsa
        self.public_key = (e, n)

    def set_private_key(self, private_key):
        rsa, n, e, d, p, q = packet.unpack_payload(RSA_PRIVATE_KEY_PAYLOAD, private_key)
        if rsa != 'ssh-rsa':
            raise ValueError, rsa
        self.public_key = (n, e, d, p, q)

    def get_public_key_blob(self):
        e, n = self.public_key
        return packet.pack_payload(RSA_PUBLIC_KEY_PAYLOAD,
                        ('ssh-rsa',
                         e, n))

    def get_private_key_blob(self):
        n, e, d, p, q = self.public_key
        return packet.pack_payload(RSA_PRIVATE_KEY_PAYLOAD,
                        ('ssh-rsa',
                         n, e, d, p, q))

    def emsa_pkcs1_v1_5_encode(self, message, n_len):
        """emsa_pkcs1_v1_5_encode(self, message, n_len) -> encoded_message
        Encodes the given string via the EMSA PKCS#1 version 1.5 method.

        <message> - The string to encode.
        <n_len> - The length (in octets) of the RSA modulus n.
        """
        hash = hashlib.sha1(message).digest()
        T = SHA1_Digest_Info + hash
        if __debug__:
            assert n_len >= len(T)+11
        # PKCS spec says that it's -3...I do not understand why that doesn't work.
        PS = '\xff'*(n_len - len(T) - 2)
        if __debug__:
            assert len(PS) >= 8
        return '\x00\x01' + PS + '\x00' + T

    def sign(self, message):
        n, e, d, p, q = self.private_key
        rsa_obj = RSA.construct( (n, e, d, p, q) )
        modulus_n_length_in_octets = rsa_obj.size()/8
        encoded_message = self.emsa_pkcs1_v1_5_encode(message, modulus_n_length_in_octets)
        signature = rsa_obj.sign(encoded_message, '')[0]    # Returns tuple of 1 element.
        signature = number.long_to_bytes(signature)
        return packet.pack_payload(RSA_SIG_PAYLOAD,
                                ('ssh-rsa',
                                 signature))

    def verify(self, message, signature):
        e, n = self.public_key
        rsa, blob = packet.unpack_payload(RSA_SIG_PAYLOAD, signature)
        if rsa != 'ssh-rsa':
            raise ValueError, rsa
        s = number.bytes_to_long(blob)
        rsa_obj = RSA.construct( (n, e) )
        modulus_n_length_in_octets = rsa_obj.size()/8
        encoded_message = self.emsa_pkcs1_v1_5_encode(message, modulus_n_length_in_octets)
        return rsa_obj.verify(encoded_message, (s,))

RSA_PUBLIC_KEY_PAYLOAD = (packet.STRING,  # "ssh-rsa"
                          packet.MPINT,   # e
                          packet.MPINT    # n
                         )

RSA_PRIVATE_KEY_PAYLOAD = (packet.STRING,  # "ssh-rsa"
                           packet.MPINT,   # n
                           packet.MPINT,   # e
                           packet.MPINT,   # d
                           packet.MPINT,   # p
                           packet.MPINT,   # q
                          )

RSA_SIG_PAYLOAD = (packet.STRING,  # "ssh-rsa"
                   packet.STRING   # signature_key_blob
                  )
