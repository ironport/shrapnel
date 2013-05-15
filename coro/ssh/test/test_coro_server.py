# -*- Mode: Python -*-

import coro.ssh.transport.server
import coro.ssh.connection.connect
import coro.ssh.l4_transport.coro_socket_transport
import coro.ssh.auth.userauth
import coro.ssh.connection.interactive_session
import getopt
import sys
import termios
import fcntl
import os
import coro.ssh.util.debug
import socket
import coro

from coro.ssh.keys.openssh_key_storage import OpenSSH_Key_Storage

W = coro.write_stderr

server_key_pri = """-----BEGIN DSA PRIVATE KEY-----
MIIBuwIBAAKBgQDTfwvvQo0WnUmZpnUFmqF/TXSXFaJ1NKbBLQXPh8dhHgTN1uFO
ZibFXMKpDHLCGCdGRm5eHansB9hu2+nNoaFf3oLDHc8ctuE7xRHT8x174D2AxcnX
r0Fw3BnZHj58lLlhayDJ4S6W77yefGEOuo/wKUEPjAUBCrvxKq3bKAeVUQIVAPpR
bJO1QQZPlj4w+MXmRTgW7wGfAoGAVUkBIX+RLrh9guyiAadi9xGk8S7n5w2PbcsP
KTG8x/ttCDEuaBp6El6qt86cA+M2GPvXjuMGR5BQT8IOaWS7Aw2+J1IamLCsrPfq
oiQvz3cqxOAutuIuorzbIAgVo0hiAyovZE4u2zzKeci7OtfD8pRThSby4Dgbkeix
FQFhW08CgYBSxcduHDSqJTCjFK4hwTlNck4h2hC1E4xuMfxYsUZkLrBAsD3nzU2W
jNoZppTz3W8XC7YnTxonncXNWxCWsDWpvs0b2zGj7uUvGRtlyxtQpybyN3LZ0flo
DssTygy7t0KlS7T2a1IhqiVDbrSUoGXz+Wp/z66lCpSLTlPsGpLeLwIVAMQldwwH
OekNfzzIBr6QkMvmIOuL
-----END DSA PRIVATE KEY-----
"""

user_key_pub = """ssh-dss AAAAB3NzaC1kc3MAAACBAPawYoOY758V46mBep5i3pRQSuXnmYLiwBWH06NMXfMKkncZE4eWIVVoDqZmeMfCSHP8uY2gS+QDfdMCGtqu9sX8noPx5SG6gzUnadhFKU2+o7tbJ9WkQX7TPHB2GLBk5SNn6MFfLlLwlLv+OFnO0jcBD81fkCZp19BoZt1CCMGLAAAAFQCCSKBZHEoXw7Y1jiT0GFuqGgPMaQAAAIB2EjHBcrMa6jvmNI1DLYEHrYlQ30cDvnYYIyunMsp6SybE1sLN2W3UqGLjqB2i3FgWh7o1yUVWdImBvFz4kdYVhlEcYUeTgu8IWH2YNFcr7/Q4IpF9h20pu/ASuR9aK/D8sA4s7JqVfkS/mIaOZ8W2aZiOSaqvJXQPee9tiKgLDAAAAIEA6jTTFwh0wBlLdzALSaxf+A4IPGwE3mlmVmzt+A+a+EqL2ZRmAZ2puQH3NKckqrAlHDY7gGuF5XlHUTiTbVanuv6vCRlPwHWCPNNZhYFqGLpMEqRNPV2cMlU0gaPn69DMZwbDNCJghZI6C2uejoh3agHvHq8jgm9q4e3X3nEjStc= rushing@beast.local\n"""

ks = OpenSSH_Key_Storage()
server_key_ob = ks.parse_private_key (server_key_pri)
user_key_ob = ks.parse_public_key (user_key_pub)

def usage():
    print 'test_coro_server [-p port]'

def serve (port):
    s = coro.tcp_sock()
    s.bind (('', port))
    s.listen (5)
    while 1:
        conn, addr = s.accept()
        coro.spawn (go, conn, addr)

class echo_server (coro.ssh.connection.interactive_session.Interactive_Session_Server):
    def __init__ (self, connection_service):
        coro.ssh.connection.interactive_session.Interactive_Session_Server.__init__ (self, connection_service)
        coro.spawn (self.go)
    def go (self):
        self.send ('Welcome to the echo server.\n')
        while 1:
            try:
                block = self.read (1000)
                self.send (block)
            except EOFError:
                break
        self.close()

def go (conn, addr):
    debug = coro.ssh.util.debug.Debug()
    debug.level = coro.ssh.util.debug.DEBUG_3
    transport = coro.ssh.l4_transport.coro_socket_transport.coro_socket_transport(sock=conn)
    server = coro.ssh.transport.server.SSH_Server_Transport (server_key_ob, debug=debug)
    pubkey_auth = coro.ssh.auth.userauth.Public_Key_Authenticator ({'rushing': { 'ssh-connection' : [user_key_ob]}})
    pwd_auth = coro.ssh.auth.userauth.Password_Authenticator ({'foo' : { 'ssh-connection' : 'bar' } })
    authenticator = coro.ssh.auth.userauth.Authenticator (server, [pubkey_auth, pwd_auth])
    server.connect (transport, authenticator)
    service = coro.ssh.connection.connect.Connection_Service (server, echo_server)

def main():

    login_username = None
    ip = None
    port = 22

    try:
        optlist, args = getopt.getopt(sys.argv[1:], 'p:')
    except getopt.GetoptError, why:
        print str(why)
        usage()
        sys.exit(1)

    for option, value in optlist:
        if option=='-p':
            port = int (value)

    coro.spawn (serve, port)
    coro.event_loop()

if __name__=='__main__':
    main()
