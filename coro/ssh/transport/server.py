# -*- Mode: Python -*-

#
# ssh.transport.server
#
# This implements the server functionality of the SSH transport layer.
#

from coro.ssh.util import debug
from coro.ssh.util import packet as ssh_packet
from coro.ssh.transport import transport as ssh_transport
from coro.ssh.keys import key_storage
from coro.ssh.transport.constants import *

from coro.ssh.auth import userauth

from coro import write_stderr as W

class SSH_Server_Transport (ssh_transport.SSH_Transport):

    def __init__(self, server_key, client_transport=None, server_transport=None, debug=None):
        ssh_transport.SSH_Transport.__init__(self, client_transport, server_transport, debug)
        self.self2remote = self.s2c
        self.remote2self = self.c2s
        self.is_server = True
        # XXX should accept a list of keys...
        self.s2c.supported_server_keys = [server_key]

    def connect (self, transport, authenticator):
        """connect(self, transport) -> None
        Connect to the remote host.
        """
        try:
            self._connect(transport, authenticator)
        except:
            # Any exception is fatal.
            self.disconnect()
            raise

    def _connect(self, transport, authenticator):
        # transport is already connected
        # Send identification string.
        self.transport = transport
        if self.s2c.comments:
            comments = ' ' + self.s2c.comments
        else:
            comments = ''
        self.s2c.version_string = 'SSH-' + self.s2c.protocol_version + '-' + self.s2c.software_version + comments
        transport.write(self.s2c.version_string + '\r\n')
        # Receive client's identification string.
        while 1:
            line = transport.read_line()
            if line.startswith('SSH-'):
                # Got the identification string.
                self.c2s.version_string = line
                # See if there are any optional comments.
                i = line.find(' ')
                if i != -1:
                    self.c2s.comments = line[i + 1:]
                    line = line[:i]
                # Break up the identification string into its parts.
                parts = line.split('-')
                if len(parts) != 3:
                    self.send_disconnect (
                        ssh_transport.SSH_DISCONNECT_PROTOCOL_ERROR,
                        'server identification invalid: %r' % line
                    )
                self.c2s.protocol_version = parts[1]
                self.c2s.software_version = parts[2]
                if self.c2s.protocol_version not in ('1.99', '2.0'):
                    self.send_disconnect (
                        ssh_transport.SSH_DISCONNECT_PROTOCOL_VERSION_NOT_SUPPORTED,
                        'protocol version not supported: %r' % self.c2s.protocol_version
                    )
                break

        self.send_kexinit()
        self.s2c.set_preferred('key_exchange')
        self.s2c.set_preferred('server_key')

        if self.self2remote.proactive_kex:
            # Go ahead and send our kex packet with our preferred algorithm.
            # This will assume the client side supports the algorithm.
            self.s2c.set_preferred('key_exchange')
            self.s2c.set_preferred('server_key')
            self.set_key_exchange()
            self.debug.write(debug.DEBUG_3, 'key exchange: sending proactive server kex packet')
            packet = self.c2s.key_exchange.get_initial_server_kex_packet()
            self.send_packet(packet)

        self.start_receive_thread()
        # Receive server kexinit
        self._process_kexinit()
        self.debug.write(debug.DEBUG_3, 'key exchange: got kexinit')
        self.debug.write(debug.DEBUG_3, 'key exchange: self.server_key=%r' % (self.server_key,))
        if not self.self2remote.proactive_kex:
            self.debug.write(debug.DEBUG_3, 'key exchange: sending initial server kex packet')
            packet = self.key_exchange.get_initial_server_kex_packet()
            if packet:
                # It is possible for a key exchange algorithm to not have
                # an initial packet to send on the client side.
                self.send_packet(packet)

        message_type, packet = self.receive_message ((SSH_MSG_SERVICE_REQUEST,))
        msg, service_name = ssh_packet.unpack_payload (ssh_packet.PAYLOAD_MSG_SERVICE_REQUEST, packet)
        self.debug.write (debug.DEBUG_1, 'service_request: %r' % (service_name,))
        # XXX consider other possibilities
        if service_name != 'ssh-userauth':
            self.send_disconnect (SSH_DISCONNECT_SERVICE_NOT_AVAILABLE, "not today, zurg")
        else:
            self.send_packet (
                ssh_packet.pack_payload (
                    ssh_packet.PAYLOAD_MSG_SERVICE_ACCEPT, (
                        ssh_transport.SSH_MSG_SERVICE_ACCEPT,
                        'ssh-userauth',
                    )
                )
            )
            authenticator.authenticate (service_name)
