# -*- Mode: Cython -*-

from libc.stdint cimport uint64_t

cdef extern from "sodium.h" nogil:

    int sodium_init()

    ctypedef struct crypto_hash_sha256_state:
        pass ## opaque

    int crypto_hash_sha256_init (
        crypto_hash_sha256_state *state
    )
    int crypto_hash_sha256_update (
        crypto_hash_sha256_state *state,
        const unsigned char *_in,
        unsigned long long inlen
    )

    int crypto_hash_sha256_final (
        crypto_hash_sha256_state *state,
        unsigned char *out
    )

    ctypedef struct crypto_hash_sha512_state:
        pass ## opaque

    int crypto_hash_sha512_init (
        crypto_hash_sha512_state *state
    )
    int crypto_hash_sha512_update (
        crypto_hash_sha512_state *state,
        const unsigned char *_in,
        unsigned long long inlen
    )

    int crypto_hash_sha512_final (
        crypto_hash_sha512_state *state,
        unsigned char *out
    )

    int crypto_scalarmult_curve25519 (
        unsigned char *q,
        const unsigned char *n,
        const unsigned char *p
    )

    int crypto_scalarmult_curve25519_base (
        unsigned char *q,
        const unsigned char *n
    )

    int crypto_sign_ed25519_detached (
        unsigned char *sig,
        unsigned long long *siglen_p,
        const unsigned char *m,
        unsigned long long mlen,
        const unsigned char *sk
    )

    int crypto_sign_ed25519_verify_detached (
        const unsigned char *sig,
        const unsigned char *m,
        unsigned long long mlen,
        const unsigned char *pk
    )

    int crypto_stream_chacha20 (
        unsigned char *c,
        unsigned long long clen,
        const unsigned char *n,
        const unsigned char *k
    )

    int crypto_stream_chacha20_xor_ic (
        unsigned char *c,
        const unsigned char *m,
        unsigned long long mlen,
        const unsigned char *n,
        uint64_t ic,
        const unsigned char *k
    )

    int crypto_onetimeauth_poly1305 (
        unsigned char *out,
        const unsigned char *_in,
        unsigned long long inlen,
        const unsigned char *k
    )

    int crypto_onetimeauth_poly1305_verify (
        const unsigned char *h,
        const unsigned char *_in,
        unsigned long long inlen,
        const unsigned char *k
    )

    int crypto_aead_chacha20poly1305_ietf_encrypt_detached (
        unsigned char *c,
        unsigned char *mac,
        unsigned long long *maclen_p,
        const unsigned char *m,
        unsigned long long mlen,
        const unsigned char *ad,
        unsigned long long adlen,
        const unsigned char *nsec,
        const unsigned char *npub,
        const unsigned char *k
    )

    int crypto_aead_chacha20poly1305_ietf_decrypt_detached (
        unsigned char *m,
        unsigned char *nsec,
        const unsigned char *c,
        unsigned long long clen,
        const unsigned char *mac,
        const unsigned char *ad,
        unsigned long long adlen,
        const unsigned char *npub,
        const unsigned char *k
    )

    void crypto_aead_chacha20poly1305_ietf_keygen (unsigned char * k)

    int crypto_aead_aes256gcm_encrypt_detached (
        unsigned char *c,
        unsigned char *mac,
        unsigned long long *maclen_p,
        const unsigned char *m,
        unsigned long long mlen,
        const unsigned char *ad,
        unsigned long long adlen,
        const unsigned char *nsec,
        const unsigned char *npub,
        const unsigned char *k
    )

    int crypto_aead_aes256gcm_decrypt_detached (
        unsigned char *m,
        unsigned char *nsec,
        const unsigned char *c,
        unsigned long long clen,
        const unsigned char *mac,
        const unsigned char *ad,
        unsigned long long adlen,
        const unsigned char *npub,
        const unsigned char *k
    )

    void __randombytes "randombytes" (
        unsigned char * const buf,
        const unsigned long long buf_len
    )


# ----- hashing -----

cdef class SHA256:

    cdef crypto_hash_sha256_state _state

    def __init__ (self):
        if 0 != crypto_hash_sha256_init (&self._state):
            raise ValueError ("sha256_init failed")

    def update (self, bytes data):
        crypto_hash_sha256_update (&self._state, data, len(data))

    def digest (self):
        r = bytearray (32)
        crypto_hash_sha256_final (&self._state, r)
        return bytes(r)

def sha256 (s):
    h = SHA256()
    h.update (s)
    return h.digest()

cdef class SHA512:

    cdef crypto_hash_sha512_state _state

    def __init__ (self):
        if 0 != crypto_hash_sha512_init (&self._state):
            raise ValueError ("sha512_init failed")

    def update (self, bytes data):
        crypto_hash_sha512_update (&self._state, data, len(data))

    def digest (self):
        r = bytearray (64)
        crypto_hash_sha512_final (&self._state, r)
        return bytes(r)

def sha512 (s):
    h = SHA512()
    h.update (s)
    return h.digest()

# ----- ECDH -----
def x25519_gen_key (bytes sk):
    if len(sk) != 32:
        raise ValueError ("secret key must be 32 bytes")
    else:
        pk = bytearray(32)
        if 0 != crypto_scalarmult_curve25519_base (pk, sk):
            raise ValueError ("curve25519: failed to generate key")
        else:
            return sk, bytes(pk)

