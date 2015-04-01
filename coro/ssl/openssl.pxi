# -*- Mode: Pyrex -*-
# Copyright (c) 2002-2012 IronPort Systems and Cisco Systems
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


# Pyrex declarations for openssl.
# By no means complete.
# If you need more stuff, add it.

cdef extern from "time.h":
    ctypedef struct time_t
    time_t time(time_t *)

cdef extern from "openssl/bn.h":
    ctypedef struct BIGNUM
    BIGNUM *BN_new ()
    void BN_free(BIGNUM *)
    char *BN_bn2dec(BIGNUM *)
    int BN_pseudo_rand(BIGNUM *, int, int, int)
    int BN_rand(BIGNUM *, int, int, int)

cdef extern from "openssl/crypto.h":
    void OPENSSL_free (void *)

cdef extern from "openssl/opensslv.h":
    char * OPENSSL_VERSION_TEXT

cdef extern from "openssl/err.h":
    unsigned long ERR_get_error()
    unsigned long ERR_peek_error()
    void ERR_clear_error()
    char * ERR_error_string (unsigned long, char *)
    void ERR_load_crypto_strings()

cdef extern from "openssl/ssl.h":
    # openssl uses a 'safestack', which uses code generation and
    #   macros to add some type safety to their stack API.  Getting
    #   that stuff declared correctly and using it from Pyrex is very
    #   difficult, compared to just using the stack api directly -
    #   but please take note of this and be careful.
    # Note: somewhere near 1.0 they renamed STACK to _STACK, the easiest
    #  way around that is to use 'struct stack_st' instead, the name of
    #  which was not changed.
    cdef struct stack_st
    int sk_num (stack_st *)
    void * sk_value (stack_st *, int)
    void sk_pop_free (stack_st *, void (*)(void *))
    int sk_push(stack_st *, char *)
    char *sk_pop(stack_st *)
    stack_st *sk_new_null ()
    void sk_free (stack_st *)

cdef extern from "openssl/bio.h":
    ctypedef struct BIO
    ctypedef struct BIO_METHOD
    BIO_METHOD  *BIO_s_mem()
    BIO * BIO_new          (BIO_METHOD *type)
    BIO * BIO_new_file     (char *, char *)
    BIO * BIO_new_mem_buf  (void *buf, int len)
    long  BIO_get_mem_data (BIO *b, char **pp)
    int   BIO_flush        (BIO *b)
    int   BIO_free         (BIO *a)
    int   BIO_puts         (BIO *bp, char *buf)
    int   BIO_read         (BIO *b, void *buf, int len)
    int   BIO_write        (BIO *b, void *buf, int len)
    void  BIO_free_all     (BIO *a)
    void  BIO_set_flags    (BIO *b, int f)

cdef extern from "openssl/asn1.h":
    int MBSTRING_ASC
    ctypedef struct BIO
    ctypedef struct ASN1_STRING
    ctypedef struct ASN1_OBJECT
    ctypedef struct ASN1_INTEGER
    ctypedef struct ASN1_TIME
    ASN1_INTEGER *ASN1_INTEGER_new()
    void ASN1_INTEGER_free(ASN1_INTEGER *)
    int ASN1_STRING_to_UTF8 (unsigned char **, ASN1_STRING *)
    long ASN1_INTEGER_get (ASN1_INTEGER *)
    int ASN1_INTEGER_set(ASN1_INTEGER *, long)
    int ASN1_TIME_print (BIO *, ASN1_TIME *)
    ASN1_TIME *ASN1_TIME_set(ASN1_TIME *,time_t)
    ASN1_INTEGER *BN_to_ASN1_INTEGER(BIGNUM *, ASN1_INTEGER *)
    int i2a_ASN1_INTEGER(BIO *, ASN1_INTEGER *)

cdef extern from "openssl/dh.h":
    ctypedef struct DH
    void DH_free (DH *)

cdef extern from "openssl/rsa.h":
    ctypedef struct RSA
    RSA * RSA_generate_key (int num, unsigned long e, void (*callback)(int,int,void *), void *cb_arg)
    RSA * RSA_new()
    void RSA_free (RSA * r)
    int RSA_size (RSA *)
    int RSA_check_key (RSA *)

