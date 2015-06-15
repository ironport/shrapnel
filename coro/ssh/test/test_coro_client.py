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

from coro.log import redirect_stderr

def is_ip (s):
    if s.count ('%') == 1:
        s, intf = s.split('%')
    try:
        socket.inet_pton (coro.AF.INET6, s)
        return True
    except socket.error:
        try:
            socket.inet_pton (coro.AF.INET, s)
            return True
        except:
            return False

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
                stdout.write (data)
        except EOFError:
            break
    coro.set_exit()

def doit (ip, port, username, debug_level):
    if not is_ip (ip):
        ip = coro.get_resolver().resolve_ipv4 (ip)
    debug = coro.ssh.util.debug.Debug()
    debug.level = debug_level
    client = coro.ssh.transport.client.SSH_Client_Transport(debug=debug)
    transport = coro.ssh.l4_transport.coro_socket_transport.coro_socket_transport(ip, port=port)
    client.connect(transport)
    auth_method = coro.ssh.auth.userauth.Userauth(client, username)
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

    import argparse
    p = argparse.ArgumentParser (description = 'shrapnel ssh demo client')
    p.add_argument ('-l', '--login', help='login username')
    p.add_argument ('-p', '--port', type=int, help='server port', default=22)
    p.add_argument ('-d', '--debug', type=int, help='debug level', default=1) # WARNING
    p.add_argument ('hostname', help='hostname/address of server')

    args = p.parse_args()

    login_username = args.login
    port = args.port

    ip = args.hostname
    if '@' in ip:
        login_username, ip = ip.split('@', 1)

    import sys
    coro.spawn (doit, ip, port, login_username, args.debug)
    try:
        coro.event_loop()
    finally:
        if oldterm:
            termios.tcsetattr(0, termios.TCSAFLUSH, oldterm)
            fcntl.fcntl(0, fcntl.F_SETFL, oldflags)
        sys.stdout.flush()
        sys.stdout.close()

if __name__ == '__main__':
    main()
