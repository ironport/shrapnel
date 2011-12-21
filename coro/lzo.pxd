# -*- Mode: Cython -*-

# www.oberhumer.com
# Note: LZO is LGPL

cdef extern from "lzo/lzo1x.h":

    cdef enum RETURN_VALUES:
        LZO_E_OK,
        LZO_E_ERROR,
        LZO_E_OUT_OF_MEMORY,
        LZO_E_NOT_COMPRESSIBLE,
        LZO_E_INPUT_OVERRUN,
        LZO_E_OUTPUT_OVERRUN,
        LZO_E_LOOKBEHIND_OVERRUN,
        LZO_E_EOF_NOT_FOUND,
        LZO_E_INPUT_NOT_CONSUMED,
        LZO_E_NOT_YET_IMPLEMENTED,
        LZO_E_INVALID_ARGUMENT

    cdef enum BUFFER_SIZES:
        LZO1X_1_MEM_COMPRESS

    ctypedef unsigned char * lzo_bytep
    ctypedef unsigned int lzo_uint
    ctypedef lzo_uint * lzo_uintp
    ctypedef void * lzo_voidp
    
    cdef int lzo_init()
    cdef char * lzo_version_string()
    cdef char * lzo_version_date()

    # decompression
    cdef int lzo1x_decompress (
        lzo_bytep src, lzo_uint src_len,
        lzo_bytep dst, lzo_uintp dst_len,
        lzo_voidp wrkmem # NOT USED
        )

    # safe decompression with overrun testing
    cdef int lzo1x_decompress_safe (
        lzo_bytep src, lzo_uint src_len,
        lzo_bytep dst, lzo_uintp dst_len,
        lzo_voidp wrkmem # NOT USED
        )

    # compression
    cdef int lzo1x_1_compress (
        lzo_bytep src, lzo_uint  src_len,
        lzo_bytep dst, lzo_uintp dst_len,
        lzo_voidp wrkmem
        )
