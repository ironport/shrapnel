# Copyright (c) 2002-2011 IronPort Systems and Cisco Systems
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

# -*- Mode: Python -*-

# first stab at coro SSL sockets.

import sslip
import coro
import socket
import coro_ssl
import string

# there are some instructions here:
#    http://members.netscapeonline.co.uk/jeremyalansmith/ssltutorial/
# that tell you how to quickly and easily generate some cert and key files.
# It's also pretty easy to generate them directly using the POW module.
# look in POW/test/utest.py for lots and lots of examples...
#
# also, for quick testing, you can't beat mini_httpd, by Poskanzer.
# The source tarball is 30k!  Compile it thus:
# 1) uncomment & edit the four SSL lines at the top of Makefile
# 2) gmake
# 3) run it: 'mini_httpd -S -p 443'

# You don't need a certificate to make a client connection.
# But: the server side can decide not to talk to you unless. [see ssl.setVerifyMode()]
# Netscape for example, does not use a certificate when making an https connection.


def http_client():
    "fetch a web page from an https server"
    client = coro_ssl.ssl_sock()
    client.create()
    client.connect (('192.168.200.44', 8080))
    client.send ('GET / HTTP/1.1\r\nConnection: close\r\n\r\n')
    data = ''
    while True:
        block = client.recv (8192)
        if block:
            data += block
        else:
            break
    print data
    client.close()

def client():
    "test echo client"
    client = coro_ssl.ssl_sock()
    client.create()
    client.connect (('127.0.0.1', 9090))
    print client.recv (8192)
    for i in range (10):
        client.send ('Hello There (%d)\r\n' % i)
        print client.recv (8192)
    client.close()

def channel (conn, addr):
    "echo server client thread"
    peer_cert = conn.ssl.get_peer_cert()
    if peer_cert:
        print 'peer CN=%r' % (peer_cert.get_cn(),)
    else:
        print 'no peer cert'
    conn.send ('Hi there %r\n' % (addr,))
    print 'cipher=', conn.ssl.get_cipher()
    while True:
        line = conn.recv (8192)
        if not line:
            break
        else:
            conn.send (line)

def server (port=9090):
    "echo server"
    server = coro_ssl.ssl_sock()
    server.create()
    server.bind (('', port))
    server.listen (1024)
    while True:
        conn, addr = server.accept()
        coro.spawn (channel, conn, addr)

def smtp_tls_server_session (conn):
    oconn = conn
    conn.send ('200 howdy\r\n')
    while True:
        cmd = conn.recv (1024)
        coro.print_stderr ('got %r\r\n' % (cmd,))
        cmd = cmd.lower()
        if cmd.startswith ('starttls'):
            conn.send ('220 ready for tls\r\n')
            ctx = coro_ssl.ssl_ctx (sslip.SSLV23_SERVER_METHOD)
            try:
                sconn = coro_ssl.ssl_sock (ctx)
                sconn.create (sock=conn)
                sconn.ssl_accept()
                conn = sconn
            except sslip.Error:
                # conn.send ('454 TLS negotiation failed\r\n')
                pass
        elif cmd.startswith ('data'):
            conn.send ('354 go ahead\r\n')
            while True:
                block = conn.recv (8192)
                if block.endswith ('\r\n.\r\n'):
                    break
            conn.send ('250 Ok.\r\n')
        elif cmd.startswith ('quit'):
            conn.send ('221 byte\r\n')
            conn.close()
            break
        elif cmd.startswith ('ehlo'):
            conn.send (
                '250-loki.ironport.com\r\n'
                '250-PIPELINING\r\n'
                '250-SIZE 10240000\r\n'
                '250-STARTTLS\r\n'
                '250 8BITMIME\r\n'
            )
        else:
            conn.send ('200 ok\r\n')

def smtp_tls_server():
    sock = coro.make_socket (socket.AF_INET, socket.SOCK_STREAM)
    sock.bind (('0.0.0.0', 25))
    sock.listen (5)
    while True:
        conn, addr = sock.accept()
        coro.spawn (smtp_tls_server_session, conn)

# an easy way to test this is to install the qmail-tls port.
# [tricky, had to rename /var/qmail/control/cert.pem to servercert.pem]
def smtp_tls_session (
    host,
    port='25',
    fromaddr='rushing@nightmare.com',
    to='rushing@nightmare.com'
):
    print "smtp tls test client"
    sock = coro.make_socket (socket.AF_INET, socket.SOCK_STREAM)
    print "host=%r port=%r" % (host, port)
    port = string.atoi(port)
    sock.connect ((host, port))
    print sock.recv (8192)
    sock.send ('EHLO fang\r\n')
    print sock.recv (8192)
    sock.send ('STARTTLS\r\n')
    print sock.recv (8192)
    ctx = coro_ssl.ssl_ctx (sslip.SSLV2_CLIENT_METHOD)
    client = coro_ssl.ssl_sock (ctx)
    client.create (sock=sock)
    # client.ssl.set_connect_state()
    try:
        coro.print_stderr ('calling ssl_connect()\n')
        client.ssl_connect()
        coro.print_stderr ('ssl_connect done()\n')
    except sslip.Error:
        coro.print_stderr ("TLS negotiation failed\n")
        coro.print_stderr ("hit <return> to attempt fallback\n")
        client.shutdown()
        raw_input()
    else:
        sock = client
    print "ssl_connect() finished"
    sock.send ('HELP\r\n')
    print sock.recv (8192)
    sock.send ('MAIL FROM:<' + fromaddr + '>\r\n')
    print sock.recv (8192)
    sock.send ('RCPT TO:<' + to + '>\r\n')
    print sock.recv (8192)
    sock.send ('DATA\r\n')
    print sock.recv (8192)
    sock.send ('From: ' + fromaddr + '\r\nSubject: testing STARTTLS\r\n\r\nHi there.  I was encrypted\r\n.\r\n')
    print sock.recv (8192)
    sock.send ('QUIT\r\n')
    print sock.recv (8192)
    sock.close()
    coro._exit = 1

if __name__ == '__main__':
    import backdoor
    import sys
    fromaddr = 'srushing@ironport.com'
    to = 'srushing@ironport.com'
    host = '192.168.200.6'
    port = '25'
    coro.spawn (backdoor.serve)
    if '-s' in sys.argv:
        coro.spawn (server)
    elif '--smtp-tls-server' in sys.argv:
        coro.spawn (smtp_tls_server)
    elif '--smtp-tls' in sys.argv:
        if '--host' in sys.argv:
            i = 1 + sys.argv.index('--host')
            host = sys.argv[i]
        if '--port' in sys.argv:
            i = 1 + sys.argv.index('--port')
            port = sys.argv[i]
        if '--from' in sys.argv:
            i = 1 + sys.argv.index('--from')
            fromaddr = sys.argv[i]
        if '--to' in sys.argv:
            i = 1 + sys.argv.index('--to')
            to = sys.argv[i]
        coro.spawn (smtp_tls_session, host, port, fromaddr, to)
    else:
        coro.spawn (client)
    coro.event_loop (30.0)
