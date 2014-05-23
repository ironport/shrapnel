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

# code is from jesse, thx.

import coro
import termios

# from Python/Lib/tty.py
# Indexes for termios list.
IFLAG = 0
OFLAG = 1
CFLAG = 2
LFLAG = 3
ISPEED = 4
OSPEED = 5
CC = 6

class stdin (coro.sock):

    def __init__ (self):
        coro.sock.__init__ (self, fd=0)
        self.fd = 0
        self.old = termios.tcgetattr (self.fd)
        # print 'old=%r' % (self.old,)
        self.new = termios.tcgetattr (self.fd)
        self.new[LFLAG] &= ~(termios.ICANON | termios.ECHO  | termios.IEXTEN)
        self.new[IFLAG] &= ~(termios.IGNBRK | termios.IXOFF | termios.IXON)
        self.new[CC][termios.VMIN] = 1
        self.new[CC][termios.VTIME] = 0
        self.new[CC][termios.CINTR] = 254  # block ctrl-c?  doesn't work.
        # print 'new=%r' % (self.new,)
        termios.tcsetattr (self.fd, termios.TCSANOW, self.new)

    def __dealloc__ (self):
        self.restore()

    def restore (self):
        # print '[restoring stdin to %r]' % (self.old,)
        termios.tcsetattr (self.fd, termios.TCSAFLUSH, self.old)

    def read (self, size):
        return self.recv (size)

    def write (self, data):
        return self.send (data)

    def writelines (self, list):
        return self.writev (filter (None, list))

# to use:
#
# s = stdin()
# while 1:
#     block = s.recv (1024)
#
# be sure to call restore() or your terminal will be hosed.
