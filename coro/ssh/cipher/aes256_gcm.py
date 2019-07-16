
#
# ssh.cipher.aes256_gcm
#

from coro.ssh.cipher import SSH_Cipher_Method
from coro.sodium import aead_aes256gcm_encrypt, aead_aes256gcm_decrypt

import struct

class AES256_GCM (SSH_Cipher_Method):

    name = 'aes256-gcm@openssh.com'
    block_size = 16
    key_size = 32
    tag_size = 16
    iv_size = 12
    cipher = None
    use_mac = False

    def update_IV (self):
        fixed = self.IV[:4]
        invo = int.from_bytes (self.IV[4:], 'big')
        invo = (invo + 1) & 0xffffffffffffffff
        self.IV = fixed + invo.to_bytes (8, 'big')

    def encrypt (self, pkt, seq):
        head = len(pkt).to_bytes (4, 'big')
        ct, tag = aead_aes256gcm_encrypt (pkt, self.key, self.IV, head)
        self.update_IV()
        return head + ct, tag

    def decrypt_header (self, header, nonce):
        return header

    def decrypt_packet (self, header, ct, nonce, tag):
        pt = aead_aes256gcm_decrypt (ct, self.key, self.IV, header, tag)
        self.update_IV()
        return pt

    def set_encryption_key_and_iv (self, key, IV):
        assert (len(key) == 32)
        assert (len(IV) == 12)
        self.key = key
        self.IV = IV