cdef extern from "openssl/evp.h":
    ctypedef struct EVP_PKEY
    ctypedef struct EVP_CIPHER
    ctypedef struct EVP_CIPHER_CTX:
        # for some reason pyrex won't just let me declare the struct's existence.
        int nid
        int block_size
        int key_len
        int iv_len
        unsigned long flags
    ctypedef struct EVP_MD
    ctypedef struct EVP_MD_CTX:
        # same as above
        unsigned long flags
    EVP_MD *EVP_sha256()
    EVP_MD *EVP_sha512()
    EVP_PKEY * EVP_PKEY_new()
    void EVP_PKEY_free (EVP_PKEY *)
    int  EVP_PKEY_bits (EVP_PKEY *)
    int  EVP_PKEY_size (EVP_PKEY *)
    int  EVP_PKEY_set1_RSA (EVP_PKEY *, RSA *)
    void EVP_CIPHER_free (EVP_CIPHER *)
    EVP_CIPHER * EVP_get_cipherbyname (char *)
    EVP_MD * EVP_get_digestbyname (char *)
    void EVP_CIPHER_CTX_init           (EVP_CIPHER_CTX *)
    void EVP_MD_CTX_init               (EVP_MD_CTX *)
    int  EVP_CIPHER_CTX_set_key_length (EVP_CIPHER_CTX *, int)
    int  EVP_CIPHER_CTX_key_length     (EVP_CIPHER_CTX *)
    int  EVP_CIPHER_CTX_iv_length      (EVP_CIPHER_CTX *)
    int  EVP_CIPHER_CTX_cleanup        (EVP_CIPHER_CTX *)
    int  EVP_MD_CTX_cleanup            (EVP_MD_CTX *)
    int  EVP_CipherInit_ex             (EVP_CIPHER_CTX *, EVP_CIPHER *, void *, char *, char *, int)
    int  EVP_DigestInit_ex             (EVP_MD_CTX *, EVP_MD *, void *)
    int  EVP_CipherUpdate              (EVP_CIPHER_CTX *, char *, int *, char *, int)
    int  EVP_DigestUpdate              (EVP_MD_CTX *, void *, size_t)
    int  EVP_CIPHER_CTX_block_size     (EVP_CIPHER_CTX *)
    int  EVP_CipherFinal_ex            (EVP_CIPHER_CTX *, char *, int *)
    int  EVP_DigestFinal_ex            (EVP_MD_CTX *, char *, int *)
    int  EVP_SignFinal                 (EVP_MD_CTX *, char *, int *, EVP_PKEY *)
    int  EVP_VerifyFinal               (EVP_MD_CTX *, char *, int, EVP_PKEY *)
    int EVP_MAX_MD_SIZE
    # --- public key encryption ---
    ctypedef struct EVP_PKEY_CTX
    # NOTE: replacing ENGINE * with void * here, we otherwise have no support for ENGINE.
    EVP_PKEY_CTX * EVP_PKEY_CTX_new (EVP_PKEY *, void *)
    void EVP_PKEY_CTX_free (EVP_PKEY_CTX *)
    int  EVP_PKEY_encrypt_init         (EVP_PKEY_CTX *)
    int  EVP_PKEY_encrypt              (EVP_PKEY_CTX *, unsigned char *, size_t *, const unsigned char *, size_t)

cdef extern from "openssl/ec.h":
    ctypedef struct EC_KEY
    ctypedef struct EC_POINT
    EC_KEY * EC_KEY_new                  ()
    EC_KEY * EC_KEY_new_by_curve_name    (int)
    int      EC_KEY_generate_key         (EC_KEY *)
    void     EC_KEY_free                 (EC_KEY *)
    EC_KEY * d2i_ECPrivateKey            (EC_KEY **, const unsigned char **, long)
    EC_KEY * o2i_ECPublicKey             (EC_KEY **, const unsigned char **, long)
    int      i2d_ECPrivateKey            (EC_KEY *, unsigned char **)
    int      i2o_ECPublicKey             (EC_KEY *, unsigned char **)
    ctypedef enum point_conversion_form_t:
        POINT_CONVERSION_COMPRESSED
        POINT_CONVERSION_UNCOMPRESSED
        POINT_CONVERSION_HYBRID
    void     EC_KEY_set_conv_form        (EC_KEY *, point_conversion_form_t)

