# -*- Mode: Cython -*-

cimport zlib

cdef class zstack:
    cdef zlib.z_stream squish, unsquish
    # this buffer is only used for compression
    cdef unsigned char * buffer
    cdef int buffer_size
    cdef size_t deflate (self, void * base, size_t size)
    cdef size_t inflate (self, void * dst, size_t dsize, void * src, size_t ssize)
