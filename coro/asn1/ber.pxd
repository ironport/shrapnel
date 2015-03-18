# -*- Mode: Cython -*-

from libc.stdint cimport uint8_t

# flags for BER tags
cdef enum FLAGS:
    FLAGS_UNIVERSAL       = 0b00000000
    FLAGS_STRUCTURED      = 0b00100000
    FLAGS_APPLICATION     = 0b01000000
    FLAGS_CONTEXT         = 0b10000000

# NULL is a pyrex keyword
# universal BER tags
cdef enum TAGS:
    TAGS_BOOLEAN          = 0x01
    TAGS_INTEGER          = 0x02
    TAGS_BITSTRING        = 0x03
    TAGS_OCTET_STRING     = 0x04
    TAGS_NULL             = 0x05
    TAGS_OBJID            = 0x06
    TAGS_OBJDESCRIPTOR    = 0x07
    TAGS_EXTERNAL         = 0x08
    TAGS_REAL             = 0x09
    TAGS_ENUMERATED       = 0x0a
    TAGS_EMBEDDED_PDV     = 0x0b
    TAGS_UTF8STRING       = 0x0c
    TAGS_SEQUENCE         = 0x10
    TAGS_SET              = 0x11

cdef long length_of_length (long n)
cdef long length_of_tag (long n)
cdef void encode_length (long l, long n, uint8_t * buffer)
cdef object _encode_integer (long n)
cdef object _encode_long_integer (n)
cdef object _TLV1 (long tag, uint8_t flags, bytes data)
cdef object _TLV (long tag, uint8_t flags, object data)
cdef object _CHOICE (long n, bint structured)
cdef object _ENUMERATED (long n)
cdef object _INTEGER (long n)
cdef object _BOOLEAN (long n)
cdef object _SEQUENCE (object elems)
cdef object _SET (object elems)
cdef object _OCTET_STRING (bytes s)
cdef object _OBJID (list l)
cdef object _BITSTRING (uint8_t unused, bytes s)
cdef object _UTF8_STRING (unicode s)
cdef object decode_string (unsigned char * s, long * pos, long length)
cdef object decode_raw (unsigned char * s, long * pos, long length)
cdef object decode_bitstring (unsigned char * s, long * pos, long length)
cdef object decode_integer (unsigned char * s, long * pos, long length)
cdef object decode_long_integer (unsigned char * s, long * pos, long length)
cdef object decode_structured (unsigned char * s, long * pos, long length)
cdef object decode_objid (unsigned char * s, long * pos, long length)
cdef object decode_boolean (unsigned char * s, long * pos, long length)
cdef long _decode_length (unsigned char * s, long * pos, long lol) except? -1
cdef object _decode (unsigned char * s, long * pos, long eos, bint just_tlv)
