# -*- Mode: Python; tab-width: 4 -*-
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

import coro
import os
import socket
import string

def client (conn, addr):
    # get request line
    request = conn.recv (8192)
    lines = string.split (request, '\r\n')
    filename = lines[0]
    if os.path.isfile (filename):
        fd = os.open (filename, os.O_RDONLY)
        length = os.lseek (fd, 0, 2)
        os.lseek (fd, 0, 0)
        conn.sendfile (fd, 0, length)
        conn.send ('bye.\r\n')
        os.close (fd)
    else:
        conn.send ('no such file!\r\n')
    conn.close()

def server (port=18080):
    s = coro.coroutine_socket()
    s.create_socket (socket.AF_INET, socket.SOCK_STREAM)
    s.set_reuse_addr()
    s.bind (('', port))
    s.listen (1024)
    while True:
        conn, addr = s.accept()
        coro.spawn (client, conn, addr)

if __name__ == '__main__':
    coro.spawn (server)
    coro.event_loop (30.0)