cdef extern from "openssl/ecdsa.h":
    int ECDSA_size (const EC_KEY * eckey)
    int ECDSA_sign (
        int type, const unsigned char *dgst, int dgstlen,
        unsigned char *sig, unsigned int *siglen, EC_KEY *eckey
    )
    int ECDSA_verify (
        int type, const unsigned char *dgst, int dgstlen,
        const unsigned char *sig, int siglen, EC_KEY *eckey
    )

cdef extern from "openssl/x509.h":
    ctypedef struct X509
    X509 *X509_new ()
    void X509_free (X509 *)
    X509 * X509_dup (X509 *)
    ctypedef struct X509_STORE
    ctypedef struct X509_STORE_CTX
    ctypedef struct X509_LOOKUP
    ctypedef struct X509_LOOKUP_METHOD
    X509_LOOKUP_METHOD * X509_LOOKUP_file()
    X509_LOOKUP *        X509_STORE_add_lookup     (X509_STORE *, X509_LOOKUP_METHOD *)
    int                  X509_load_crl_file        (X509_LOOKUP *, char *, int)
    void                 X509_STORE_set_flags      (X509_STORE *, long)
    int                  X509_STORE_set_purpose    (X509_STORE *, int)
    int                  X509_STORE_set_trust      (X509_STORE *, int)
    X509_STORE_CTX *     X509_STORE_CTX_new()
    char *               X509_verify_cert_error_string (long)
    long                 X509_get_version(X509 *)
    int                  X509_set_version(X509 *, long)
    ASN1_INTEGER *       X509_get_serialNumber(X509 *)
    int                  X509_set_serialNumber(X509 *, ASN1_INTEGER *)
    ASN1_TIME *          X509_get_notBefore(X509 *)
    ASN1_TIME *          X509_get_notAfter(X509 *)
    int X509_print_ex(BIO *bp,X509 *x, unsigned long nmflag, unsigned long cflag)
    int X509_FILETYPE_PEM, X509_V_FLAG_CRL_CHECK, X509_V_FLAG_CRL_CHECK_ALL
    int X509_set_pubkey (X509 *, EVP_PKEY *)
    int X509_sign(X509 *, EVP_PKEY *, EVP_MD *)
    int X509_cmp_current_time(ASN1_TIME *)
    ASN1_TIME * X509_gmtime_adj(ASN1_TIME *, long)

    ctypedef struct X509_NAME
    X509_NAME * X509_get_issuer_name(X509 *)
    X509_NAME * X509_get_subject_name(X509 *)
    int X509_NAME_entry_count(X509_NAME *)
    int X509_NAME_add_entry_by_txt (X509_NAME *, char *, int, char *, int, int, int)
    unsigned long XN_FLAG_SEP_MULTILINE
    unsigned long XN_FLAG_SEP_COMMA_PLUS
    int X509_NAME_print_ex(BIO *, X509_NAME *, int, unsigned long)

    ctypedef struct X509_NAME_ENTRY
    X509_NAME_ENTRY *X509_NAME_get_entry(X509_NAME *, int)
    ASN1_OBJECT *X509_NAME_ENTRY_get_object(X509_NAME_ENTRY *)
    ASN1_STRING *X509_NAME_ENTRY_get_data(X509_NAME_ENTRY *)
    int X509_NAME_get_index_by_NID (X509_NAME *, int, int)

    ctypedef struct X509_REQ_INFO
    ctypedef struct X509_REQ
    X509_REQ *X509_REQ_new ()
    void X509_REQ_free (X509_REQ *)
    EVP_PKEY * X509_REQ_get_pubkey(X509_REQ *)
    X509_NAME *X509_REQ_get_subject_name(X509_REQ *)
    int X509_REQ_set_pubkey (X509_REQ *, EVP_PKEY *)
    int X509_REQ_print(BIO *, X509_REQ *)
    int X509_REQ_sign(X509_REQ *, EVP_PKEY *, EVP_MD *)

    X509_REQ * X509_to_X509_REQ(X509 *, EVP_PKEY *, EVP_MD *)
    X509 * X509_REQ_to_X509(X509_REQ *, int, EVP_PKEY *)

