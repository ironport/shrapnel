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
# ssh_transport
#
# This module implements the SSH Transport layer.
# This is the lowest-level layer of the SSH Protocol.  It does NOT implement
# authentication or anything else.
#
# This implements the SSH2 protocol ONLY.
#

import coro
import struct
import sys

from coro.ssh.util import random, pick_from_list
from coro.ssh.util import debug as ssh_debug
from coro.ssh.util import packet as ssh_packet
from coro.ssh.transport import SSH_Protocol_Error

from coro.ssh.transport.constants import *
from coro.ssh.key_exchange.diffie_hellman import Diffie_Hellman_Group1_SHA1
from coro.ssh.keys.dss import SSH_DSS
from coro.ssh.keys.rsa import SSH_RSA
from coro.ssh.cipher.des3_cbc import Triple_DES_CBC
from coro.ssh.cipher.blowfish_cbc import Blowfish_CBC
from coro.ssh.mac.hmac_sha1 import HMAC_SHA1
from coro.ssh.mac.hmac_md5 import HMAC_MD5
from coro.ssh.mac.none import MAC_None
from coro.ssh.cipher.none import Cipher_None
from coro.ssh.compression.none import Compression_None
from coro.ssh.keys.openssh_key_storage import OpenSSH_Key_Storage

from coro import write_stderr as W

