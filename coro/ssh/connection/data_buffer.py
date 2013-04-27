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
# ssh.connection.data_buffer
#
# This implements a simple buffer class that works like a FIFO.
# It is time-effecient since it tries to avoid string copies whenever
# possible.

__version__ = '$Revision: #1 $'

import coro_fifo

class Buffer:

    def __init__(self):
        self.fifo = coro_fifo.circular_fifo()

    def __len__(self):
        return len(self.fifo)

    def write(self, data):
        """write(self, data) -> None
        Writes data to the buffer.
        """
        self.fifo.enqueue(data)

    def pop(self):
        """pop(self) -> str
        Pops the first string from the buffer.
        """
        return self.fifo.dequeue()

    def read_at_most(self, bytes):
        """read_at_most(self, bytes) -> str
        Reads at most <bytes>.
        May return less than <bytes> even if there is more data in the buffer.
        Returns the empty string when the buffer is empty.
        """
        while 1:
            try:
                data = self.fifo.peek()
            except IndexError:
                # Buffer empty.
                self.fifo.cv.wait()
            else:
                break
        if not data:
            raise EOFError
        if len(data) > bytes:
            result = data[:bytes]
            self.fifo.poke(data[bytes:])
            return result
        else:
            return self.fifo.dequeue()
