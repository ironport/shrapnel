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

ks = OpenSSH_Key_Storage()
dss_obj = ks.parse_private_key (server_key_pri)

def usage():
    print 'test_coro_server [-p port]'

def input_thread(channel):
    stdin = coro.fd_sock(0)
    while 1:
        data = stdin.recv(100)
        channel.send(data)

def transport_thread(channel):
    stdout = coro.fd_sock (1)
    while not channel.eof and not channel.closed:
        try:
            data = channel.read(1024)
            if data:
                stdout.send (data)
                #os.write(1, data)
        except EOFError:
            break
    coro.set_exit()

def serve (port):
    s = coro.tcp_sock()
    s.bind (('', port))
    s.listen (5)
    while 1:
        conn, addr = s.accept()
        coro.spawn (go, conn, addr)

def go (conn, addr):
    debug = coro.ssh.util.debug.Debug()
    debug.level = coro.ssh.util.debug.DEBUG_3
    transport = coro.ssh.l4_transport.coro_socket_transport.coro_socket_transport(sock=conn)
    server = coro.ssh.transport.server.SSH_Server_Transport(dss_obj, debug=debug)
    server.connect (transport)
    W ('after server.connect()\n')    
    service = coro.ssh.connection.connect.Connection_Service(server)
    W ('service=%r\n' % (service,))
    W ('sleeping...\n')
    coro.sleep_relative (1000)

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
