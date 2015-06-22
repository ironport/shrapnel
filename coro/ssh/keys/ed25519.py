# -*- Mode: Python -*-

#
# ssh.keys.ed25519
#

# https://git.libssh.org/projects/libssh.git/tree/doc/curve25519-sha256@libssh.org.txt

import hashlib
import public_private_key
from coro.ssh.util import packet
from coro.ssh.crypto import ed25519

from Crypto.PublicKey import RSA
from Crypto.Util import number

class SSH_ED25519 (public_private_key.SSH_Public_Private_Key):

    # Features of this key type.
    supports_signature = 1
    supports_encryption = 0
    name = 'ssh-ed25519'
    private_key = ''
    public_key = ''

    def set_public_key(self, public_key):
        ident, q = packet.unpack_payload (ED25519_PUBLIC_KEY_PAYLOAD, public_key)
        if ident != self.name:
            raise ValueError (ident)
        self.public_key = q

    def set_private_key(self, private_key):
        # appears to be skey:pkey concatenated.
        self.private_key = private_key[:32]
        self.public_key = private_key[32:]

    def get_public_key_blob(self):
        return packet.pack_payload (ED25519_PUBLIC_KEY_PAYLOAD, (self.name, self.public_key))

    def get_private_key_blob(self):
        return packet.pack_payload (ED25519_PUBLIC_KEY_PAYLOAD, (self.name, self.private_key))

    def sign (self, message):
        sig = ed25519.signature (message, self.private_key, self.public_key)
        return packet.pack_payload (ED25519_SIG_PAYLOAD, (self.name, sig))

    def verify (self, message, signature):
        ident, sig = packet.unpack_payload (ED25519_SIG_PAYLOAD, signature)
        if ident != self.name:
            raise ValueError (ident)
        try:
            ed25519.checkvalid (sig, message, self.public_key)
            return 1
        except:
            return 0

ED25519_PUBLIC_KEY_PAYLOAD = (
    packet.STRING,
    packet.STRING,
)

ED25519_PRIVATE_KEY_PAYLOAD = (
    packet.STRING,
    packet.STRING,
)

ED25519_SIG_PAYLOAD = (
    packet.STRING,
    packet.STRING,
)