def x25519 (bytes sk, bytes pk):
    if len(sk) != 32:
        raise ValueError ("secret key must be 32 bytes")
    if len(pk) != 32:
        raise ValueError ("public key must be 32 bytes")
    result = bytearray(32)
    if 0 != crypto_scalarmult_curve25519 (result, sk, pk):
        raise ValueError ("curve25519: scalarmult failed.")
    return bytes(result)

# ----- Ed25519 -----

def ed25519_sign (bytes m, bytes k):
    sig = bytearray (64)
    if len(k) != 64:
        raise ValueError ("key must be 64 bytes")
    elif 0 != crypto_sign_ed25519_detached (sig, NULL, m, len(m), k):
        raise ValueError ("ed25519_sign failed")
    else:
        return bytes(sig)

def ed25519_verify (bytes m, bytes sig, bytes pk):
    if len(pk) != 32:
        raise ValueError ("public key must be 32 bytes")
    elif 0 != crypto_sign_ed25519_verify_detached (sig, m, len(m), pk):
        raise ValueError ("ed25519_verify failed")
    else:
        return True

# ----- ChaCha20 -----

def chacha20 (bytes key, bytes data, bytes nonce, unsigned long long ctr):
    dlen = len(data)
    result = bytearray (dlen)
    # XXX assert len(nonce) == 8
    if 0 != crypto_stream_chacha20_xor_ic (result, data, dlen, nonce, ctr, key):
        raise ValueError ("crypto_stream_chacha20_xor_ic failed")
    else:
        return bytes(result)

# ----- Poly1305 -----

# XXX this is probably poly1305_init?
def poly1305_key (bytes key, bytes nonce):
    result = bytearray (32)
    if len(nonce) != 8:
        raise ValueError ("nonce must be 8 bytes")
    elif len(key) != 32:
        raise ValueError ("key must be 32 bytes")
    elif 0 != crypto_stream_chacha20 (result, 32, nonce, key):
        raise ValueError ("chacha20 failed")
    else:
        return bytes(result)

def poly1305 (bytes key, bytes data, bytes nonce):
    tag = bytearray (16)
    if len(key) != 32:
        raise ValueError ("key must be 32 bytes")
    elif len(nonce) != 8:
        raise ValueError ("nonce must be 8 bytes")
    elif 0 != crypto_onetimeauth_poly1305 (tag, data, len(data), poly1305_key (key, nonce)):
        raise ValueError ("poly1305 failed")
    else:
        return bytes(tag)

def poly1305_verify (bytes key, bytes data, bytes nonce, bytes tag):
    return 0 == crypto_onetimeauth_poly1305_verify (
        tag, data, len(data), poly1305_key (key, nonce)
    )

# ----- AEAD -----

def aead_chacha20poly1305_encrypt (bytes m, bytes k, bytes nonce, bytes ad):
    cdef unsigned long long maclen
    ct = bytearray (len(m))
    mac = bytearray (16)
    if 0 != crypto_aead_chacha20poly1305_ietf_encrypt_detached (
            ct,
            mac, &maclen,
            m, len(m),
            ad, len(ad),
            NULL,
            nonce,
            k
            ):
        raise ValueError ("chacha20poly1305 encrypt failed")
    else:
        return bytes(ct), bytes(mac[:maclen])

def aead_chacha20poly1305_decrypt (bytes c, bytes k, bytes nonce, bytes ad, bytes mac):
    m = bytearray (len(c))
    if 0 != crypto_aead_chacha20poly1305_ietf_decrypt_detached (
            m, NULL,
            c, len(c),
            mac,
            ad, len(ad),
            nonce,
            k
            ):
        raise ValueError ("chacha20poly1305 decrypt failed")
    else:
        return m

def aead_aes256gcm_encrypt (bytes m, bytes k, bytes nonce, bytes ad):
    cdef unsigned long long maclen
    mlen = len(m)
    c = bytearray (mlen)
    mac = bytearray (16)
    if len(k) != 32:
        raise ValueError ("key must be 32 bytes")
    elif len(nonce) != 12:
        raise ValueError ("nonce must be 12 bytes")
    elif 0 != crypto_aead_aes256gcm_encrypt_detached (
            c,
            mac, &maclen,
            m, mlen,
            ad, len(ad),
            NULL,
            nonce,
            k):
        raise ValueError ("aes256gcm_encrypt failed")
    else:
        return bytes(c), bytes(mac)[:maclen]

def aead_aes256gcm_decrypt (bytes c, bytes k, bytes nonce, bytes ad, bytes mac):
    clen = len(c)
    m = bytearray (clen)
    if len(k) != 32:
        raise ValueError ("key must be 32 bytes")
    elif len(nonce) != 12:
        raise ValueError ("nonce must be 12 bytes")
    elif len(mac) != 16:
        raise ValueError ("mac must be 16 bytes")
    elif 0 != crypto_aead_aes256gcm_decrypt_detached (
            m, NULL, c, clen, mac, ad, len(ad), nonce, k):
        raise ValueError ("aes256gcm_decrypt failed")
    else:
        return bytes(m)

# ----- random ----
def randombytes (unsigned long long n):
    r = bytearray (n)
    __randombytes (r, n)
    return bytes(r)


if 0 != sodium_init():
    raise ValueError ("sodium_init failed.")
