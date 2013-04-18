# -*- Mode: Python -*-

# smtp load generator

import coro
import re
import socket
import string

#
usage_message = """
python %s server
    [-h <host>]
    [-p <port>]
    [-c <nconns>]
    [-m <nmessages>]
    [-i <nidle>]
    [-r <nrcpts>]
"""

def usage ():
    sys.stderr.write (usage_message % sys.argv[0])

class smtp_client:

    buffer_size = 8192
    response_re = re.compile ('([0-9][0-9][0-9])([ -])(.*)')

    def __init__ (self):
        self.s = coro.make_socket (socket.AF_INET, socket.SOCK_STREAM)
        self.buffer = ''
        self.lines = []

    def connect (self, address):
        self.s.connect (address)

    def read_line (self):
        if self.lines:
            l = self.lines[0]
            self.lines = self.lines[1:]
            return l
        else:
            while not self.lines:
                buffer = self.s.recv (self.buffer_size)
                lines = buffer.split ('\r\n')
                for l in lines[:-1]:
                    self.lines.append (l)
                self.buffer = lines[-1]
            return self.read_line()

    def get_response (self):
        result = ''
        while 1:
            line = self.read_line()
            m = self.response_re.match (line)
            if not m:
                raise ProtocolError, repr(line)
            else:
                code, cont, text = m.groups()
                result = result + text + '\n'
                if cont == ' ':
                    return code, result

    def command (self, command):
        self.s.send (command + '\r\n')
        return self.get_response()

    def send (self, data):
        return self.s.send (data)

def smtp_session (ip, port, nm, nr):
    s = smtp_client()
    s.connect ((ip, port))
    s.get_response()
    sys.stderr.write ('+')
    for x in range(nm):
        code, text = s.command ('MAIL FROM:<fred@hell.org>')
        for y in range(nr):
            code, text = s.command ('RCPT TO:<fred%d@hell.org>' %y)
        # we need to check the reply codes...
        code, text = s.command ('DATA')
        s.send (
            "Subject: testing\r\n\r\n"
            "This is message #%d\r\n" % x +
            "BCNU\r\n"
            "\r\n.\r\n"
            )
        code, text = s.get_response()
        sys.stderr.write ('m')
    s.command ('QUIT')
    sys.stderr.write('-')
    global count
    count = count - 1
    #print 'count =',count
    if count == 0:
        coro.set_exit()

count = None

def go (ip, port, nc, nm, ni, nr):
    global count
    count = nc
    for i in range (nc):
        coro.spawn (smtp_session, ip, port, nm, nr)

if __name__ == '__main__':
    import sys
    import getopt

    nc = 10
    nm = 100
    ni = 0
    nr = 1
    port = 25
    host = None
    backdoor = 0

    opts, args = getopt.getopt (sys.argv[1:], "h:c:m:i:p:r:b")

    for o, a in opts:
        if o == '-h':
            host = a
        elif o == '-c':
            nc = int(a)
        elif o == '-m':
            nm = int(a)
        elif o == '-i':
            ni = int(a)
        elif o == '-p':
            port = int(a)
        elif o == '-r':
            nr = int(a)
        elif o == '-b':
            backdoor = 1

    if not host:
        usage()
    else:

        if backdoor:
            import backdoor
            coro.spawn (backdoor.serve, 8023)

        ip = socket.gethostbyname (host)
        go (ip, port, nc, nm, ni, nr)
        coro.event_loop()
        import os
        os._exit(1)
