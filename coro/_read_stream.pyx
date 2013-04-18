# -*- Mode: Cython -*-

cdef class buffered_stream:
    cdef object producer
    cdef bytes buffer
    cdef int pos

    def __init__ (self, producer):
        self.producer = producer
        self.buffer = b''
        self.pos = 0

    def gen_read_until (self, bytes delim):
        "generate pieces of input up to and including <delim>, then StopIteration"
        cdef int ld = len (delim)
        cdef char * pdelim = delim
        cdef char * pbuffer
        cdef int lb = 0
        cdef int m = 0
        cdef int i = 0
        while 1:
            if self.pos == len(self.buffer):
                self.buffer = self.producer()
                self.pos = 0
                if not self.buffer:
                    # eof
                    yield b''
                    return
            i = self.pos
            lb = len (self.buffer)
            pbuffer = self.buffer
            while i < lb:
                if pbuffer[i] == pdelim[m]:
                    m += 1
                    if m == ld:
                        yield pbuffer[self.pos:i+1]
                        self.pos = i+1
                        return
                else:
                    m = 0
                i += 1
            block, self.buffer = self.buffer[self.pos:], b''
            self.pos = 0
            yield block

    def read_until (self, bytes delim, bint join=True):
        "read until <delim>.  return a list of parts unless <join> is True"
        result = ( x for x in self.gen_read_until (delim) )
        if join:
            return ''.join (result)
        else:
            return result

    def flush (self):
        "flush this stream's buffer"
        result, self.buffer = self.buffer, b''
        self.pos = 0
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
