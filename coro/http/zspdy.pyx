# -*- Mode: Cython -*-

# SPDY uses zlib's deflate/inflate with a predefined dictionary.
# see http://www.chromium.org/spdy/spdy-protocol/spdy-protocol-draft3

cimport zlib
from cpython.mem cimport PyMem_Malloc, PyMem_Free
from cpython.bytes cimport PyBytes_FromStringAndSize
from libc.stdint cimport uint32_t, uint16_t
from libc.string cimport memcpy

draft3_dict = (
	'\x00\x00\x00\x07options\x00\x00\x00\x04head\x00\x00\x00\x04post\x00\x00\x00\x03'
	'put\x00\x00\x00\x06delete\x00\x00\x00\x05trace\x00\x00\x00\x06accept\x00\x00\x00'
	'\x0eaccept-charset\x00\x00\x00\x0faccept-encoding\x00\x00\x00\x0faccept-langua'
	'ge\x00\x00\x00\raccept-ranges\x00\x00\x00\x03age\x00\x00\x00\x05allow\x00\x00\x00'
	'\rauthorization\x00\x00\x00\rcache-control\x00\x00\x00\nconnection\x00\x00\x00'
	'\x0ccontent-base\x00\x00\x00\x10content-encoding\x00\x00\x00\x10content-langua'
	'ge\x00\x00\x00\x0econtent-length\x00\x00\x00\x10content-location\x00\x00\x00\x0b'
	'content-md5\x00\x00\x00\rcontent-range\x00\x00\x00\x0ccontent-type\x00\x00\x00'
	'\x04date\x00\x00\x00\x04etag\x00\x00\x00\x06expect\x00\x00\x00\x07expires\x00\x00'
	'\x00\x04from\x00\x00\x00\x04host\x00\x00\x00\x08if-match\x00\x00\x00\x11if-mod'
	'ified-since\x00\x00\x00\rif-none-match\x00\x00\x00\x08if-range\x00\x00\x00\x13'
	'if-unmodified-since\x00\x00\x00\rlast-modified\x00\x00\x00\x08location\x00\x00'
	'\x00\x0cmax-forwards\x00\x00\x00\x06pragma\x00\x00\x00\x12proxy-authenticate\x00'
	'\x00\x00\x13proxy-authorization\x00\x00\x00\x05range\x00\x00\x00\x07referer\x00'
	'\x00\x00\x0bretry-after\x00\x00\x00\x06server\x00\x00\x00\x02te\x00\x00\x00\x07'
	'trailer\x00\x00\x00\x11transfer-encoding\x00\x00\x00\x07upgrade\x00\x00\x00\nu'
	'ser-agent\x00\x00\x00\x04vary\x00\x00\x00\x03via\x00\x00\x00\x07warning\x00\x00'
	'\x00\x10www-authenticate\x00\x00\x00\x06method\x00\x00\x00\x03get\x00\x00\x00\x06'
	'status\x00\x00\x00\x06200 OK\x00\x00\x00\x07version\x00\x00\x00\x08HTTP/1.1\x00'
	'\x00\x00\x03url\x00\x00\x00\x06public\x00\x00\x00\nset-cookie\x00\x00\x00\nkee'
	'p-alive\x00\x00\x00\x06origin1001012012022052063003023033043053063074024054064'
	'07408409410411412413414415416417502504505203 Non-Authoritative Information204 '
	'No Content301 Moved Permanently400 Bad Request401 Unauthorized403 Forbidden404'
	' Not Found500 Internal Server Error501 Not Implemented503 Service UnavailableJ'
	'an Feb Mar Apr May Jun Jul Aug Sept Oct Nov Dec 00:00:00 Mon, Tue, Wed, Thu, F'
	'ri, Sat, Sun, GMTchunked,text/html,image/png,image/jpg,image/gif,application/x'
	'ml,application/xhtml+xml,text/plain,text/javascript,publicprivatemax-age=gzip,'
	'deflate,sdchcharset=utf-8charset=iso-8859-1,utf-,*,enq=0.'
	)

