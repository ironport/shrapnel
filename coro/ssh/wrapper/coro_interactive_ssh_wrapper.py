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
# ssh.wrapper.coro_interactive_ssh_wrapper
#
# This is a easy-to-use wrapper that uses coro_ssh.
#
# It has only a few features, but many may be added in the future.

import dnsqr
import inet_utils
import coro.ssh.transport.client
import coro.ssh.connection.connect
import coro.ssh.l4_transport.coro_socket_transport
import coro.ssh.auth.userauth
import coro.ssh.connection.interactive_session
import coro.ssh.util.debug

DISABLE_PASSWORD = '__DISABLE_PASSWORD__'

class Coro_Interactive_SSH_Wrapper:

    client = None
    transport = None
    service = None
    channel = None

    def __init__(self):
        pass

    def connect(self, username, remote_address, remote_port=22, password=None,
                command=None, debug_level=coro.ssh.util.debug.WARNING):
        """connect(self, username, remote_address, remote_port=22, password=None,
                   command=None, debug_level=coro.ssh.util.debug.WARNING) -> None
        The opens a connection to the remote side and authenticates.

        <username> - The remote username to log into.
        <remote_address> - The remote address to connect to.
        <remote_port> - The remote port to connect to.
        <password> - The password to use when connecting to the remote side.
                     If None, and there are no authorized_keys configured,
                     then it will ask for the password on stdout/stdin.
                     If DISABLE_PASSWORD, will disable password auth.
        <command> - The command to run on the remote side.
                    If no command is given, then it will open a pty and shell.
        <debug_level> - Level a debuging to print to stderr.
        """

        self.client = coro.ssh.transport.client.SSH_Client_Transport()
        if inet_utils.is_ip(remote_address):
            remote_ip = remote_address
            hostname = None
        else:
            dns_query_result = dnsqr.query(remote_address, 'A')
            remote_ip = dns_query_result[0][-1]
            hostname = remote_address
        coro_socket_transport = coro.ssh.l4_transport.coro_socket_transport
        self.transport = coro_socket_transport.coro_socket_transport(
            remote_ip, remote_port, hostname=hostname)
        self.client.connect(self.transport)
        self.client.debug.level = debug_level
        self.service = coro.ssh.connection.connect.Connection_Service(self.client)
        self._authenticate(username, password)
        self.channel = coro.ssh.connection.interactive_session.Interactive_Session_Client(self.service)
        self.channel.open()
        if command is not None:
            self.channel.exec_command(command)
        else:
            self.channel.open_pty()
            self.channel.open_shell()

    def _authenticate(self, username, password=None):
        auth_method = coro.ssh.auth.userauth.Userauth(self.client)
        auth_method.username = username
        if password is not None:
            for x in xrange(len(auth_method.methods)):
                if auth_method.methods[x].name == 'password':
                    break
            else:
                # This should never happen.
                raise ValueError('Expected password auth method in Userauth class')
            if password is DISABLE_PASSWORD:
                del auth_method.methods[x]
            else:
                password_method = Fixed_Password_Auth(self.client)
                password_method.password = password
                auth_method.methods[x] = password_method
        self.client.authenticate(auth_method, self.service.name)

    def disconnect(self):
        if self.channel is not None:
            self.channel.close()
        if self.client is not None:
            self.client.disconnect()

    close = disconnect

    def read(self, bytes):
        return self.channel.read(bytes)

    recv = read

    def read_exact(self, bytes):
        return self.channel.read_exact(bytes)

    def write(self, data):
        self.channel.send(data)

    send = write

class Fixed_Password_Auth(coro.ssh.auth.userauth.Password):

    password = None

    def get_password(self, username, prompt=None):
        return self.password
