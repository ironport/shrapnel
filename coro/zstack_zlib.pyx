# -*- Mode: Cython -*-

class ZlibError (Exception):
    "A problem with zlib"

cimport zlib

cdef class zstack:
    def __init__ (self, int size=4*1024*1024):
        cdef int r
        self.squish.zalloc = NULL
        self.squish.zfree  = NULL
        self.squish.opaque = NULL
        self.unsquish.zalloc = NULL
        self.unsquish.zfree  = NULL
        self.unsquish.opaque = NULL
        self.buffer = <unsigned char *>PyMem_Malloc (size)
        if not self.buffer:
            raise MemoryError
        self.buffer_size = size
        r = zlib.deflateInit (&self.squish, zlib.Z_BEST_SPEED)
        if r != zlib.Z_OK:
            raise ZlibError (r)
        r = zlib.inflateInit (&self.unsquish)
        if r != zlib.Z_OK:
            raise ZlibError (r)

    def __dealloc__ (self):
        zlib.deflateEnd (&self.squish)
        zlib.inflateEnd (&self.unsquish)
        PyMem_Free (self.buffer)

    cdef size_t deflate (self, void * base, size_t size):
        zlib.deflateReset (&self.squish)
        self.squish.next_in = <unsigned char *> base
        self.squish.avail_in = size
        self.squish.next_out = self.buffer
        self.squish.avail_out = self.buffer_size
        zlib.deflate (&self.squish, 1)
        # return the compressed size
        return self.buffer_size - self.squish.avail_out

    cdef size_t inflate (self, void * dst, size_t dsize, void * src, size_t ssize):
        zlib.inflateReset (&self.unsquish)
        self.unsquish.next_in = <unsigned char *>src
        self.unsquish.avail_in = ssize
        self.unsquish.next_out = <unsigned char *>dst
        self.unsquish.avail_out = dsize
        zlib.inflate (&self.unsquish, 1)
        # return the uncompressed size
        return dsize - self.unsquish.avail_out