cdef extern from "openssl/pem.h":
    int        PEM_write_bio_X509      (BIO *bp, X509 *x)
    X509 *     PEM_read_bio_X509       (BIO *bp, X509 **x, void *cb, void *u)
    # XXX check type of final param of these next two, void* or char*?
    EVP_PKEY * PEM_read_bio_PrivateKey (BIO *bp, EVP_PKEY **x, void *cb, char *u)
    RSA *      PEM_read_bio_RSAPrivateKey(BIO *bp, EVP_PKEY **x, void *cb, char *u)
    EVP_PKEY * PEM_read_bio_PUBKEY     (BIO *bp, EVP_PKEY **x, void *cb, char *u)
    int        PEM_write_bio_PUBKEY    (BIO *bp, EVP_PKEY *x)
    int        PEM_write_bio_PrivateKey(BIO *bp, EVP_PKEY *x, EVP_CIPHER *enc, char *kstr, int klen,void *cb, void *u)
    DH *       PEM_read_bio_DHparams   (BIO *bp, DH **x, void *cb, void *u)
    int        PEM_write_bio_RSAPrivateKey (BIO *bp, RSA *x, EVP_CIPHER *enc, char * kstr, int klen, void *cb, void *u)
    int        PEM_write_bio_RSAPublicKey (BIO *bp, RSA *x)
    X509_REQ * PEM_read_bio_X509_REQ(BIO *bp, X509_REQ *x, void *cb, char *u)
    int        PEM_write_bio_X509_REQ (BIO *bp, X509_REQ *x)

