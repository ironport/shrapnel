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
# ssh.transport.client
#
# This implements the client functionality of the SSH transport layer.
#

from coro.ssh.util import debug
from coro.ssh.util import packet as ssh_packet
from coro.ssh.transport import transport
from coro.ssh.keys import key_storage
from coro.ssh.transport.constants import *

class SSH_Client_Transport(transport.SSH_Transport):

    def __init__(self, client_transport=None, server_transport=None, debug=None):
        transport.SSH_Transport.__init__(self, client_transport, server_transport, debug)
        self.self2remote = self.c2s
        self.remote2self = self.s2c

    def connect(self, transport):
        """connect(self, transport) -> None
        Connect to the remote host.
        """
        try:
            self._connect(transport)
        except:
            # Any exception is fatal.
            self.disconnect()
            raise

    def _connect(self, transport):
        self.transport = transport
        transport.connect()

        # Send identification string.
        if self.c2s.comments:
            comments = ' ' + self.c2s.comments
        else:
            comments = ''
        self.c2s.version_string = 'SSH-' + self.c2s.protocol_version + '-' + self.c2s.software_version + comments
        transport.write(self.c2s.version_string + '\r\n')
        # Receive server's identification string.
        while 1:
            # We might receive lines before we get the version.  Just ignore
            # them.
            # Note that the SSH spec says that clients MUST be able to receive
            # a version string that does not end in CRLF.  It appears that not
            # even OpenSSH does this.  Plus, the spec does not indicate how to
            # determine the length of the identification string.  We're not
            # going to bother supporting that here.  It's for backwards
            # compatibility.
            line = transport.read_line()
            if line.startswith('SSH-'):
                # Got the identification string.
                self.s2c.version_string = line
                # See if there are any optional comments.
                i = line.find(' ')
                if i != -1:
                    self.s2c.comments = line[i + 1:]
                    line = line[:i]
                # Break up the identification string into its parts.
                parts = line.split('-')
                if len(parts) != 3:
                    self.send_disconnect(
                        transport.SSH_DISCONNECT_PROTOCOL_ERROR, 'server identification invalid: %r' % line)
                self.s2c.protocol_version = parts[1]
                self.s2c.software_version = parts[2]
                if self.s2c.protocol_version not in ('1.99', '2.0'):
                    self.send_disconnect(transport.SSH_DISCONNECT_PROTOCOL_VERSION_NOT_SUPPORTED,
                                         'protocol version not supported: %r' % self.s2c.protocol_version)
                break

        self.send_kexinit()

        if self.self2remote.proactive_kex:
            # Go ahead and send our kex packet with our preferred algorithm.
            # This will assume the server side supports the algorithm.
            self.c2s.set_preferred('key_exchange')
            self.c2s.set_preferred('server_key')
            self.set_key_exchange()
            packet = self.c2s.key_exchange.get_initial_client_kex_packet()
            self.send_packet(packet)

        # Start the receive thread.
        # This depends on coro behavior that the thread won't start until we go to sleep
        # (which will happen in _process_kexinit).
        self.start_receive_thread()
        # Receive server kexinit
        self._process_kexinit()
        self.debug.write(debug.DEBUG_3, 'key exchange: got kexinit')
        if not self.self2remote.proactive_kex:
            packet = self.key_exchange.get_initial_client_kex_packet()
            if packet:
                # It is possible for a key exchange algorithm to not have
                # an initial packet to send on the client side.
                self.send_packet(packet)
        # Let the key exchange finish.
        # XXX: Need to lock down to prevent any non-key exchange packets from being transferred.
        # Key exchange finished and SSH_MSG_NEWKEYS sent, wait for the remote side to send NEWKEYS.
        message_type, packet = self.receive_message((SSH_MSG_NEWKEYS,))
        self.msg_newkeys(packet)
        # XXX: Unlock key exchange lockdown for c2s.

    def authenticate(self, authentication_method, service_name):
        """authenticate(self, authentication_method, service) -> None
        Authenticate with the remote side.

        <authentication_method>:
        <service_name>: The name of the service that you want to use after
                        authenticating.  Typically 'ssh-connection'.
        """
        # Ask the remote side if it is OK to use this authentication service.
        self.debug.write(debug.DEBUG_3, 'authenticate: sending service request (%s)', (authentication_method.name,))
        service_request_packet = ssh_packet.pack_payload(ssh_packet.PAYLOAD_MSG_SERVICE_REQUEST,
                                                         (transport.SSH_MSG_SERVICE_REQUEST,
                                                          authentication_method.name))
        self.send_packet(service_request_packet)
        # Server will disconnect if it doesn't like our service request.
        self.debug.write(debug.DEBUG_3, 'authenticate: waiting for SERVICE_ACCEPT')
        message_type, packet = self.receive_message((transport.SSH_MSG_SERVICE_ACCEPT,))
        msg, accepted_service_name = ssh_packet.unpack_payload(ssh_packet.PAYLOAD_MSG_SERVICE_ACCEPT, packet)
        self.debug.write(debug.DEBUG_3, 'authenticate: got SERVICE_ACCEPT')
        if accepted_service_name != authentication_method.name:
            self.send_disconnect(transport.SSH_DISCONNECT_PROTOCOL_ERROR,
                                 'accepted service does not match requested service "%s"!="%s"' %
                                 (authentication_method.name, accepted_service_name))
        # This authetnication service is OK, try to authenticate.
        authentication_method.authenticate(service_name)

    def request_service(self, service_instance):
        """request_service(self, service_instance) -> None
        Requests to run this service over the transport.
        If the service is not available, then a disconnect will be sent.
        <service_instance> is a SSH_Service class instance.
        """
        # SSH_MSG_SERVICE_REQUEST
        pass

    def msg_service_request_response(self, packet):
        pass

    def verify_public_host_key(self, public_host_key, username=None):
        """verify_public_host_key(self, public_host_key, username=None) -> None
        Verifies that the given public host key is the correct public key for
        the current remote host.
        <public_host_key>: A SSH_Public_Private_Key instance.

        Raises Invalid_Server_Public_Host_Key exception if it does not match.
        """
        host_id = self.transport.get_host_id()
        port = self.transport.get_port()
        for storage in self.supported_key_storages:
            if storage.verify(host_id, self.c2s.supported_server_keys, public_host_key, username, port):
                return
        raise key_storage.Invalid_Server_Public_Host_Key(host_id, public_host_key)
