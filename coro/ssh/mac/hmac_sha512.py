
#
# ssh_hmac_sha512
#
# Implements the hmac-sha2-512 SSH MAC algorithm.

from .hmac import SSH_HMAC
from coro.sodium import SHA512

class HMAC_SHA512 (SSH_HMAC):

    name = 'hmac-sha2-512'
    block_size = 128
    digest_size = 64
    key_size = 64

    def get_hash_object(self):
        return SHA512()
