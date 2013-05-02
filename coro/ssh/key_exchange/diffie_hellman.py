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
# ssh.key_exchange.diffie_hellman
#
# This module implements the Diffie Hellman Group 1 SHA1 key exchange.
#

__version__ = '$Revision: #1 $'

import hashlib

from coro import write_stderr as W

from coro.ssh.util import packet as ssh_packet
from coro.ssh.util import debug as ssh_debug
from coro.ssh.util import random as ssh_random

from coro.ssh.key_exchange import SSH_Key_Exchange
from coro.ssh.transport import constants
from coro.ssh.keys import parse_public_key

# 2**1024 - 2**960 - 1 + 2**64 * floor( 2**894 Pi + 129093 )
DH_PRIME = 179769313486231590770839156793787453197860296048756011706444423684197180216158519368947833795864925541502180565485980503646440548199239100050792877003355816639229553136239076508735759914822574862575007425302077447712589550957937778424442426617334727629299387668709205606050270810842907692932019128194467627007L
DH_GENERATOR = 2L

SSH_MSG_KEXDH_INIT      = 30
SSH_MSG_KEXDH_REPLY     = 31

class Diffie_Hellman_Group1_SHA1(SSH_Key_Exchange):

    name = 'diffie-hellman-group1-sha1'

    # What type of host key features this kex algorithm wants.
    wants_signature_host_key = 1
    wants_encryption_host_key = 0

    client_random_value = ''    # x
    client_exchange_value = 0L  # e
    server_public_host_key = None # k_s

    server_random_value = ''    # y
    server_exchange_value = 0L  # f

    def get_initial_client_kex_packet(self):
        self.transport.debug.write(ssh_debug.DEBUG_3, 'get_initial_kex_packet()')
        # Send initial key.
        # This is x.
        self.client_random_value = ssh_random.get_random_number(512)
        # p is large safe prime (DH_PRIME)
        # g is a generator for a subgroup of GF(p) (DH_GENERATOR)
        # compute e=g**x mod p
        self.client_exchange_value = pow(DH_GENERATOR, self.client_random_value, DH_PRIME)
        return ssh_packet.pack_payload(KEXDH_INIT_PAYLOAD,
                                            (SSH_MSG_KEXDH_INIT,
                                             self.client_exchange_value)
                                           )

    def get_initial_server_kex_packet(self):
        return None

    def _get_hash_object(self):
        """_get_hash_object(self) -> hash_object
        Return a raw hash object (see get_hash_object).
        """
        return hashlib.sha1()

    def register_client_callbacks(self):
        callbacks = {SSH_MSG_KEXDH_REPLY: self.msg_kexdh_reply}
        self.transport.register_callbacks(self.name, callbacks)

    def register_server_callbacks(self):
        callbacks = {SSH_MSG_KEXDH_INIT: self.msg_kexdh_init}
        self.transport.register_callbacks(self.name, callbacks)

    def msg_kexdh_init (self, packet):
        msg, self.client_exchange_value = ssh_packet.unpack_payload (KEXDH_INIT_PAYLOAD, packet)
        # XXX make sure e is a valid number
        W ('kexdh: self.client_exchange_value=%r\n' % (self.client_exchange_value,))
        # This is y.
        self.server_random_value = ssh_random.get_random_number(512)
        # p is large safe prime (DH_PRIME)
        # g is a generator for a subgroup of GF(p) (DH_GENERATOR)
        # compute f=g**y mod p
        self.server_exchange_value = pow(DH_GENERATOR, self.server_random_value, DH_PRIME)
        self.shared_secret = pow (self.server_exchange_value, self.client_exchange_value, DH_PRIME)
        # find my public key
        for key in self.transport.server_keys:
            if key.name == 'ssh-dss':
                K_S = key.get_public_key_blob()
                break
        else:
            raise ValueError ("no dss key?")
        W ('kexdh: K_S=%r\n' % (K_S,))
        H = ssh_packet.pack_payload (
            KEXDH_HASH_PAYLOAD, (
                self.c2s_version_string,
                self.s2c_version_string,
                self.c2s_kexinit_packet,
                self.s2c_kexinit_packet,
                K_S,
                self.client_exchange_value,
                self.server_exchange_value,
                self.shared_secret
                )
            )
        self.exchange_hash = hashlib.sha1(H).digest()
        if self.session_id is None:
            # The session id is the first exchange hash.
            self.session_id = self.exchange_hash
        H_sig = key.sign (self.exchange_hash)
        W ('kexdh: sending KEXDH_REPLY\n')
        self.transport.send_packet (
            ssh_packet.pack_payload (
                KEXDH_REPLY_PAYLOAD, (
                    SSH_MSG_KEXDH_REPLY,
                    K_S,
                    self.server_exchange_value,
                    H_sig
                    )
                )
            )

    def msg_kexdh_reply(self, packet):
        # string    server public host key and certificates (K_S)
        # mpint     f
        # string    signature of H
        msg, public_host_key, server_exchange_value, signature_of_h = ssh_packet.unpack_payload(KEXDH_REPLY_PAYLOAD, packet)

        W ('kexdh: KEXDH_REPLY public host blob = %r\n' % (public_host_key,))
        # Create a SSH_Public_Private_Key instance from the packed string.
        self.server_public_host_key = parse_public_key(public_host_key)

        # Verify that this is a known host key.
        self.transport.verify_public_host_key(self.server_public_host_key)

        # Make sure f is a valid number
        if server_exchange_value <= 1 or server_exchange_value >= DH_PRIME-1:
            self.transport.send_disconnect(constants.SSH_DISCONNECT_KEY_EXCHANGE_FAILED, 'Key exchange did not succeed: Server exchange value not valid.')

        # K = f**x mod p
        self.shared_secret = pow(server_exchange_value, self.client_random_value, DH_PRIME)
        # Verify hash.
        # string    V_C, the client's version string (CR and NL excluded)
        # string    V_S, the server's version string (CR and NL excluded)
        # string    I_C, the payload of the client's SSH_MSG_KEXINIT
        # string    I_S, the payload of the server's SSH_MSG_KEXINIT
        # string    K_S, the host key
        # mpint     e, exchange value sent by the client
        # mpint     f, exchange value sent by the server
        # mpint     K, the shared secret
        H = ssh_packet.pack_payload(KEXDH_HASH_PAYLOAD,
                                 (self.c2s_version_string,
                                 self.s2c_version_string,
                                 self.c2s_kexinit_packet,
                                 self.s2c_kexinit_packet,
                                 public_host_key,
                                 self.client_exchange_value,
                                 server_exchange_value,
                                 self.shared_secret))
        # Double check that the signature from the server matches our signature.
        hash = hashlib.sha1(H)
        self.exchange_hash = hash.digest()
        if self.session_id is None:
            # The session id is the first exchange hash.
            self.session_id = self.exchange_hash

        if not self.server_public_host_key.verify(self.exchange_hash, signature_of_h):
            self.transport.send_disconnect(constants.SSH_DISCONNECT_KEY_EXCHANGE_FAILED, 'Key exchange did not succeed:  Signature did not match.')

        # Finished...
        self.transport.send_newkeys()

KEXDH_REPLY_PAYLOAD = (ssh_packet.BYTE,
                       ssh_packet.STRING,      # public host key and certificates (K_S)
                       ssh_packet.MPINT,       # f
                       ssh_packet.STRING       # signature of H
                      )

KEXDH_INIT_PAYLOAD = (ssh_packet.BYTE,
                      ssh_packet.MPINT    # e
                     )

KEXDH_HASH_PAYLOAD = (ssh_packet.STRING, # V_C, the client's version string (CR and NL excluded)
                      ssh_packet.STRING, # V_S, the server's version string (CR and NL excluded)
                      ssh_packet.STRING, # I_C, the payload of the client's SSH_MSG_KEXINIT
                      ssh_packet.STRING, # I_S, the payload of the server's SSH_MSG_KEXINIT
                      ssh_packet.STRING, # K_S, the host key
                      ssh_packet.MPINT,  # e, exchange value sent by the client
                      ssh_packet.MPINT,  # f, exchange value sent by the server
                      ssh_packet.MPINT   # K, the shared secret
                     )