class ZlibError (Exception):
    "A problem with zlib"

class ZSpdyBufferTooLarge (Exception):
    "Header buffer was too large for zspdy"

# XXX consider using alloca so the user can request a different size buffer.
cdef enum:
    BUFFER_SIZE = 4000

cdef class deflator:
    cdef zlib.z_stream zstr
    def __init__ (self, int level=zlib.Z_DEFAULT_COMPRESSION):
        cdef int r
        self.zstr.zalloc = NULL
        self.zstr.zfree = NULL
        self.zstr.opaque = NULL
        r = zlib.deflateInit (&self.zstr, level)
        if r != zlib.Z_OK:
            raise ZlibError (r)
        r = zlib.deflateSetDictionary (&self.zstr, draft3_dict, len(draft3_dict))
        if r != zlib.Z_OK:
            raise ZlibError (r)
        
    def __call__ (self, bytes input):
        cdef unsigned char output[BUFFER_SIZE]
        cdef int r
        if len(input) >= BUFFER_SIZE:
            raise ZSpdyBufferTooLarge (len(input))
        self.zstr.avail_in = len (input)
        self.zstr.next_in = input
        self.zstr.next_out = &output[0]
        self.zstr.avail_out = BUFFER_SIZE
        r = zlib.deflate (&self.zstr, zlib.Z_SYNC_FLUSH)
        if r != zlib.Z_OK:
            raise ZlibError (r)
        else:
            return output[:BUFFER_SIZE - self.zstr.avail_out]

    def __dealloc__ (self):
        zlib.deflateEnd (&self.zstr)

cdef class inflator:
    cdef zlib.z_stream zstr
    def __init__ (self):
        cdef int r
        self.zstr.zalloc = NULL
        self.zstr.zfree = NULL
        self.zstr.opaque = NULL
        r = zlib.inflateInit (&self.zstr)
        if r != zlib.Z_OK:
            raise ZlibError (r)
        
    def __call__ (self, bytes input):
        cdef unsigned char output[BUFFER_SIZE]
        cdef int r
        if len(input) >= BUFFER_SIZE:
            raise ZSpdyBufferTooLarge (len(input))
        self.zstr.avail_in = len (input)
        self.zstr.next_in = input
        self.zstr.next_out = &output[0]
        self.zstr.avail_out = BUFFER_SIZE
        while 1:
            r = zlib.inflate (&self.zstr, zlib.Z_SYNC_FLUSH)
            if r == zlib.Z_OK:
                return output[:BUFFER_SIZE - self.zstr.avail_out]
            elif r == zlib.Z_NEED_DICT:
                r = zlib.inflateSetDictionary (&self.zstr, draft3_dict, len(draft3_dict))
                if r != zlib.Z_OK:
                    raise ZlibError (r)
                # retry
            # XXX test with a tiny buffer (or huge header) to see what happens
            #   when BUFFER_SIZE isn't big enough.

    def __dealloc__ (self):
        zlib.inflateEnd (&self.zstr)

# helper functions for the spdy protocol

cdef pack16 (int n, unsigned char * buffer, int offset):
    if n < 0 or n >= 0x10000:
        raise ValueError (n)
    else:
        buffer[offset+0] = (n >> 8) & 0xff
        buffer[offset+1] = n & 0xff

cdef pack24 (int n, unsigned char * buffer, int offset):
    if n < 0 or n >= 0x1000000:
        raise ValueError (n)
    else:
        buffer[offset+0] = (n >> 16) & 0xff
        buffer[offset+1] = (n >>  8) & 0xff
        buffer[offset+2] = (n >>  0) & 0xff

cdef pack32 (int n, unsigned char * buffer, int offset):
    if n < 0 or n >= 0x100000000:
        raise ValueError (n)
    else:
        buffer[offset+0] = (n >> 24) & 0xff
        buffer[offset+1] = (n >> 16) & 0xff
        buffer[offset+2] = (n >>  8) & 0xff
        buffer[offset+3] = (n >>  0) & 0xff

