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
# ssh.key_exchange
#
# This is the generic key exchange system.
# Currently the SSH spec only defines one key exchange method (diffie hellman),
# but in theory you could create your own method.
#

from coro.ssh.util import packet as ssh_packet
from coro.ssh.util import debug as ssh_debug

class SSH_Key_Exchange:
    """SSH_Key_Exchange

    Base class for any type of key exchange.
    """
    name = 'none'

    # What type of host key features this kex algorithm wants.
    wants_signature_host_key = 0
    wants_encryption_host_key = 0

    shared_secret = None
    exchange_hash = None

    # session_id is the session identifier for this connection.
    # It is the value of the very first exchange_hash.  If new keys are
    # exchanged, this will stay the same.
    session_id = None

    c2s_version_string = ''
    s2c_version_string = ''
    s2c_kexinit_packet = ''
    c2s_kexinit_packet = ''

    # The SSH_Transport.
    transport = None

    def __init__(self, transport):
        self.supported_server_keys = []
        self.transport = transport

    def get_initial_client_kex_packet(self):
        """get_initial_client_kex_packet(self) -> packet
        Get the very first packet of the key exchange to be sent by the client.
        If the key exchange algorithm does not support the client sending
        the first packet, then this function should return None.
        """
        raise NotImplementedError

    def get_initial_server_kex_packet(self):
        """get_initial_server_kex_packet(self) -> packet
        Get the very first packet of the key exchange to be sent by the server.
        If the key exchange algorithm does not support the server sending
        the first packet, then this function should return None.
        """
        raise NotImplementedError

    def register_client_callbacks(self):
        """register_client_callbacks(self) -> None
        Register callbacks necessary to handle the client side.
        """
        raise NotImplementedError

    def register_server_callbacks(self):
        """register_server_callbacks(self) -> None
        Register callbacks necessary to handle the server side.
        """
        raise NotImplementedError

    def get_hash_object(self, *args):
        """get_hash_object(self, *args) -> hash_object
        This returns a hash object.
        This object must have the same API as the sha and md5 modules in
        standard python:
            - update(str)
            - digest()
            - hexdigest()
            - copy()

        Additional args are added to the hash object via update().
        """
        hash_object = self._get_hash_object()
        for arg in args:
            hash_object.update(arg)
        return hash_object

    def _get_hash_object(self):
        """_get_hash_object(self) -> hash_object
        Return a raw hash object (see get_hash_object).
        """
        raise NotImplementedError

    def get_encryption_key(self, letter, required_size):
        """get_encryption_key(self, letter, required_size) -> key
        Computes an encryption key with the given letter.
        <required_size> is the length of the key that you require (in bytes).
        """
        shared_secret = ssh_packet.pack_payload((ssh_packet.MPINT,), (self.shared_secret,))
        key = self.get_hash_object(
                shared_secret,
                self.exchange_hash,
                letter,
                self.session_id).digest()
        if len(key) > required_size:
            # Key is too big...return only what is needed.
            key = key[:required_size]
        elif len(key) < required_size:
            # Key is not big enough...compute additional hashes until big enough.
            # K1 = HASH(K || H || X || session_id)   (X is e.g. "A")
            # K2 = HASH(K || H || K1)
            # K3 = HASH(K || H || K1 || K2)
            # ...
            # key = K1 || K2 || K3 || ...
            self.transport.debug.write(ssh_debug.DEBUG_2, 'get_encryption_key: computed key is too small len(key)=%i required_size=%i', (len(key), required_size))
            key_data = [key]
            key_data_len = len(key)
            while key_data_len < required_size:
                additional_key_data = self.get_hash_object(shared_secret, self.exchange_hash, ''.join(key_data)).digest()
                key_data.append(additional_key_data)
                key_data_len += len(additional_key_data)
            key = ''.join(key_data)[:required_size]
        else:
            # Key is just the right length.
            pass
        return key

    def set_info(self, c2s_version_string, s2c_version_string, c2s_kexinit_packet, s2c_kexinit_packet, supported_server_keys):
        self.c2s_version_string = c2s_version_string
        self.s2c_version_string = s2c_version_string
        self.c2s_kexinit_packet = c2s_kexinit_packet
        self.s2c_kexinit_packet = s2c_kexinit_packet
        self.supported_server_keys = supported_server_keys

    def get_key_algorithm(self, key):
        name = ssh_packet.unpack_payload( (ssh_packet.STRING,), key)[0]
        for key_alg in self.supported_server_keys:
            if key_alg.name == name:
                return key_alg
        raise ValueError, name
