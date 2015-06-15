
#
# ssh_hmac_sha256
#
# Implements the hmac-sha256 SSH MAC algorithm.

from hmac import SSH_HMAC
from Crypto.Hash import SHA256

class HMAC_SHA256 (SSH_HMAC):

    name = 'hmac-sha256'
    block_size = 64
    digest_size = 32
    key_size = 32

    def get_hash_object(self):
        return SHA256.new()
