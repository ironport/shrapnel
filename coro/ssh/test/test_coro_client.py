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
#
# SMR 2013: seems to kinda work on OSX

import coro.ssh.transport.client
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
    print 'test_coro_client [-l login_name] [-p port] hostname | user@hostname'

import re
is_ip_re = re.compile ('[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$')

# cheap emulation of inet_utils.is_ip()
def is_ip (s):
    return is_ip_re.match (s)    

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

def doit (ip, port):
    if not is_ip (ip):
        ip = coro.get_resolver().resolve_ipv4 (ip)
    debug = coro.ssh.util.debug.Debug()
    debug.level = coro.ssh.util.debug.DEBUG_1
    client = coro.ssh.transport.client.SSH_Client_Transport(debug=debug)
    transport = coro.ssh.l4_transport.coro_socket_transport.coro_socket_transport(ip, port=port)
    client.connect(transport)
    auth_method = coro.ssh.auth.userauth.Userauth(client)
    service = coro.ssh.connection.connect.Connection_Service(client)
    client.authenticate(auth_method, service.name)
    channel = coro.ssh.connection.interactive_session.Interactive_Session_Client(service)
    channel.open()
    channel.open_pty()
    channel.open_shell()
    set_stdin_unbuffered()
    coro.spawn(input_thread, channel)
    coro.spawn(transport_thread, channel)

def main():

    login_username = None
    ip = None
    port = 22

    try:
        optlist, args = getopt.getopt(sys.argv[1:], 'l:p:')
    except getopt.GetoptError, why:
        print str(why)
        usage()
        sys.exit(1)

    for option, value in optlist:
        if option=='-l':
            login_username = value
        elif option=='-p':
            port = int (value)

    if len(args) != 1:
        usage()
        sys.exit(1)

    ip = args[0]
    if '@' in ip:
        login_username, ip = ip.split('@', 1)

    coro.spawn(doit, ip, port)
    try:
        coro.event_loop()
    finally:
        if oldterm:
            termios.tcsetattr(0, termios.TCSAFLUSH, oldterm)
            fcntl.fcntl(0, fcntl.F_SETFL, oldflags)

if __name__=='__main__':
    main()
