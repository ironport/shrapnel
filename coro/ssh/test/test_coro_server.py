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
    server = coro.ssh.transport.server.SSH_Server_Transport(debug=debug)
    server.connect (transport)
    service = coro.ssh.connection.connect.Connection_Service(server)
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
