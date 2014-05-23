# -*- Mode: Python -*-

class socket_producer:
    def __init__ (self, conn, buffer_size=8000):
        self.conn = conn
        self.buffer_size = buffer_size

    def next (self):
        return self.conn.recv (self.buffer_size)

def sock_stream (sock):
    return buffered_stream (socket_producer (sock).next)

class buffered_stream:

    def __init__ (self, producer):
        self.producer = producer
        self.buffer = ''

    def gen_read_until (self, delim):
        "generate pieces of input up to and including <delim>, then StopIteration"
        ld = len(delim)
        m = 0
        while 1:
            if not self.buffer:
                self.buffer = self.producer()
                if not self.buffer:
                    # eof
                    yield ''
                    return
            i = 0
            while i < len (self.buffer):
                if self.buffer[i] == delim[m]:
                    m += 1
                    if m == ld:
                        result, self.buffer = self.buffer[:i + 1], self.buffer[i + 1:]
                        yield result
                        return
                else:
                    m = 0
                i += 1
            block, self.buffer = self.buffer, ''
            yield block

    def gen_read_until_dfa (self, dfa):
        "generate pieces of input up to and including a match on <dfa>, then StopIteration"
        m = 0
        while 1:
            if not self.buffer:
                self.buffer = self.producer()
                if not self.buffer:
                    # eof
                    yield ''
                    return
            i = 0
            while i < len (self.buffer):
                if dfa.consume (self.buffer[i]):
                    result, self.buffer = self.buffer[:i + 1], self.buffer[i + 1:]
                    yield result
                    return
                i += 1
            block, self.buffer = self.buffer, ''
            yield block

    def gen_read_exact (self, size):
        "generate pieces of input up to <size> bytes, then StopIteration"
        remain = size
        while remain:
            if len (self.buffer) >= remain:
                result, self.buffer = self.buffer[:remain], self.buffer[remain:]
                yield result
                return
            else:
                piece, self.buffer = self.buffer, self.producer()
                remain -= len (piece)
                yield piece
                if not self.buffer:
                    # eof
                    yield ''
                    return

    def read_until (self, delim, join=True):
        "read until <delim>.  return a list of parts unless <join> is True"
        result = (x for x in self.gen_read_until (delim))
        if join:
            return ''.join (result)
        else:
            return result

    def read_exact (self, size, join=True):
        "read exactly <size> bytes.  return a list of parts unless <join> is True"
        result = (x for x in self.gen_read_exact (size))
        if join:
            return ''.join (result)
        else:
            return result

    def flush (self):
        "flush this stream's buffer"
        result, self.buffer = self.buffer, ''
        return result

    def read_line (self, delim='\r\n'):
        "read a CRLF-delimited line from this stream"
        return self.read_until (delim)

    def read_all (self):
        "read from self.producer until the stream terminates"
        if self.buffer:
            yield self.flush()
        while 1:
            block = self.producer()
            if not block:
                return
            else:
                yield block