class SSH_Transport:

    # The low-level OS transport abstraction.
    transport = None

    # These are references to the in-use entry from one of the
    # supported_xxx lists.
    # These two values are not set until after we have received the remote
    # side's kexinit packet.  (Thus, you can not rely on them when making
    # a proactive guess before the kexinit packet has arrived.)
    key_exchange = None
    server_key = None

    # Set this to true if we failed to guess the correct kex algorithm.
    ignore_first_packet = False

    # Normally One_Way_SSH_Transport instances.
    # You can subclass this class to use a different
    # transport that supports different algorithms.
    c2s = None  # client to server ssh transport
    s2c = None  # server to client ssh transport

    # These are references to the appropriate c2s or s2c object.
    self2remote = None
    remote2self = None

    # List of key_storage instances.
    supported_key_storages = None

    # Boolean whether or not we are the server.
    is_server = False

    # Thread object for reading from the socket.
    _receive_thread = None

    # Flag to indicate whether or not this connection is closed.
    closed = True

    def __init__(self, client_transport=None, server_transport=None, debug=None):
        self.tmc = Thread_Message_Callbacks()
        self.send_mutex = coro.mutex()
        # This is the registry of modules that want to receive certain messages.
        # The key is the module name, the value is a dictionary of message number
        # to callback function.  The function takes 1 parameter (the packet).
        self.message_callback_registry = {}
        # This is a mapping of SSH message numbers to the function to call when
        # that message is received.  It is an optimized version computed from
        # message_callback_registry.
        self.message_callbacks = {}

        if debug is None:
            self.debug = ssh_debug.Debug()
        else:
            self.debug = debug
        if client_transport is None:
            self.c2s = One_Way_SSH_Transport(self)
        else:
            self.c2s = client_transport
        if server_transport is None:
            self.s2c = One_Way_SSH_Transport(self)
        else:
            self.s2c = server_transport
        self.supported_key_storages = [OpenSSH_Key_Storage()]
        # XXX who/what sets self.is_server?  can we use self.is_server
        #     to decide which callbacks to register?  Or should that be done
        #     by the subclass?
        self.register_callbacks('__base__',
                                {SSH_MSG_IGNORE: self.msg_ignore,
                                 SSH_MSG_DEBUG: self.msg_debug,
                                 SSH_MSG_DISCONNECT: self.msg_disconnect,
                                 SSH_MSG_UNIMPLEMENTED: self.msg_unimplemented,
                                 # SSH_MSG_KEXINIT:self.msg_kexinit,
                                 SSH_MSG_NEWKEYS: self.msg_newkeys,
                                 }
                                )

    def unregister_callbacks(self, module_name):
        """unregister_callbacks(self, module_name) -> None
        Remove the given module from the registry.
        """
        try:
            del self.message_callback_registry[module_name]
        except KeyError:
            pass
        self._recompile_callback_registry()

    def register_callbacks(self, module_name, callback_dict):
        """register_callbacks(self, module_name, callback_dict) -> None
        Registers the given module_name (a string) the given callbacks.
        <callback_dict> is a dictionary of message number to callback function.

        If there were callbacks previously registered under the same name,
        this will clear the previous values.

        If more than one module is listening for the same message numbers,
        it is not deterministic which one will receive the message.
        In other words, don't do that!
        Also, beware that some message numbers can be the same even if they
        are referenced with different names.  An example is
        SSH_MSG_KEX_DH_GEX_GROUP and SSH_MSG_KEXDH_REPLY both are the
        number 31.
        """
        self.debug.write(ssh_debug.DEBUG_3, 'register_callbacks(module_name=%s, callback_dict=...)', (module_name,))
        self.message_callback_registry[module_name] = callback_dict
        self._recompile_callback_registry()

    def _recompile_callback_registry(self):
        # Recompile message_callbacks
        self.message_callbacks = {}
        for dictn in self.message_callback_registry.values():
            self.message_callbacks.update(dictn)

    def disconnect(self):
        """disconnect(self) -> None
        Closes the connection.
        """
        if not self.closed:
            self.stop_receive_thread()
            self.closed = True

    # Make an alias.
    close = disconnect

    def send_disconnect(self, reason_code, description):
        """send_disconnect(self, reason_code, description) -> None
        """
        self.debug.write(
            ssh_debug.DEBUG_3, 'send_disconnect(reason_code=%r, description=%r)', (reason_code, description))
        # Language tag currently set to the empty string.
        language_tag = ''
        self.send_packet(
            ssh_packet.pack_payload (
                ssh_packet.PAYLOAD_MSG_DISCONNECT,
                (SSH_MSG_DISCONNECT,
                 reason_code,
                 description,
                 language_tag)
            )
        )
        self.disconnect()
        raise SSH_Protocol_Error(reason_code, description)

    def send (self, format, values):
        self.send_packet (ssh_packet.pack_payload (format, values))

    def send_packet(self, data):
        """send_packet(self, data) -> None
        Sends the given packet data.
        <data>: A string.
        """
        self.send_mutex.lock()
        try:
            try:
                self._send_packet(data)
            except:
                # Any error is fatal.
                self.disconnect()
                raise
        finally:
            self.send_mutex.unlock()

    def _send_packet(self, data):
        # Packet is:
        # uint32 packet_length
        # byte padding_length
        # byte[n1] payload
        # byte[n2] random padding
        # byte[m] MAC
        self.debug.write(ssh_debug.DEBUG_3, 'send_packet( len(data)=%i )', (len(data),))
        data = self.self2remote.compression.compress(data)

        # packet_len + padding_length + payload + random_padding
        # must be multiple of cipher block size.
        block_size = max(8, self.self2remote.cipher.block_size)
        padding_length = block_size - ((5 + len(data)) % block_size)
        if padding_length < 4:
            padding_length += block_size
        # Total packet size must also be at least 16 bytes.
        base_size = 5 + len(data) + padding_length
        minimum_size = max(16, block_size)
        if base_size < minimum_size:
            self.debug.write(ssh_debug.DEBUG_2, 'send_packet: base size too small')
            # Add enough padding to make it big enough.
            # Make a first guess of the padding length.
            padding_length_guess = minimum_size - base_size
            # See how much larger it should be to make it a multiple of the
            # block size.
            additional_padding_length = block_size - ((5 + len(data) + padding_length_guess) % block_size)
            padding_length = padding_length_guess + additional_padding_length

        self.debug.write(ssh_debug.DEBUG_2, 'send_packet: padding_length=%i', (padding_length,))
        self.debug.write(ssh_debug.DEBUG_2, 'send_packet: cipher=%s', (self.self2remote.cipher.name,))

        packet_length = 1 + len(data) + padding_length
        self.debug.write(ssh_debug.DEBUG_2, 'send_packet: packet_length=%i', (packet_length,))

        random_padding = random.get_random_data(padding_length)
        chunk = struct.pack('>Ic', packet_length, chr(padding_length)) + data + random_padding
        self.debug.write(ssh_debug.DEBUG_2, 'send_packet: chunk_length=%i', (len(chunk),))

        mac = self.self2remote.mac.digest(self.self2remote.packet_sequence_number, chunk)
        self.self2remote.inc_packet_sequence_number()
        self.debug.write(ssh_debug.DEBUG_2, 'send_packet: mac=%r', (mac,))

        # self.debug.write(ssh_debug.DEBUG_2, 'send_packet: chunk=%r', (chunk,))
        encrypted_chunk = self.self2remote.cipher.encrypt(chunk)
        # self.debug.write(ssh_debug.DEBUG_2, 'send_packet: encrypted_chunk=%r', (encrypted_chunk,))

        self.transport.write(encrypted_chunk + mac)

    def receive_message(self, wait_till):
        """receive_message(self, wait_till) -> message_type, packet
        Read a message off the stream.

        <wait_till>: List of message types that you are looking for.
        """
        if not self._receive_thread:
            raise SSH_Protocol_Error('receive thread not running')
        self.tmc.add(coro.current(), wait_till)
        try:
            return coro._yield()
        except:
            self.tmc.remove(coro.current())
            raise

    def start_receive_thread(self):
        """start_receive_thread(self) -> None
        Spawns the receive thread.
        """
        self.closed = False
        self._receive_thread = coro.spawn(self.receive_loop)

    def stop_receive_thread(self):
        """stop_receive_thread(self) -> None
        Stops the receive thread.
        """
        # If the receive loop calls a handler that calls disconnect
        # then we don't want to raise an exception on ourself.
        if self._receive_thread and self._receive_thread is not coro.current():
            self._receive_thread.raise_exception(Stop_Receiving_Exception)
            self._receive_thread = None

    def receive_loop(self):
        """receive_loop(self) -> None
        This is the receive thread.  It runs forever processing messages off
        the socket.
        """
        exc_type = exc_data = exc_tb = None
        while True:
            try:
                packet, sequence_number = self._receive_packet()
            except Stop_Receiving_Exception:
                break
            except:
                exc_type, exc_data, exc_tb = sys.exc_info()
                break
            if self.ignore_first_packet:
                # This can only happen during the beginning of the
                # connection, so we don't need to worry about multiple
                # threads since there can be only 1.
                assert(len(self.tmc.processing_threads) <= 1)
                self.debug.write(ssh_debug.DEBUG_1, 'receive_thread: ignoring first packet')
                self.ignore_first_packet = False
                continue

            message_type = ord(packet[0])
            self.debug.write(ssh_debug.DEBUG_2, 'receive_thread: message_type=%i', (message_type,))
            try:
                self._handle_packet(message_type, packet, sequence_number)
            except Stop_Receiving_Exception:
                break
            except:
                exc_type, exc_data, exc_tb = sys.exc_info()
                break
            # XXX: We should check here for SSH_MSG_KEXINIT.
            #      If we see it, then we should lock down and prevent any
            #      other messages other than those for the key exchange.
            # if message_type == SSH_MSG_KEXINIT:

            # Wake up anyone waiting for their message.
            if message_type in self.tmc.processing_messages:
                thread = self.tmc.processing_messages[message_type]
                try:
                    self.debug.write(ssh_debug.DEBUG_2, 'receive_thread: waiting thread waking up')
                    coro.schedule(thread, (message_type, packet))
                except coro.ScheduleError:
                    # Coro already scheduled.
                    pass
                self.tmc.remove(thread)
        self.closed = True
        self.transport.close()
        self._receive_thread = None
        if exc_data is None:
            exc_data = SSH_Protocol_Error('Receive thread shut down.')

        # Wake up anyone still waiting for messages.
        for thread in self.tmc.processing_messages.values():
            try:
                # XXX: Too bad can't pass in traceback.
                thread.raise_exception(exc_data, force=False)
            except coro.ScheduleError:
                # Coro already scheduled.
                pass
        self.tmc.clear()

    def _handle_packet(self, message_type, packet, sequence_number):
        if message_type not in self.tmc.processing_messages:
            if message_type in self.message_callbacks:
                f = self.message_callbacks[message_type]
                self.debug.write(ssh_debug.DEBUG_2, 'receive_thread: calling registered function %s', (f.__name__,))
                f(packet)
            else:
                self.debug.write(ssh_debug.DEBUG_2, 'receive_thread: unimplemented message type (%i)', (message_type,))
                self.send_unimplemented(sequence_number)

    def prepare_keys(self):
        self.c2s.cipher.set_encryption_key_and_iv(self.key_exchange.get_encryption_key('C', self.c2s.cipher.key_size),
                                                  self.key_exchange.get_encryption_key('A', self.c2s.cipher.iv_size))
        self.s2c.cipher.set_encryption_key_and_iv(self.key_exchange.get_encryption_key('D', self.s2c.cipher.key_size),
                                                  self.key_exchange.get_encryption_key('B', self.s2c.cipher.iv_size))
        self.c2s.mac.set_key(self.key_exchange.get_encryption_key('E', self.c2s.mac.key_size))
        self.s2c.mac.set_key(self.key_exchange.get_encryption_key('F', self.s2c.mac.key_size))

    def send_newkeys(self):
        self.debug.write(ssh_debug.DEBUG_3, 'send_newkeys()')
        packet = ssh_packet.pack_payload(ssh_packet.PAYLOAD_MSG_NEWKEYS, (SSH_MSG_NEWKEYS,))
        self.send_packet(packet)
        # XXX: Unlock key exchange lockdown for self2remote.

    def send_unimplemented(self, sequence_number):
        self.debug.write(ssh_debug.DEBUG_3, 'send_unimplemented(sequence_number=%i)', (sequence_number,))
        self.send_packet(
            ssh_packet.pack_payload(ssh_packet.PAYLOAD_MSG_UNIMPLEMENTED,
                                    (SSH_MSG_UNIMPLEMENTED,
                                     sequence_number)
                                    )
        )

    def _receive_packet(self):
        """_receive_packet(self) -> payload, sequence_number
        Reads a packet off the l4 transport.
        """
        self.debug.write(ssh_debug.DEBUG_3, 'receive_packet()')
        first_chunk = self.transport.read(max(8, self.remote2self.cipher.block_size))
        self.debug.write(ssh_debug.DEBUG_3, 'receive_packet: first_chunk=%r', (first_chunk,))
        first_chunk = self.remote2self.cipher.decrypt(first_chunk)
        self.debug.write(ssh_debug.DEBUG_3, 'receive_packet: post decrypt: %r', (first_chunk,))
        self.debug.write(ssh_debug.DEBUG_3, 'receive_packet: cipher=%s', (self.remote2self.cipher.name,))

        packet_length = struct.unpack('>I', first_chunk[:4])[0]
        min_packet_length = max(16, self.remote2self.cipher.block_size)
        # +4 to include the length field.
        if packet_length + 4 < min_packet_length:
            self.debug.write(
                ssh_debug.WARNING, 'receive_packet: packet length too small (len=%i)', (packet_length + 4,))
            self.send_disconnect(SSH_DISCONNECT_PROTOCOL_ERROR, 'packet length too small: %i' % packet_length)
        if packet_length + 4 > 1048576:  # 1 megabyte
            self.debug.write(ssh_debug.WARNING, 'receive_packet: packet length too big (len=%i)', (packet_length + 4,))
            self.send_disconnect(SSH_DISCONNECT_PROTOCOL_ERROR, 'packet length too big: %i' % packet_length)

        self.debug.write(
            ssh_debug.DEBUG_3, 'receive_packet: reading rest of packet (packet_length=%i)', (packet_length,))
        rest_of_packet = self.transport.read(packet_length - len(first_chunk) + 4 + self.remote2self.mac.digest_size)
        if self.remote2self.mac.digest_size == 0:
            mac = ''
        else:
            mac = rest_of_packet[-self.remote2self.mac.digest_size:]
            rest_of_packet = rest_of_packet[:-self.remote2self.mac.digest_size]
        rest_of_packet = self.remote2self.cipher.decrypt(rest_of_packet)
        packet = first_chunk + rest_of_packet

        padding_len = ord(packet[4])
        self.debug.write(ssh_debug.DEBUG_3, 'receive_packet: padding_length=%i', (padding_len,))
        payload = packet[5:packet_length + 4 - padding_len]

        packet_sequence_number = self.remote2self.packet_sequence_number
        self.debug.write(ssh_debug.DEBUG_3, 'receive_packet: packet=%r', (packet,))
        self.debug.write(ssh_debug.DEBUG_3, 'receive_packet: packet_sequence_number=%i', (packet_sequence_number,))
        computed_mac = self.remote2self.mac.digest(packet_sequence_number, packet)
        self.remote2self.inc_packet_sequence_number()

        if computed_mac != mac:
            self.debug.write(
                ssh_debug.WARNING, 'receive_packet: mac did not match: computed=%r actual=%r', (computed_mac, mac))
            self.send_disconnect(SSH_DISCONNECT_MAC_ERROR, 'mac did not match')

        return payload, packet_sequence_number

    def msg_disconnect(self, packet):
        msg, reason_code, description, language = ssh_packet.unpack_payload (ssh_packet.PAYLOAD_MSG_DISCONNECT, packet)
        self.disconnect()
        raise SSH_Protocol_Error(reason_code, description)

    def msg_ignore(self, packet):
        # msg, data = ssh_packet.unpack_payload(ssh_packet.PAYLOAD_MSG_IGNORE, packet)
        pass

    def msg_debug(self, packet):
        msg, always_display, message, language = ssh_packet.unpack_payload(ssh_packet.PAYLOAD_MSG_DEBUG, packet)
        self.debug.write(ssh_debug.DEBUG_1, 'SSH_MSG_DEBUG: %s', message)

    def msg_unimplemented(self, packet):
        msg, seq_number = ssh_packet.unpack_payload(ssh_packet.PAYLOAD_MSG_UNIMPLEMENTED, packet)
        self.debug.write(ssh_debug.DEBUG_1, 'SSH_MSG_UNIMPLEMENTED: %i', seq_number)

    def msg_kexinit(self, packet):
        self.remote2self.kexinit_packet = packet
        msg, cookie, kex_algorithms, server_host_key_algorithms, encryption_algorithms_c2s, \
            encryption_algorithms_s2c, mac_algorithms_c2s, mac_algorithms_s2c, \
            compression_algorithms_c2s, compression_algorithms_s2c, \
            languages_c2s, languages_s2c, first_kex_packet_follows, pad = ssh_packet.unpack_payload(
                ssh_packet.PAYLOAD_MSG_KEXINIT, packet)

        self.remote2self.proactive_kex = first_kex_packet_follows

        self.c2s.set_supported(kex_algorithms,
                               server_host_key_algorithms,
                               encryption_algorithms_c2s,
                               mac_algorithms_c2s,
                               compression_algorithms_c2s,
                               languages_c2s,
                               1)  # Prefer client's list.
        self.s2c.set_supported(kex_algorithms,
                               server_host_key_algorithms,
                               encryption_algorithms_s2c,
                               mac_algorithms_s2c,
                               compression_algorithms_s2c,
                               languages_s2c,
                               0)  # Prefer client's list.

        # The algorithm that we use is the first item that is on the client's
        # list that is also on the server's list.
        self._matchup_kex_and_key()
        self._matchup('cipher')
        self._matchup('mac')
        self._matchup('compression')
        # XXX: lang not supported

        # See if we guessed the kex properly.
        if self.remote2self.proactive_kex and \
                self.remote2self.key_exchange.name != self.key_exchange.name:
            # Remote side sent an incorrect initial kex packet...ignore it.
            self.ignore_first_packet = True

        if self.self2remote.proactive_kex and \
                self.self2remote.key_exchange.name != self.key_exchange.name:
            # We sent an invalid initial kex packet.
            # Resend proper kex packet.
            self.debug.write(ssh_debug.DEBUG_1, 'msg_kexinit: Resending initial kex packet due to incorrect guess')
            if self.is_server:
                packet = self.key_exchange.get_initial_server_kex_packet()
            else:
                packet = self.key_exchange.get_initial_client_kex_packet()
            # packet should never be None because if proactive_kex is set,
            # then that means we sent the first packet.
            assert (packet is not None)
            self.send_packet(packet)

        # Sync up.
        self.remote2self.key_exchange = self.key_exchange
        self.self2remote.key_exchange = self.key_exchange
        self.remote2self.server_key = self.server_key
        self.self2remote.server_key = self.server_key

        # Make sure kex algorithm has the information it needs.
        self.key_exchange.set_info(self.c2s.version_string, self.s2c.version_string,
                                   self.c2s.kexinit_packet, self.s2c.kexinit_packet, self.s2c.supported_server_keys)

    def _matchup(self, what):
        if getattr(self.remote2self, what) is None:
            self.send_disconnect(
                SSH_DISCONNECT_KEY_EXCHANGE_FAILED, 'We do not support any of the remote side\'s %ss.' % what)
        if getattr(self.self2remote, what) is None:
            self.send_disconnect(
                SSH_DISCONNECT_KEY_EXCHANGE_FAILED, 'The remote side does not support any of our %ss.' % what)

    def _matchup_kex_and_key(self):
        """_matchup_kex_and_key(self) -> None
        This sets self.key_exchange and self.server_key to the appropriate
        value.  It checks that both us and the remote end support the same
        key exchange and we both support a key type that has the appropriate
        features required by the key exchange algorithm.
        """
        self.remote2self.set_preferred('key_exchange')
        self.remote2self.set_preferred('server_key')
        self.self2remote.set_preferred('key_exchange')
        self.self2remote.set_preferred('server_key')

        if self.remote2self.key_exchange is None or self.self2remote.key_exchange is None:
            self.send_disconnect(SSH_DISCONNECT_KEY_EXCHANGE_FAILED, 'Could not find matching key exchange algorithm.')
        if self.remote2self.server_key is None or self.self2remote.server_key is None:
            self.send_disconnect(SSH_DISCONNECT_KEY_EXCHANGE_FAILED, 'Could not find matching server key type.')

        if self.remote2self.key_exchange.name != self.self2remote.key_exchange.name:
            # iterate over client's kex algorithms,
            # one at a time.  Choose the first algorithm that satisfies
            # the following conditions:
            # +  the server also supports the algorithm,
            # +  if the algorithm requires an encryption-capable host key,
            #    there is an encryption-capable algorithm on the server's
            #    server_host_key_algorithms that is also supported by the
            #    client, and
            # +  if the algorithm requires a signature-capable host key,
            #    there is a signature-capable algorithm on the server's
            #    server_host_key_algorithms that is also supported by the
            #    client.
            # +  If no algorithm satisfying all these conditions can be
            #    found, the connection fails, and both sides MUST
            #    disconnect.
            for client_kex_algorithm in self.c2s.supported_key_exchanges:
                server_kex_algorithm = pick_from_list(client_kex_algorithm.name, self.s2c.supported_key_exchanges)
                if server_kex_algorithm is not None:
                    # We both support this kex algorithm.
                    # See if we both have key types that match the requirements of this kex algorithm.
                    for server_host_key_type in self.s2c.supported_server_keys:
                        if (server_kex_algorithm.wants_encryption_host_key and not server_host_key_type.supports_encryption) or \
                           (server_kex_algorithm.wants_signature_host_key and not server_host_key_type.supports_signature):  # noqa
                            # This host key is not appropriate.
                            continue
                        else:
                            # This key meets our requirements.
                            break
                    else:
                        # None of the host key types worked, try next kex algorithm.
                        continue

                    # If we got here, then this is the kex to use.
                    self.set_key_exchange(client_kex_algorithm.name, server_host_key_type.name)
                    break
            else:
                # None of the kex algorithms worked.
                self.send_disconnect(
                    SSH_DISCONNECT_KEY_EXCHANGE_FAILED, 'Could not find matching key exchange algorithm.')
        else:
            # We have agreement on the kex algorithm to use.
            # See if we have agreement on the server host key type.
            self.debug.write (ssh_debug.DEBUG_3, 'msg_kexinit: agreement on %r' % (self.self2remote.key_exchange.name,))
            if self.remote2self.server_key.name != self.self2remote.server_key.name:
                # See if we share a server host key type that also works with our chosen kex algorithm.
                for client_server_key_type in self.c2s.supported_server_keys:
                    server_server_key_type = pick_from_list(client_server_key_type.name, self.s2c.supported_server_keys)
                    if server_server_key_type is not None:
                        # We both support this server key algorithm.
                        # See if it matches our kex algorithm requirements.
                        if (self.remote2self.key_exchange.wants_encryption_host_key and not server_server_key_type.supports_encryption) or \
                           (self.remote2self.key_exchange.wants_signature_host_key and not server_server_key_type.supports_signature):  # noqa
                            # This server key type is not appropriate.
                            continue
                        else:
                            # This meets our requirements.
                            break
                else:
                    # None of the server key types worked.
                    self.send_disconnect(
                        SSH_DISCONNECT_KEY_EXCHANGE_FAILED,
                        'Could not find matching server key type for %s key exchange.' %
                        self.remote2self.key_exchange.name)
            self.debug.write (ssh_debug.DEBUG_3, 'msg_kexinit: set_key_exchange: %r' %
                              (self.remote2self.server_key.name,))
            self.set_key_exchange(self.remote2self.key_exchange.name, self.remote2self.server_key.name)

    def set_key_exchange(self, key_exchange=None, server_host_key_type=None):
        """set_key_exchange(self, key_exchange=None, server_host_key_type=None) -> None
        Sets the key exchange algorithm to use.

        <key_exchange> - A string.  The key exchange algorithm to use.
                         Must be one of those in supported_key_exchanges.
                         Set to None to default to the preferred algorithm.
        <server_host_key_type> - A string.  The server host key type to use.
                         Must be one of thos in supported_server_keys.
                         Set to None to default to the preferred algorithm.
                         The key_exchange algorithm MUST support this type
                         of key.
        """
        kex = pick_from_list(key_exchange, self.self2remote.supported_key_exchanges)
        if kex is None:
            raise ValueError('Unknown key exchange algorithm: %s' % key_exchange)
        key = pick_from_list(server_host_key_type, self.self2remote.supported_server_keys)
        if key is None:
            raise ValueError('Unknown server key type: %s' % server_host_key_type)
        self.key_exchange = kex
        self.server_key = key
        if self.is_server:
            self.key_exchange.register_server_callbacks()
        else:
            self.key_exchange.register_client_callbacks()

    def _process_kexinit(self):
        """_process_kexinit(self) -> None
        This processes the key exchange.
        """
        message_type, packet = self.receive_message((SSH_MSG_KEXINIT,))
        self.msg_kexinit(packet)

    def send_kexinit(self):
        """send_kexinit(self) -> None
        Start the key exchange.
        """
        # Tell the remote side what features we support.
        self.debug.write(ssh_debug.DEBUG_3, 'send_kexinit()')
        packet = self._send_kexinit()
        self.send_packet(packet)

    def _send_kexinit(self):
        """_send_kexinit(self) -> None
        Sets self2remote.kexinit_packet.
        Separate function to help with unittests.
        """
        cookie = random.get_random_data(16)
        server_keys = [x.name for x in self.self2remote.supported_server_keys]
        server_keys.reverse()
        packet = ssh_packet.pack_payload(ssh_packet.PAYLOAD_MSG_KEXINIT,
                                         (SSH_MSG_KEXINIT,
                                          cookie,
                                          [x.name for x in self.self2remote.supported_key_exchanges],
                                             # [x.name for x in self.self2remote.supported_server_keys],
                                             server_keys,
                                             [x.name for x in self.c2s.supported_ciphers],
                                             [x.name for x in self.s2c.supported_ciphers],
                                             [x.name for x in self.c2s.supported_macs],
                                             [x.name for x in self.s2c.supported_macs],
                                             [x.name for x in self.c2s.supported_compressions],
                                             [x.name for x in self.s2c.supported_compressions],
                                             [x.name for x in self.c2s.supported_languages],
                                             [x.name for x in self.s2c.supported_languages],
                                             self.self2remote.proactive_kex,  # first_kex_packet_follows
                                             0  # reserved
                                          )
                                         )
        self.self2remote.kexinit_packet = packet
        return packet

    def msg_newkeys(self, packet):
        self.send_newkeys()
        self.debug.write(ssh_debug.DEBUG_3, 'msg_newkeys(packet=...)')
        # Switch to using new algorithms.
        self.remote2self.set_preferred()
        self.self2remote.set_preferred()
        # Set the keys to use for encryption and MAC.
        self.prepare_keys()
        self.debug.write(ssh_debug.DEBUG_3, 'msg_newkeys: keys have been prepared')

