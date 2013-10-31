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
# ssh.keys.dss
#
# Encapsulates the DSS key.

import public_private_key
import hashlib
from coro.ssh.util import packet, random
from Crypto.PublicKey import DSA
from Crypto.Util import number

class SSH_DSS(public_private_key.SSH_Public_Private_Key):

    # Features of this key type.
    supports_signature = 1
    supports_encryption = 0
    name = 'ssh-dss'
    # why not store these as attributes?
    # p, q, g, y
    private_key = (0L, 0L, 0L, 0L, 0L)
    # p, q, g, y, x
    public_key = (0L, 0L, 0L, 0L)

    def set_public_key(self, public_key):
        dss, p, q, g, y = packet.unpack_payload(DSS_PUBLIC_KEY_PAYLOAD, public_key)
        if dss != 'ssh-dss':
            raise ValueError, dss
        self.public_key = (p, q, g, y)

    set_public_key.__doc__ = public_private_key.SSH_Public_Private_Key.set_public_key.__doc__

    def set_private_key(self, private_key):
        dss, p, q, g, y, x = packet.unpack_payload(DSS_PRIVATE_KEY_PAYLOAD, private_key)
        if dss != 'ssh-dss':
            raise ValueError, dss
        self.private_key = (p, q, g, y, x)

    set_private_key.__doc__ = public_private_key.SSH_Public_Private_Key.set_private_key.__doc__

    def get_public_key_blob(self):
        if self.public_key != (0, 0, 0, 0):
            p, q, g, y = self.public_key
        else:
            p, q, g, y, x = self.private_key
        return packet.pack_payload(DSS_PUBLIC_KEY_PAYLOAD,
                        ('ssh-dss',
                         p, q, g, y))

    get_public_key_blob.__doc__ = public_private_key.SSH_Public_Private_Key.get_public_key_blob.__doc__

    def get_private_key_blob(self):
        p, q, g, y, x = self.private_key
        return packet.pack_payload(DSS_PRIVATE_KEY_PAYLOAD,
                        ('ssh-dss',
                         p, q, g, y, x))

    get_private_key_blob.__doc__ = public_private_key.SSH_Public_Private_Key.get_private_key_blob.__doc__

    def create (self, size=1024):
        key = DSA.generate (size)
        self.private_key = (key.p, key.q, key.g, key.y, key.x)
        self.public_key = (key.p, key.q, key.g, key.y)

    def sign(self, message):
        p, q, g, y, x = self.private_key
        dsa_obj = DSA.construct( (y, g, p, q, x) )
        message_hash = hashlib.sha1(message).digest()
        # Get a random number that is greater than 2 and less than q.
        random_number = random.get_random_number_from_range(2, q)
        random_data = number.long_to_bytes(random_number)
        r, s = dsa_obj.sign(message_hash, random_data)
        signature = number.long_to_bytes(r, 20) + number.long_to_bytes(s, 20)
        return packet.pack_payload(DSS_SIG_PAYLOAD,
                            ('ssh-dss',
                             signature))

    sign.__doc__ = public_private_key.SSH_Public_Private_Key.sign.__doc__

    def verify(self, message, signature):
        p, q, g, y = self.public_key
        dss, blob = packet.unpack_payload(DSS_SIG_PAYLOAD, signature)
        if dss != 'ssh-dss':
            raise ValueError, dss
        # blob is the concatenation of r and s
        # r and s are 160-bit (20-byte) integers in network-byte-order
        assert( len(blob) == 40 )
        r = number.bytes_to_long(blob[:20])
        s = number.bytes_to_long(blob[20:])
        dsa_obj = DSA.construct( (y, g, p, q) )
        hash_of_message = hashlib.sha1(message).digest()
        return dsa_obj.verify(hash_of_message, (r, s))

    verify.__doc__ = public_private_key.SSH_Public_Private_Key.verify.__doc__

DSS_PUBLIC_KEY_PAYLOAD = (packet.STRING,  # "ssh-dss"
                          packet.MPINT,   # p
                          packet.MPINT,   # q
                          packet.MPINT,   # g
                          packet.MPINT    # y
                         )

DSS_PRIVATE_KEY_PAYLOAD = (packet.STRING,  # "ssh-dss"
                           packet.MPINT,   # p
                           packet.MPINT,   # q
                           packet.MPINT,   # g
                           packet.MPINT,   # y
                           packet.MPINT,   # x
                          )


DSS_SIG_PAYLOAD = (packet.STRING,  # "ssh-dss"
                   packet.STRING   # signature_key_blob
                  )
