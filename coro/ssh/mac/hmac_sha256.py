
#
# ssh_hmac_sha256
#
# Implements the hmac-sha2-256 SSH MAC algorithm.

from .hmac import SSH_HMAC
from coro.sodium import SHA256

class HMAC_SHA256 (SSH_HMAC):

    name = 'hmac-sha2-256'
    block_size = 64
    digest_size = 32
    key_size = 32

    def get_hash_object(self):
        return SHA256()
