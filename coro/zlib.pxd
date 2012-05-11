# -*- Mode: Cython -*-

# minimal interface to zlib

cdef extern from "zlib.h":

    ctypedef struct z_stream:
        unsigned char * next_in  # next input byte
        unsigned int avail_in    # number of bytes available at next_in
        unsigned long total_in   # total nb of input bytes read so far
        unsigned char * next_out # next output byte should be put there
        unsigned int avail_out   # remaining free space at next_out
        unsigned long total_out  # total nb of bytes output so far
        void * zalloc
        void * zfree
        void * opaque
    
    cdef int deflateInit  (z_stream *, int)
    cdef int deflate      (z_stream *, int)
    cdef int deflateEnd   (z_stream *)
    cdef int deflateReset (z_stream *)
    cdef int inflateInit  (z_stream *)
    cdef int inflate      (z_stream *, int)
    cdef int inflateEnd   (z_stream *)
    cdef int inflateReset (z_stream *)
    cdef int deflateSetDictionary (z_stream *, unsigned char *, unsigned int)
    cdef int inflateSetDictionary (z_stream *, unsigned char *, unsigned int)

    cdef enum FLUSH_VALUES:
        Z_NO_FLUSH
        Z_PARTIAL_FLUSH
        Z_SYNC_FLUSH
        Z_FULL_FLUSH
        Z_FINISH
        Z_BLOCK
        Z_TREES

    cdef enum COMPRESSION_LEVELS:
        Z_NO_COMPRESSION,
        Z_BEST_SPEED,
        Z_BEST_COMPRESSION,
        Z_DEFAULT_COMPRESSION

    cdef enum RETURN_VALUES:
        Z_OK,
        Z_STREAM_END,
        Z_NEED_DICT,
        Z_ERRNO,
        Z_STREAM_ERROR,
        Z_DATA_ERROR,
        Z_MEM_ERROR,
        Z_BUF_ERROR,
        Z_VERSION_ERROR