class One_Way_SSH_Transport:

    # These are references to the in-use entry from one of the
    # supported_xxx lists.
    key_exchange = None
    server_key = None
    compression = None
    cipher = None
    mac = None
    language = None

    protocol_version = '2.0'
    software_version = 'Shrapnel_1.0'
    comments = ''
    version_string = ''
    kexinit_packet = ''

    # Whether or not we sent our first kex packet with the assumption that
    # the remote side supports our preferred algorithms.
    proactive_kex = 0

    packet_sequence_number = 0

    def __init__(self, transport):
        # Instantiate all components.
        # An assumption is made that the first (preferred) key exchange algorithm
        # supports the first (preferred) server key type.
        self.supported_key_exchanges = [Diffie_Hellman_Group1_SHA1(transport)]
        self.supported_server_keys = [SSH_DSS(), SSH_RSA()]
        self.supported_compressions = [Compression_None()]
        self.supported_ciphers = [Triple_DES_CBC(),
                                  Blowfish_CBC(),
                                  Cipher_None(),
                                  ]
        self.supported_macs = [HMAC_SHA1(),
                               MAC_None(),
                               ]
        self.supported_languages = []

        self.set_none()

    def inc_packet_sequence_number(self):
        """inc_packet_sequence_number(self) -> None
        Raises the packet sequence number by one.
        """
        self.packet_sequence_number += 1
        if self.packet_sequence_number == 4294967296:
            self.packet_sequence_number = 0

    def set_none(self):
        """set_none(self) -> None
        Sets the in-use settings to that which is suitable for the beginning
        of a connection.
        """
        self.key_exchange = None
        self.server_key = None
        self.compression = Compression_None()
        self.cipher = Cipher_None()
        self.mac = MAC_None()
        self.language = None

    def set_preferred(self, what=None):
        """set_preferred(self, what = None) -> None
        Sets the "preferred" pointers to the first element of the appropriate
        lists.

        <what> - Can be a string to indicate which element to set.
                 Set to None to set all elements.
        """
        def get(list):
            try:
                return list[0]
            except IndexError:
                return None

        if what is None:
            self.key_exchange = get(self.supported_key_exchanges)
            self.server_key = get(self.supported_server_keys)
            self.compression = get(self.supported_compressions)
            self.cipher = get(self.supported_ciphers)
            self.mac = get(self.supported_macs)
            self.language = get(self.supported_languages)
        else:
            supported = getattr(self, 'supported_%ss' % what)
            setattr(self, what, get(supported))

    def set_supported(self, kex, key, encrypt, mac, compress, lang, prefer_self):
        """set_supported(self, kex, key, encrypt, mac, compress, lang, prefer_self) -> None
        Sets the supported feature lists.
        Each argument is a list of strings.
        <prefer_self> - boolean.  If true, prefers the order of self.supported_xxx.
                                  If false, prefers the order of the given lists.
        """
        def _filter(feature_list, algorithm_list, prefer_self):
            algorithm_list[:] = filter(lambda x, y=feature_list: x.name in y, algorithm_list)
            if not prefer_self:
                # Change the order to match that of <feature_list>
                new_list = []
                for feature in feature_list:
                    for self_alg in algorithm_list:
                        if self_alg.name == feature:
                            new_list.append(self_alg)

                if __debug__:
                    assert(len(algorithm_list) == len(new_list))
                algorithm_list[:] = new_list

        _filter(kex, self.supported_key_exchanges, prefer_self)
        _filter(key, self.supported_server_keys, prefer_self)
        _filter(encrypt, self.supported_ciphers, prefer_self)
        _filter(mac, self.supported_macs, prefer_self)
        _filter(compress, self.supported_compressions, prefer_self)
        _filter(lang, self.supported_languages, prefer_self)