cdef uint32_t unpack_uint32 (unsigned char * data, int offset):
    return (  (data[offset+0] << 24)
            | (data[offset+1] << 16)
            | (data[offset+2] << 8)
            | (data[offset+3] << 0)
            )

cdef uint16_t unpack_uint16 (unsigned char * data, int offset):
    return (data[offset+0] << 8) | (data[offset+1] << 0)

def unpack_control_frame (bytes head):
    cdef uint32_t vertype  = unpack_uint32 (<unsigned char *> head, 0)
    cdef uint32_t flagslen = unpack_uint32 (<unsigned char *> head, 4)
    cdef int fversion = (vertype >> 16) & 0x7fff
    cdef int ftype    = vertype & 0xffff
    cdef int flags    = flagslen >> 24
    cdef int length   = flagslen & 0x00FFFFFF
    return fversion, ftype, flags, length

def unpack_data_frame (bytes head):
    cdef uint32_t stream_id = unpack_uint32 (<unsigned char *>head, 0)
    cdef uint32_t flagslen  = unpack_uint32 (<unsigned char *>head, 4)
    cdef int flags = flagslen >> 24
    cdef int length = flagslen & 0x00FFFFFF
    return stream_id, flags, length

def pack_control_frame (unsigned char version, int ftype, int flags, bytes data):
    cdef int length = len (data)
    cdef bytes result = PyBytes_FromStringAndSize (NULL, length + 8)
    cdef unsigned char * rp = result
    pack16 (0x8000 | version, rp, 0)
    pack16 (ftype, rp, 2)
    rp[4] = flags & 0xff
    pack24 (length, rp, 5)
    memcpy (rp + 8, <void*>(<char *>data), length)
    return result

def pack_data_frame (unsigned char version, int stream_id, int flags, bytes data):
    cdef int length = len (data)
    cdef bytes result = PyBytes_FromStringAndSize (NULL, length + 8)
    cdef unsigned char * rp = result
    # stream_id is actually 31 bits
    assert stream_id < 0x80000000
    pack32 (stream_id, rp, 0)
    rp[4] = flags & 0xff
    pack24 (length, rp, 5)
    memcpy (rp + 8, <void*>(<char *>data), length)
    return result

class TooManyHeaders (Exception):
    pass

def pack_http_header (dict headers):
    cdef int offset = 0
    cdef int l = 0
    cdef bytes h, v
    cdef unsigned char buffer[4000]
    pack32 (len (headers), buffer, 0)
    offset += 4
    for h, vs in headers.iteritems():
        l = len(h)
        if offset + 4 + l >= 4000:
            raise TooManyHeaders (headers)
        pack32 (l, buffer, offset)
        offset += 4
        memcpy (buffer + offset, <void*>(<char*>h), l)
        offset += l
        # calculate size
        l = 0
        for v in vs:
            l += len(v) + 1
        # no trailing NUL
        l -= 1
        if offset + 4 + l >= 4000:
            raise TooManyHeaders (headers)
        pack32 (l, buffer, offset)
        offset += 4
        for v in vs:
            l = len(v)
            memcpy (buffer + offset, <void*>(<char*>v), l)
            offset += l
            buffer[offset] = 0
            offset += 1
        # no trailing NUL
        offset -= 1
    return buffer[:offset]

def unpack_http_header (bytes data):
    cdef dict result = {}
    cdef int n = unpack_uint32 (data, 0)
    cdef int pos = 4, nlen=0, vlen=0
    cdef bytes name, val
    for i in range (n):
        nlen = unpack_uint32 (data, pos)
        pos += 4
        name = data[pos:pos+nlen]
        pos += nlen
        vlen = unpack_uint32 (data, pos)
        pos += 4
        val = data[pos:pos+vlen]
        pos += vlen
        result[name] = val.split ('\x00')
    return result
