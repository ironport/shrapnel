# -*- Mode: Cython; indent-tabs-mode: nil -*-

# need to generalize this, make a module of it

from libc.stdint cimport uint64_t, uint32_t, uint16_t, uint8_t, int32_t, int16_t

cdef class unpacker:
    cdef readonly bytes data
    cdef unsigned char * d
    cdef readonly int len
    cdef readonly int pos

    def __init__ (self, bytes data):
        self.data = data
        self.d = data
        self.len = len(data)
        self.pos = 0
    
    cpdef need (self, int n):
        if self.pos + n > self.len:
            raise IndexError (self.len, self.pos +n)

    cpdef uint8_t u8 (self):
        "unpack a uint8_t"
        cdef uint8_t r
        self.need (1)
        r = self.d[self.pos]
        self.pos += 1
        return r

    cpdef char c (self):
        "unpack a single character"
        cdef char r
        self.need (1)
        r = self.d[self.pos]
        self.pos += 1
        return r

    cpdef uint16_t lu16 (self):
        "unpack a little-endian uint16_t"
        cdef uint16_t r
        self.need (2)
        r = (self.d[self.pos+1] << 8) | self.d[self.pos] 
        self.pos += 2
        return r

    cpdef uint16_t bu16 (self):
        "unpack a big-endian uint16_t"
        cdef uint16_t r
        self.need (2)
        r = (self.d[self.pos+0] << 8) | self.d[self.pos+1] 
        self.pos += 2
        return r

    cpdef int16_t b16 (self):
        "unpack a big-endian int16_t"
        cdef int16_t r
        self.need (2)
        r = (self.d[self.pos+0] << 8) | self.d[self.pos+1] 
        self.pos += 2
        return r

    cpdef uint32_t lu32 (self):
        "unpack a little-endian uint32_t"
        cdef uint32_t r = 0
        cdef int i
        self.need (4)
        for i in range (3,-1,-1):
            r <<= 8
            r |= self.d[self.pos+i]
        self.pos += 4
        return r

    cpdef uint32_t bu32 (self):
        "unpack a big-endian uint32_t"
        cdef uint32_t r = 0
        cdef int i
        self.need (4)
        for i in range (0, 4):
            r <<= 8
            r |= self.d[self.pos+i]
        self.pos += 4
        return r

    cpdef int32_t b32 (self):
        "unpack a big-endian int32_t"
        cdef int32_t r = 0
        cdef int i
        self.need (4)
        for i in range (0, 4):
            r <<= 8
            r |= self.d[self.pos+i]
        self.pos += 4
        return r

    cpdef uint64_t lu64 (self):
        "unpack a little-endian uint64_t"
        cdef uint64_t r = 0
        cdef int i
        self.need (8)
        for i in range (7,-1,-1):
            r <<= 8
            r |= self.d[self.pos+i]
        self.pos += 8
        return r

    cpdef uint64_t bu64 (self):
        "unpack a big-endian uint64_t"
        cdef uint64_t r = 0
        cdef int i
        self.need (8)
        for i in range (0, 8):
            r <<= 8
            r |= self.d[self.pos+i]
        self.pos += 8
        return r

    cpdef bytes zt (self):
        "unpack a zero-terminated string"
        cdef bytes result
        cdef int j = self.pos
        while j < self.len:
            if self.d[j] == '\x00':
                result = self.d[self.pos:j]
                self.pos = j + 1
                return result
            j += 1
        raise IndexError (self.len, self.len)

    cpdef bytes rest (self):
        "return any remaining bytes"
        cdef bytes result = self.d[self.pos:self.len]
        self.pos = self.len
        return result

def unpack_data (bytes data, bytes formats, bint return_rest=0):
    """Unpack the data part of a packed according to format:

    i: Int32
    h: Int16
    s: String
    c: Byte1 (returned as 1-character string)

    If return_rest is true, then return the rest of the
    data as the last item in the list.
    """
    cdef unsigned char * pf = formats
    cdef unsigned char code
    
    cdef unpacker UP = unpacker (data) 
    cdef list result = []

    for i in range (len (formats)):
        code = pf[i]
        if code == c'i':
            result.append (UP.b32())
        elif code == 'h':
            result.append (UP.b16())
        elif code == 'c':
            result.append (UP.c())
        elif code == 's':
            result.append (UP.zt())

    if return_rest:
        result.append (UP.rest())

    return result