class Thread_Message_Callbacks:

    """Thread_Message_Callbacks()

    This is a simple wrapper around the transport's process messages mechanism.
    """

    def __init__(self):
        # processing_messages: Dictionary of {message: thread}
        # Indicates which thread to wake up for each message.
        self.processing_messages = {}
        # processing_threads: Dictionary of {thread_id:wait_till}
        # Reverse of processing_messages.
        self.processing_threads = {}

    def clear(self):
        """clear(self) -> None
        Clear all threads/messages.
        """
        self.processing_messages = {}
        self.processing_threads = {}

    def remove(self, coro_object):
        """remove(self, coro_object) -> None
        Remove a thread that is being tracked.
        """
        thread_id = coro_object.thread_id()
        if thread_id in self.processing_threads:
            messages = self.processing_threads[thread_id]
            for m in messages:
                assert(self.processing_messages[m] == coro_object)
                del self.processing_messages[m]
            del self.processing_threads[thread_id]

    def add(self, coro_object, messages_waiting_for):
        """add(self, coro_object, messages_waiting_for) -> None
        Add a thread to the list of processing.

        <coro_object>: The thread object.
        <messages_waiting_for>: List of messages the thread is waiting for.
        """
        self.processing_threads[coro_object.thread_id()] = messages_waiting_for
        for m in messages_waiting_for:
            if m in self.processing_messages:
                raise AssertionError('Can\'t register message %i with multiple threads.' % m)
            self.processing_messages[m] = coro_object

class Stop_Receiving_Exception(Exception):
    pass
