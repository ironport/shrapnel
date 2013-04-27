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
# NOTE: THIS DOES NOT WORK.
# There is a problem with reading from stdin via kqueue.
# I'm not sure (yet) what exactly is wrong.

import ssh.transport.client
import ssh.connection.connect
import ssh.l4_transport.coro_socket_transport
import ssh.auth.userauth
import ssh.connection.interactive_session
import getopt
import sys
import termios
import fcntl
import os
import ssh.util.debug
import inet_utils
import socket
import coro

def usage():
    print 'test_coro_client [-l login_name] hostname | user@hostname'

oldterm = None
oldflags = None

def set_stdin_unbuffered():
    global oldterm, oldflags

    oldterm = termios.tcgetattr(0)
    newattr = termios.tcgetattr(0)
    newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
    termios.tcsetattr(0, termios.TCSANOW, newattr)

    oldflags = fcntl.fcntl(0, fcntl.F_GETFL)
    fcntl.fcntl(0, fcntl.F_SETFL, oldflags | os.O_NONBLOCK)

def input_thread(channel):

    stdin = coro.fd_sock(0)

    while 1:
        data = stdin.recv(100)
        channel.send(data)

def transport_thread(channel):

    while not channel.eof and not channel.closed:
        data = channel.read(1024)
        if data:
            os.write(1, data)

def doit(ip):
    debug = ssh.util.debug.Debug()
    #debug.level = ssh.util.debug.DEBUG_3
    client = ssh.transport.client.SSH_Client_Transport(debug=debug)
    transport = ssh.l4_transport.coro_socket_transport.coro_socket_transport(ip)
    client.connect(transport)
    auth_method = ssh.auth.userauth.Userauth(client)
    service = ssh.connection.connect.Connection_Service(client)
    client.authenticate(auth_method, service.name)
    channel = ssh.connection.interactive_session.Interactive_Session_Client(service)
    channel.open()
    channel.open_pty()
    channel.open_shell()
    set_stdin_unbuffered()
    coro.spawn(input_thread, channel)
    coro.spawn(transport_thread, channel)

def main():

    login_username = None
    ip = None

    try:
        optlist, args = getopt.getopt(sys.argv[1:], 'l:')
    except getopt.GetoptError, why:
        print str(why)
        usage()
        sys.exit(1)

    for option, value in optlist:
        if option=='l':
            login_username = value

    if len(args) != 1:
        usage()
        sys.exit(1)

    ip = args[0]
    if '@' in ip:
        login_username, ip = ip.split('@', 1)
    if not inet_utils.is_ip(ip):
        ip = socket.gethostbyname(ip)

    coro.spawn(doit, ip)
    try:
        coro.event_loop()
    finally:
        if oldterm:
            termios.tcsetattr(0, termios.TCSAFLUSH, oldterm)
            fcntl.fcntl(0, fcntl.F_SETFL, oldflags)

if __name__=='__main__':
    main()
