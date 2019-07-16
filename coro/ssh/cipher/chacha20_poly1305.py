
#
# ssh.cipher.chacha20_poly1305
#

from coro.ssh.cipher import SSH_Cipher_Method
from coro.sodium import chacha20, poly1305, poly1305_verify

import struct

class CHACHA20_POLY1305 (SSH_Cipher_Method):

    name = 'chacha20-poly1305@openssh.com'
    key_size = 64
    iv_size = 0
    cipher = None
    use_mac = False
    tag_size = 16

    def encrypt (self, pkt, seq):
        plen = len(pkt)
        hdr = plen.to_bytes (4, 'big')
        nonce = seq.to_bytes (8, 'big')
        hdr = chacha20 (self.k2, hdr, nonce, 0)
        pkt = chacha20 (self.k1, pkt, nonce, 1)
        both = hdr + pkt
        tag = poly1305 (self.k1, both, nonce)
        return both, tag

    def decrypt_header (self, header, nonce):
        return chacha20 (self.k2, header, nonce, 0)

    def decrypt_packet (self, header, data, nonce, tag):
        if poly1305_verify (self.k1, header + data, nonce, tag):
            return chacha20 (self.k1, data, nonce, 1)
        else:
            raise ValueError ("poly1305_verify failed\n")

    def set_encryption_key_and_iv (self, key, IV):
        assert (len(key) == 64)
        assert (len(IV) == 0)
        self.k1 = key[:32]
        self.k2 = key[32:]
