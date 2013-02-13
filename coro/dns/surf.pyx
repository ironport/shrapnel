# -*- Mode: Cython -*-

from libc.stdint cimport uint32_t, uint8_t

# cython translation of Eric Huss' version of djb's dns_random.c

# crummy emulation of the C macros
cdef inline uint32_t ROTATE (uint32_t x, uint32_t b):
    return (((x) << (b)) | ((x) >> (32 - (b))))

cdef inline void MUSH (uint32_t i, uint32_t b, uint32_t *x, uint32_t *t, uint32_t s):
    t[i] += (((x[0] ^ seed[i]) + s) ^ ROTATE (x[0], b))
    x[0] = t[i]

cdef uint32_t seed[32]
cdef uint32_t iin[12]
cdef uint32_t out[8]
cdef int outleft = 0

#
#  Simple Unpredictable Random Function
#
cdef surf():
    cdef uint32_t t[12], x, sum = 0
    cdef int r, i, loop
    for i in range (12):
        t[i] = iin[i] ^ seed[12 + i]
    for i in range (8):
        out[i] = seed[24 + i]
    x = t[11]
    for loop in range (2):
        for r in range (16):
            sum += 0x9e3779b9U
            MUSH(0,5,&x,t,sum)
            MUSH(1,7,&x,t,sum)
            MUSH(2,9,&x,t,sum)
            MUSH(3,13,&x,t,sum)
            MUSH(4,5,&x,t,sum)
            MUSH(5,7,&x,t,sum)
            MUSH(6,9,&x,t,sum)
            MUSH(7,13,&x,t,sum)
            MUSH(8,5,&x,t,sum)
            MUSH(9,7,&x,t,sum)
            MUSH(10,9,&x,t,sum)
            MUSH(11,13,&x,t,sum)
        for i in range (8):
            out[i] ^= t[i+4]

from cython.operator cimport preincrement as incr, predecrement as decr

#cython: cdivision=True
def dns_random (uint32_t n):
    "return an unpredictable random number in the range 0-n"
    global outleft
    if not n:
        return 0
    elif not outleft:
        if not incr (iin[0]):
            if not incr (iin[1]):
                if not incr (iin[2]):
                    incr(iin[3])
        surf()
        outleft = 8
    return <int> (out[decr(outleft)] % n)

def set_seed (bytes b not None):
    "set the initial seed for the SURF PRNG"
    cdef int i
    cdef uint8_t * p
    p = <uint8_t *> (&seed[0])
    cdef unsigned char * x = b
    for i in range (min (len (b), sizeof(seed))):
        p[i] = <uint8_t> x[i]
