# -*- Mode: Cython -*-

class Lz4Error (Exception):
    "A problem with lz4"

# at this time (Apr 2012) the lz4 distribution does not generate a library
# something like the following steps will be necessary:
#
# $ cc -O3 lz4.c -o lz4.o -c
# $ ar rvs liblz4.a lz4.o 
# ar: creating archive liblz4.a
# a - lz4.o
# $ cp lz4.h /usr/local/include/
# $ cp liblz4.a /usr/local/lib

cimport lz4

cdef class zstack:
    cdef char * buffer
    cdef int buffer_size
    def __init__ (self, int size=1024*1024):
        cdef int r
        self.buffer = <char *>PyMem_Malloc (size)
        if not self.buffer:
            raise MemoryError
        self.buffer_size = size
    def __dealloc__ (self):
        if self.buffer:
            PyMem_Free (self.buffer)
    cdef size_t deflate (self, void * base, size_t size):
        return lz4.LZ4_compress (<char*>base, self.buffer, size)
    cdef size_t inflate (self, void * dst, size_t dsize, void * src, size_t ssize):
        return lz4.LZ4_uncompress (<char*>src, <char*>dst, dsize)
