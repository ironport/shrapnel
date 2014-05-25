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
# ssh.l4_transport.coro_socket_transport
#
# Socket transport used by SSH.
#

import coro
from coro.dns.exceptions import DNS_Error
from coro.oserrors import raise_oserror
import errno
import socket
from coro.ssh import l4_transport
from coro.ssh.keys import remote_host

class coro_socket_transport(l4_transport.Transport):

    # The socket
    s = None
    # peer
    peer = None

    def __init__(self, ip=None, port=22, bind_ip=None, hostname=None, sock=None):
        self.ip = ip
        self.port = port
        self.bind_ip = bind_ip
        self.hostname = hostname
        if sock is None:
            if ':' in ip:
                self.s = coro.tcp6_sock()
            else:
                self.s = coro.tcp_sock()
        else:
            self.s = sock
            self.peer = self.s.getpeername()

    def connect(self):
        if self.bind_ip is not None:
            self.s.bind((self.bind_ip, 0))
        if '%' in self.ip:
            # link local address, need 4-tuple
            ai = socket.getaddrinfo (self.ip, self.port)
            address = ai[0][4]
            ip, port, flowinfo, scope_id = address
            ip, intf = ip.split ('%')
            self.s.connect ((ip, port, flowinfo, scope_id))
        else:
            self.s.connect((self.ip, self.port))

    def read(self, bytes):
        # XXX: This could be made more efficient.
        count = bytes
        result = []
        while count > 0:
            try:
                chunk = self.s.recv(count)
            except OSError, why:
                if why.errno == errno.EBADF:
                    raise EOFError
                else:
                    raise
            except coro.ClosedError:
                raise EOFError
            if len(chunk) == 0:
                raise EOFError
            count -= len(chunk)
            result.append(chunk)
        return ''.join(result)

    def write(self, bytes):
        try:
            return self.s.send(bytes)
        except OSError, why:
            if why.errno == errno.EBADF:
                raise_oserror(errno.EPIPE)
            else:
                raise
        except coro.ClosedError:
            raise_oserror(errno.EPIPE)

    def read_line(self):
        # XXX: This should be made more efficient with buffering.
        # However, the complexity and overhead of adding buffering just
        # to support reading the line at the beginning of the protocol
        # negotiation seems kinda silly.
        result = []
        while 1:
            try:
                it = self.s.recv(1)
            except OSError, why:
                if why.errno == errno.EBADF:
                    raise EOFError
                else:
                    raise
            except coro.ClosedError:
                raise EOFError
            if not it:
                raise EOFError

            if it == '\r':
                # This is a part of CR LF line ending.  Skip it.
                pass

            elif it == '\n':
                break

            else:
                result.append(it)

        return ''.join(result)

    def close(self):
        self.s.close()

    def get_hostname(self):
        if self.hostname is None:
            resolver = coro.get_resolver()
            try:
                in_addr = to_in_addr_arpa (self.ip)
                self.hostname = resolver.cache.query (in_addr, 'PTR')[0][1]
            except (DNS_Error, IndexError):
                # XXX: Log debug message.
                pass
        return self.hostname

    def get_host_id(self):
        return remote_host.IPv4_Remote_Host_ID(self.ip, self.get_hostname())

    def get_port(self):
        return self.port

# obviously ipv4 only
def to_in_addr_arpa (ip):
    octets = ip.split ('.')
    octets.reverse()
    return '%s.in-addr.arpa' % ('.'.join (octets))
