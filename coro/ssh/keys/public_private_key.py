# $Header: //prod/main/ap/ssh/ssh/keys/public_private_key.py#1 $

"""ssh.keys.public_private_key

This is the base public/private key object.
Specific key types subclass this for their implementation.
"""

import hashlib

class SSH_Public_Private_Key:
    """SSH_Public_Private_Key

    Base class for any type of public/private key.
    """
    name = 'none'

    # Features of this key type.
    supports_signature = 0
    supports_encryption = 0

    # Keys are encoded according to the implementation.
    private_key = None
    public_key = None

    def set_public_key(self, public_key):
        """set_public_key(self, public_key) -> None
        Sets the public key.  public_key is a string encoded according
        to the algorithm.
        """
        raise NotImplementedError

    def set_private_key(self, private_key):
        """set_private_key(self, private_key) -> None
        Sets the private key.  private_key is a string encoded according
        to the algorithm.
        """
        raise NotImplementedError

    def get_public_key_blob(self):
        raise NotImplementedError

    def get_private_key_blob(self):
        raise NotImplementedError

    def sign(self, message):
        """sign(self, message, ) -> signature
        Signs a message with the given private_key.
        <message> is a string of bytes.

        The resulting signature is encoded as a payload of (string, bytes)
        where string is the signature format identifier and byes is the
        signature blob.
        """
        raise NotImplementedError

    def verify(self, message, signature):
        """verify(self, message, signature, public_key) -> boolean
        Returns true or false if the signature is a match for the
        signature of <message>.
        <message> is a string of bytes.
        <signature> is a payload encoded as (string, bytes).
        """
        raise NotImplementedError

    def public_key_fingerprint(self):
        """public_key_fingerprint(self) -> fingerprint string
        Returns a fingerprint of the public key.
        """
        m = hashlib.md5(self.get_public_key_blob())
        # hexdigest returns lowercase already, but I just wanted to be careful.
        fingerprint = m.hexdigest().lower()
        pieces = [ fingerprint[x]+fingerprint[x+1] for x in xrange(0, len(fingerprint), 2) ]
        return ':'.join(pieces)

    # XXX: encrypt functions...
