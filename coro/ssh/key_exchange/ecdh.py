# -*- Mode: Python -*-

# implement ECDH key exchange

# http://www.openssh.com/txt/rfc5656.txt

# note: for now, only ed25519

import hashlib

from coro import write_stderr as W

from coro.ssh.util.packet import STRING, BYTE, MPINT, pack_payload, unpack_payload
from coro.ssh.util import debug as ssh_debug
from coro.ssh.util import random as ssh_random

from coro.ssh.key_exchange import SSH_Key_Exchange
from coro.ssh.transport import constants
from coro.ssh.keys import parse_public_key
from coro.ssh.crypto import ed25519, curve25519

from coro.ssh.util.mpint import pack_mpint


SSH_MSG_KEX_ECDH_INIT = 30
SSH_MSG_KEX_ECDH_REPLY = 31


class ECDH_CURVE25519 (SSH_Key_Exchange):

    name = 'curve25519-sha256@libssh.org'

    wants_signature_host_key = 1
    wants_encryption_host_key = 1

    def get_initial_client_kex_packet(self):
        self.transport.debug.write(ssh_debug.DEBUG_3, 'get_initial_kex_packet()')
        skey, pkey = curve25519.gen_key()
        self.secret_key = skey
        self.public_key = pkey
        return pack_payload (KEX_ECDH_INIT_PAYLOAD, (SSH_MSG_KEX_ECDH_INIT, self.public_key))

    def _get_hash_object (self):
        return hashlib.sha256()

    def get_initial_server_kex_packet(self):
        return None

    def register_client_callbacks(self):
        callbacks = {SSH_MSG_KEX_ECDH_REPLY: self.msg_kex_ecdh_reply}
        self.transport.register_callbacks(self.name, callbacks)

    def register_server_callbacks(self):
        callbacks = {SSH_MSG_KEX_ECDH_INIT: self.msg_kex_ecdh_init}
        self.transport.register_callbacks(self.name, callbacks)

    def msg_kex_ecdh_init (self, packet):
        _, q_c = unpack_payload (KEX_ECDH_INIT_PAYLOAD, packet)
        raise NotImplementedError

    def msg_kex_ecdh_reply(self, packet):
        # string    server public host key and certificates (K_S)
        # string    server's ephemeral public key (Q_S)
        # string    signature of H
        _, k_s, q_s, sig_h = unpack_payload (KEX_ECDH_REPLY_PAYLOAD, packet)

        # Verify that server public key length is 32 bytes.
        self.server_public_host_key = parse_public_key (k_s)
        assert (len (self.server_public_host_key.public_key) == 32)

        # Verify host keys belong to server.
        self.transport.verify_public_host_key (self.server_public_host_key)

        self.transport.debug.write (ssh_debug.DEBUG_3, 'public_key: %s', self.server_public_host_key.public_key.encode ('hex'))

        # Compute shared secret.
        shared_secret = curve25519.curve25519 (self.secret_key, q_s)
        # note: endian reversal.
        self.shared_secret = int (shared_secret.encode ('hex'), 16)

        self.transport.debug.write (ssh_debug.DEBUG_3, 'shared_secret: %s', hex(self.shared_secret))

        # Verify hash.
        # string   V_C, client's identification string (CR and LF excluded)
        # string   V_S, server's identification string (CR and LF excluded)
        # string   I_C, payload of the client's SSH_MSG_KEXINIT
        # string   I_S, payload of the server's SSH_MSG_KEXINIT
        # string   K_S, server's public host key
        # string   Q_C, client's ephemeral public key octet string
        # string   Q_S, server's ephemeral public key octet string
        # mpint    K,   shared secret

        H = pack_payload (
            KEX_ECDH_HASH_PAYLOAD, (
                self.c2s_version_string,
                self.s2c_version_string,
                self.c2s_kexinit_packet,
                self.s2c_kexinit_packet,
                k_s,
                self.public_key,
                q_s,
                self.shared_secret
            )
        )

        self.transport.debug.write (ssh_debug.DEBUG_3, 'to_hash: %s', H.encode ('hex'))
        # Generate exchange hash.

        self.exchange_hash = hashlib.sha256(H).digest()
        self.transport.debug.write (ssh_debug.DEBUG_3, 'exchange hash: %s', self.exchange_hash.encode ('hex'))

        if self.session_id is None:
            # The session id is the first exchange hash.
            self.session_id = self.exchange_hash

        # Verify server's signature.
        if not self.server_public_host_key.verify (self.exchange_hash, sig_h):
            self.transport.send_disconnect (
                constants.SSH_DISCONNECT_KEY_EXCHANGE_FAILED,
                'Key exchange did not succeed:  Signature did not match.'
            )



KEX_ECDH_INIT_PAYLOAD = (
    BYTE,   # SSH_MSG_KEX_ECDH_INIT = 30
    STRING, # Q_C, client's ephemeral public key
)

KEX_ECDH_REPLY_PAYLOAD = (
    BYTE,   # SSH_MSG_KEX_ECDH_REPLY = 31
    STRING, # K_S, server's public host key
    STRING, # Q_S, server's emphemeral public key
    STRING, # signature on the exchange hash
)

KEX_ECDH_HASH_PAYLOAD = (
    STRING, #   V_C, client's identification string (CR and LF excluded)
    STRING, #   V_S, server's identification string (CR and LF excluded)
    STRING, #   I_C, payload of the client's SSH_MSG_KEXINIT
    STRING, #   I_S, payload of the server's SSH_MSG_KEXINIT
    STRING, #   K_S, server's public host key
    STRING, #   Q_C, client's ephemeral public key octet string
    STRING, #   Q_S, server's ephemeral public key octet string
    MPINT,  #   K,   shared secret
)
