
#
# ssh.cipher.aes256_ctr
#
# Implements the AES256 cipher in CTR mode.
#

from coro.ssh.cipher import SSH_Cipher_Method
from Crypto.Cipher import AES
from Crypto.Util import Counter
import os

from coro.log import Facility
LOG = Facility ('aes256_ctr')

class AES256_CTR (SSH_Cipher_Method):

    name = 'aes256-ctr'
    block_size = AES.block_size
    key_size = 32
    iv_size = 16
    cipher = None

    def encrypt (self, data):
        return self.cipher.encrypt(data)

    def decrypt (self, data):
        return self.cipher.decrypt(data)

    def counter (self):
        r = ('%032x' % (self.counter_value,)).decode ('hex')
        self.counter_value += 1
        return r

    def set_encryption_key_and_iv (self, key, IV):
        self.key = key
        self.IV = IV
        self.counter_value = int (IV.encode ('hex'), 16)
        self.cipher = AES.new (key, AES.MODE_CTR, IV, counter=self.counter)
