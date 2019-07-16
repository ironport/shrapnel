# -*- Mode: Python; insert-tabs-mode: nil -*-

from coro.ssh.transport.client import SSH_Client_Transport
from coro.ssh.l4_transport.coro_socket_transport import coro_socket_transport
from coro.ssh.auth.userauth import Userauth
from coro.ssh.connection.interactive_session import Interactive_Session_Client
from coro.ssh.connection.connect import Connection_Service

import sys
import coro
# avoid full-blown dns resolver
coro.set_resolver (coro.dummy_resolver())

class client:

    # this is to avoid a PTR lookup, its value is not important
    hostname = b'host'

    def __init__ (self, ip, username, port=22):
        self.ip = ip
        self.port = port
        self.username = username

    def open (self):
        client = SSH_Client_Transport()
        transport = coro_socket_transport (self.ip, port=self.port, hostname=self.hostname)
        client.connect (transport)
        auth_method = Userauth (client, self.username)
        service = Connection_Service (client)
        client.authenticate (auth_method, service.name)
        channel = Interactive_Session_Client (service)
        channel.open()
        return channel

    def read_all (self, channel):
        while 1:
            try:
                yield channel.read (1000)
            except EOFError:
                break

    def command (self, cmd, output=sys.stdout):
        channel = self.open()
        channel.exec_command (cmd)
        for block in self.read_all (channel):
            output.write (block.decode ('us-ascii'))
        channel.close()

def go (ip, username, cmd):
    c = client (ip.encode(), username)
    c.command (cmd)
    coro.set_exit()

# try: python remote_exec.py 10.1.1.3 bubba "ls -l"
if __name__ == '__main__':
    import sys
    #from coro.ssh.util.debug import Debug
    #Debug.level = 5
    if len(sys.argv) < 3:
        sys.stderr.write ('Usage: %s <ip> <username> <cmd>\n' % (sys.argv[0],))
        sys.stderr.write ('Example: python %s 10.1.1.3 bubba "ls -l"\n' % (sys.argv[0],))
    else:
        coro.spawn (go, *sys.argv[1:])
        coro.event_loop()
