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
# ssh_hmac
#
# This implements the base HMAC hashing algorithm from RFC 2104.
#

from coro.ssh.mac import SSH_MAC_Method
from coro.ssh.util import str_xor
import struct

class SSH_HMAC(SSH_MAC_Method):
    """SSH_HMac

    Base class of other HMAC algorithms.
    See RFC 2104.
    """

    def get_hash_object(self):
        raise NotImplementedError

    def set_key(self, key):
        if __debug__:
            # Insecure.
            assert len(key) >= self.digest_size
        if len(key) > self.block_size:
            # Key is too big.  Hash it and use the result as the key.
            # This really isn't necessary because we're certain that the key
            # is going to be the correct size.  However, I put it in here
            # for completeness with the HMAC spec.
            import sys
            sys.stderr.write('WARNING: Unexecpted HMAC key size!!!\n')
            h = self.get_hash_object()
            self.key = h.update(key).digest()
        else:
            self.key = key

        ipad = '\x36' * self.block_size
        opad = '\x5C' * self.block_size
        padded_key = self.key + '\0' * (self.block_size-len(self.key))

        self._enc_ipad = str_xor(padded_key, ipad)
        self._enc_opad = str_xor(padded_key, opad)

    def digest(self, sequence_number, data):
        sequence_number = struct.pack('>L', sequence_number)
        return self.hmac(sequence_number + data)

    def hmac(self, data):
        # H(K XOR opad, H(K XOR ipad, text))
        hash = self.get_hash_object()
        hash.update(self._enc_ipad)
        hash.update(data)
        b = hash.digest()
        hash = self.get_hash_object()
        hash.update(self._enc_opad)
        hash.update(b)
        return hash.digest()
