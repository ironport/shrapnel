# -*- Mode: Cython -*-

# http://code.google.com/p/lz4/

cdef extern from "lz4.h":
    cdef int LZ4_compress   (char * source, char * dest, int isize)
    cdef int LZ4_uncompress (char * source, char * dest, int osize)
    cdef int LZ4_compressBound (int isize)
    cdef int LZ4_uncompress_unknownOutputSize (char * source, char * dest, int isize, int maxOutputSize)
    # these are apparently static...
    #cdef int LZ4_compressCtx (void ** ctx, char * source, char * dest, int isize)
    #cdef int LZ4_compress64kCtx (void ** ctx, char * source, char * dest, int isize)
