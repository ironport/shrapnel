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

__version__ = '$Revision: #2 $'

import coro
import dnsqr
import dns_exceptions
import errno
import inet_utils
import ironutil
import socket
import ssh.l4_transport
import ssh.keys.remote_host

class coro_socket_transport(ssh.l4_transport.Transport):

    # The socket
    s = None

    def __init__(self, ip, port=22, bind_ip=None, hostname=None):
        assert inet_utils.is_ip(ip)
        self.ip = ip
        self.port = port
        self.bind_ip = bind_ip
        self.hostname = hostname
        self.s = coro.make_socket(socket.AF_INET, socket.SOCK_STREAM)

    def connect(self):
        if self.bind_ip is not None:
            self.s.bind((self.bind_ip, 0))

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
            if len(chunk)==0:
                raise EOFError
            count -= len(chunk)
            result.append(chunk)
        return ''.join(result)

    def write(self, bytes):
        try:
            return self.s.send(bytes)
        except OSError, why:
            if why.errno == errno.EBADF:
                ironutil.raise_oserror(errno.EPIPE)
            else:
                raise
        except coro.ClosedError:
            ironutil.raise_oserror(errno.EPIPE)

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
            try:
                in_addr = inet_utils.to_in_addr(self.ip)
                self.hostname = dnsqr.query (in_addr, 'PTR')[0][1]
            except (dns_exceptions.DNS_Error, IndexError):
                # XXX: Log debug message.
                pass
        return self.hostname

    def get_host_id(self):
        return ssh.keys.remote_host.IPv4_Remote_Host_ID(self.ip, self.get_hostname())