cdef extern from "openssl/ssl.h":
    ctypedef struct SSL
    ctypedef struct SSL_CTX
    ctypedef struct SSL_METHOD
    void SSL_CTX_free                   (SSL_CTX *)
    SSL_CTX * SSL_CTX_new               (SSL_METHOD *)
    SSL * SSL_new                       (SSL_CTX *)
    void SSL_free                       (SSL *)
    SSL_METHOD * SSLv23_method          ()
    int SSL_use_certificate             (SSL *, X509 *)
    int SSL_CTX_use_certificate         (SSL_CTX *, X509 *)
    int SSL_CTX_add_extra_chain_cert    (SSL_CTX *, X509 *)
    int SSL_CTX_use_PrivateKey          (SSL_CTX *, EVP_PKEY *)
    int SSL_use_PrivateKey              (SSL *, EVP_PKEY *)
    int SSL_CTX_set_cipher_list         (SSL_CTX *, char *)
    int SSL_set_cipher_list             (SSL *, char *)
    long SSL_CTX_set_tmp_dh             (SSL_CTX *, DH *)
    long SSL_set_tmp_dh                 (SSL *, DH *)
    void SSL_CTX_set_verify             (SSL_CTX *, int, void *)
    void SSL_set_verify                 (SSL *, int, void *)
    int SSL_CTX_check_private_key       (SSL_CTX *)
    int SSL_check_private_key           (SSL *)
    int SSL_CTX_load_verify_locations   (SSL_CTX *, char *, char *)

    IF NPN:
        # next protocol ('NPN') support
        void SSL_CTX_set_next_protos_advertised_cb (
            SSL_CTX *,
            int (*cb) (
                SSL *,
                unsigned char **,
                unsigned int *,
                void *
                ),
            void *
            )
        void SSL_get0_next_proto_negotiated (SSL *, unsigned char **, unsigned *)
        void SSL_CTX_set_next_proto_select_cb (
            SSL_CTX *,
            int (*cb) (
                SSL *,
                unsigned char **,
                unsigned char *,
                unsigned char *,
                unsigned int,
                void *
                ),
            void *
            )
        int SSL_select_next_proto (
            unsigned char **, unsigned char *,
            unsigned char *, unsigned int,
            unsigned char *, unsigned int
            )

    X509_STORE * SSL_CTX_get_cert_store (SSL_CTX *)
    int X509_STORE_CTX_init             (X509_STORE_CTX *, X509_STORE *, X509 *, void *)
    void X509_STORE_CTX_free            (X509_STORE_CTX *)
    int X509_verify_cert                (X509_STORE_CTX *)
    long SSL_CTX_get_options            (SSL_CTX *)
    long SSL_CTX_set_options            (SSL_CTX *, long)
    long SSL_get_options                (SSL *)
    long SSL_set_options                (SSL *, long)
    char * SSL_get_cipher_list          (SSL *, int)
    char * SSL_get_cipher               (SSL *)
    void SSL_set_connect_state          (SSL *)
    void SSL_set_accept_state           (SSL *)
    int SSL_set_fd                      (SSL *, int)
    X509 * SSL_get_peer_certificate     (SSL *)
    stack_st * SSL_get_peer_cert_chain     (SSL *)
    int SSL_accept                      (SSL *)
    int SSL_connect                     (SSL *)
    int SSL_read                        (SSL *, void *, int)
    int SSL_write                       (SSL *, void *, int)
    int SSL_shutdown                    (SSL *)
    long SSL_get_verify_result          (SSL *)
    int SSL_get_error                   (SSL *, int)

    void OpenSSL_add_all_algorithms()
    void OpenSSL_add_all_ciphers()
    void OpenSSL_add_all_digests()
    int  OpenSSL_add_ssl_algorithms()
    void SSL_load_error_strings()

    int SSL_OP_ALL, SSL_OP_NO_SSLv2, SSL_OP_NO_SSLv3, SSL_OP_NO_TLSv1
    int SSL_OP_SINGLE_DH_USE
    int SSL_ERROR_SYSCALL, SSL_ERROR_WANT_READ, SSL_ERROR_WANT_WRITE, SSL_ERROR_SSL, SSL_ERROR_ZERO_RETURN
    int SSL_VERIFY_NONE, SSL_VERIFY_PEER, SSL_VERIFY_FAIL_IF_NO_PEER_CERT, SSL_VERIFY_CLIENT_ONCE
    int SSL_TLSEXT_ERR_OK

cdef extern from "openssl/rand.h":
    int RAND_bytes (char *, int)
    int RAND_status()

cdef extern from "openssl/objects.h":
    ctypedef struct OBJ_NAME:
        int type
        int alias
        char *name
        char *data
    char *SN_commonName
    char *SN_countryName
    char *SN_localityName
    char *SN_stateOrProvinceName
    char *SN_organizationName
    char *SN_organizationalUnitName
    int NID_commonName
    int NID_countryName
    int NID_localityName
    int NID_stateOrProvinceName
    int NID_organizationName
    int NID_organizationalUnitName
    char *SN_sha1

    void OBJ_NAME_do_all_sorted (int, void (*)(OBJ_NAME *,void *), void *)
    int OBJ_NAME_TYPE_CIPHER_METH
    int OBJ_obj2nid (ASN1_OBJECT *)
    char *OBJ_nid2sn (int)
    char *OBJ_nid2ln (int)
    int OBJ_sn2nid (char *)

cdef extern from "openssl/pkcs12.h":
    ctypedef struct PKCS12
    void PKCS12_free (PKCS12 *)
    PKCS12 * d2i_PKCS12_bio (BIO *, PKCS12 **)
    int i2d_PKCS12_bio (BIO *, PKCS12 *)
    int PKCS12_parse (PKCS12 *, char *, EVP_PKEY **, X509 **, stack_st **)
    PKCS12 * PKCS12_create (char *, char *, EVP_PKEY *, X509 *, stack_st *, int, int, int, int, int)
    int PKCS12_newpass(PKCS12 *, char *, char *)
