# -*- Mode: Cython -*-

class LzoError (Exception):
    "A problem with lzo"

cimport lzo

cdef class zstack:
    # lzo's working memory
    cdef unsigned char * wrkmem
    # this buffer is only used for compression
    cdef unsigned char * buffer
    cdef int buffer_size
    def __init__ (self, int size=4*1024*1024):
        cdef int r
        self.buffer = <unsigned char *>PyMem_Malloc (size)
        if not self.buffer:
            raise MemoryError
        self.buffer_size = size
        self.wrkmem = <unsigned char *>PyMem_Malloc (lzo.LZO1X_1_MEM_COMPRESS)

    def __dealloc__ (self):
        PyMem_Free (self.buffer)
        PyMem_Free (self.wrkmem)

    cdef size_t deflate (self, void * base, size_t size):
        cdef lzo.lzo_uint out_size = self.buffer_size
        cdef int r = lzo.lzo1x_1_compress (
            <unsigned char *>base, size,
            self.buffer, &out_size, self.wrkmem
            )
        if r != lzo.LZO_E_OK:
            raise LzoError (r)
        # return the compressed size
        return out_size

    cdef size_t inflate (self, void * dst, size_t dsize, void * src, size_t ssize):
        cdef lzo.lzo_uint out_size = dsize
        cdef int r = lzo.lzo1x_decompress (
            <unsigned char *>src, ssize,
            <unsigned char *>dst, &out_size, NULL
            )
        if r != lzo.LZO_E_OK:
            raise LzoError (r)
        # return the uncompressed size
        return out_size
