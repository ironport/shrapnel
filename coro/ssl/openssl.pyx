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

# -*- Mode: Cython; indent-tabs-mode: nil -*-

from libc.errno cimport errno

from cpython.exc cimport PyErr_SetFromErrno
from cpython.bytes cimport PyBytes_FromStringAndSize, PyBytes_FromString

cimport cpython.string

include "openssl.pxi"

# ================================================================================

class Error (Exception):
    pass

class WantRead (Exception):
    pass

class WantWrite (Exception):
    pass

class UnknownCipherType (Exception):
    pass

class UnknownDigestType (Exception):
    pass

cdef raise_ssl_error():
    cdef int error
    error = ERR_get_error()
    if error == SSL_ERROR_SYSCALL:
        PyErr_SetFromErrno (OSError)
    else:
        error_string = ERR_error_string (error, NULL)
        ERR_clear_error()
        raise Error (error, error_string)

# ================================================================================

cdef class mem_bio:

    cdef BIO * bio

    def __dealloc__ (self):
        if self.bio is not NULL:
            BIO_free (self.bio)

    def __init__ (self, bytes value=None):
        if value is None:
            self.bio = BIO_new (BIO_s_mem())
        else:
            self.bio = BIO_new_mem_buf (<void*>(<char*>value), len(value))
        if self.bio is NULL:
            raise_ssl_error()

    def as_string (self):
        cdef int size
        cdef char * data
        size = BIO_get_mem_data (self.bio, &data)
        return data[:size]

# ================================================================================

# This is useful for generating fresh RSA keys

cdef class rsa:

    cdef RSA * rsa

    def __dealloc__ (self):
        if self.rsa is not NULL:
            RSA_free (self.rsa)

    def __init__ (self, value, unsigned long e=65537, password=''):
        cdef mem_bio mb
        cdef int bits
        cdef char *pem
        if type(value) is int:
            bits = value
            if e < 3 or ((e % 2) != 1):
                # bad things will happen otherwise (e.g., call will hang)
                raise ValueError, "exponent must be an odd number greater than 1"
            else:
                self.rsa = RSA_generate_key (bits, e, NULL, NULL)
        elif type(value) is str:
            pem = value
            mb = mem_bio (pem)
            self.rsa = PEM_read_bio_RSAPrivateKey (mb.bio, NULL, NULL, password)

        else:
            self.rsa = NULL

    def check (self):
        cdef int result
        result = RSA_check_key (self.rsa)
        if result == 1:
            return True
        elif result == 0:
            return False
        else:
            raise_ssl_error()

    def as_pem (self):
        cdef mem_bio buf
        if self.rsa is not NULL:
            buf = mem_bio()
            PEM_write_bio_RSAPrivateKey(buf.bio, self.rsa, NULL, NULL, 0, NULL, NULL)
            return buf.as_string()
        else:
            raise Error ("NULL rsa object")

# ================================================================================

cdef class pkey:

    cdef EVP_PKEY * pkey

    def __dealloc__ (self):
        if self.pkey is not NULL:
            EVP_PKEY_free (self.pkey)

    def __init__ (self, ob=None, password='', private=False):
        cdef mem_bio mb
        cdef rsa r
        if type(ob) is rsa:
            # ob is a freshly-generated RSA key.
            r = ob
            self.pkey = EVP_PKEY_new()
            if self.pkey is NULL:
                raise_ssl_error()
            else:
                # XXX or do we want 'assign' here?
                EVP_PKEY_set1_RSA (self.pkey, r.rsa)
        elif ob is not None:
            # ob is a PEM string
            mb = mem_bio (ob)
            if private:
                self.pkey = PEM_read_bio_PrivateKey (mb.bio, NULL, NULL, password)
            else:
                self.pkey = PEM_read_bio_PUBKEY (mb.bio, NULL, NULL, NULL)
            if self.pkey is NULL:
                raise_ssl_error()
        else:
            self.pkey = NULL

    def get_private (self):
        cdef mem_bio buf
        buf = mem_bio()
        PEM_write_bio_PrivateKey (buf.bio, self.pkey, NULL, NULL, 0, NULL, NULL)
        return buf.as_string()

    def get_public (self):
        cdef mem_bio buf
        buf = mem_bio()
        PEM_write_bio_PUBKEY (buf.bio, self.pkey)
        return buf.as_string()

    cdef int _bits (self):
        return EVP_PKEY_bits (self.pkey)

    cdef int _size (self):
        return EVP_PKEY_size (self.pkey)

    def size (self):
        return self._size()

    def bits (self):
        return self._bits()

    def encrypt (self, bytes iblock):
        cdef size_t outlen = 0
        cdef bytes oblock
        # NOTE: no engine support yet...
        cdef EVP_PKEY_CTX * ctx = EVP_PKEY_CTX_new (self.pkey, NULL)
        if ctx is NULL:
            raise_ssl_error()
        else:
            try:
                if EVP_PKEY_encrypt_init (ctx) != 1:
                    raise_ssl_error()
                else:
                    if EVP_PKEY_encrypt (ctx, NULL, &outlen, iblock, len(iblock)) != 1:
                        raise_ssl_error()
                    else:
                        oblock = PyBytes_FromStringAndSize (NULL, outlen)
                        if EVP_PKEY_encrypt (ctx, oblock, &outlen, iblock, len(iblock)) != 1:
                            raise_ssl_error()
                        else:
                            return oblock
            finally:
                EVP_PKEY_CTX_free (ctx)

# compatibility
def read_pem_key (pem, pwd):
    return pkey (pem, pwd, True)

# ================================================================================


cdef class asn1_integer:

    cdef ASN1_INTEGER *delegate
    cdef int __dealloc

    def __dealloc__ (self):
        if self.delegate is not NULL and self.__dealloc != 0:
            ASN1_INTEGER_free(self.delegate)

    def __init__ (self, value=None):
        self.__dealloc = 0
        if value is None:
            self.delegate = NULL
        else:
            self.delegate = ASN1_INTEGER_new()
            self.__dealloc = 1
            self.set(value)

    def get (self):
        """Translates the class to a long.

        :Return:
            long value.  If integer is too large
            to fit in a long, 0xffffffffL is return instead
        """
        if self.delegate is not NULL:
            return ASN1_INTEGER_get(self.delegate)

        return None

    def set (self, long value):
        if self.delegate is not NULL:
            return ASN1_INTEGER_set(self.delegate, value)

    def to_hex (self):
        cdef mem_bio buf
        if self.delegate is not NULL:
            buf = mem_bio()
            i2a_ASN1_INTEGER(buf.bio, self.delegate)
            return buf.as_string()
        return None

    def __str__ (self):
        return "asn1_integer{%r}" % (self.to_hex(),)

cdef class bignum:
    cdef BIGNUM *delegate

    def __dealloc__ (self):
        if self.delegate is not NULL:
            BN_free(self.delegate)

    def __init__ (self):
        self.delegate = BN_new()

    def to_asn1_integer(self):
        cdef asn1_integer integer
        integer = asn1_integer(0)
        BN_to_ASN1_INTEGER(self.delegate, integer.delegate)
        return integer

    def pseudo_rand (self):
        if BN_pseudo_rand(self.delegate, 64, 0, 0) == 0:
            raise_ssl_error()

    def rand (self):
        if BN_rand(self.delegate, 64, 0, 0) == 0:
            raise_ssl_error()

    def __str__ (self):
        return "bignum{%s}" % (BN_bn2dec(self.delegate),)

cdef class asn1_time:

    cdef ASN1_TIME *delegate

    def __init__ (self):
        self.delegate = NULL

    def to_string (self):
        cdef mem_bio buf

        if self.delegate is not NULL:
            buf = mem_bio()
            ASN1_TIME_print (buf.bio, self.delegate)
            return buf.as_string()

        return None

    def set_now (self):
        """Set the time to the current time

        :Return:
            True if successful.  False if an error occured
        """
        if self.delegate is not NULL:
            if ASN1_TIME_set(self.delegate, time(NULL)) != NULL:
                return True
        return False

    def gmtime_adj (self, long offset):
        """Adjust the time to the current time

        :Parameters:
            `offset`: Number of miliseconds to offset time

        :Return:
            True if successful.  False if an error occured
        """
        if self.delegate is not NULL:
            if X509_gmtime_adj(self.delegate, offset) != NULL:
                return True
        return False

    def cmp_current_time(self):
        """Compares the date with the current time

        :Return:
            Positive integer if current time is before than this time
            0 for an error
            Negative integer if current time is after this time
        """
        if self.delegate is not NULL:
            return X509_cmp_current_time(self.delegate);
        raise_ssl_error()

    def __str__ (self):
        return "asn1_time{%s}" % (self.to_string(),)

cdef class asn1_string:

    cdef ASN1_STRING *delegate

    def __init__ (self):
        self.delegate = NULL

    def to_UTF8 (self):
        cdef unsigned char *utf8

        value = None
        if self.delegate is not NULL:
            utf8 = NULL
            ASN1_STRING_to_UTF8(&utf8, self.delegate)
            if utf8 is not NULL:
                value = PyBytes_FromString(<char *>utf8)
                OPENSSL_free(utf8)

        return value

    def __str__ (self):
        return "asn1_string{%s}" % (self.to_UTF8(),)

cdef class asn1_object:

    cdef ASN1_OBJECT *delegate

    def __init__ (self):
        self.delegate = NULL

    def sn (self):
        """Returns the short name

        :Return:
            Short name
        """
        nid = self.nid()
        if nid:
            return OBJ_nid2sn(nid)
        return None

    def ln (self):
        """Returns the long name

        :Return:
            Long name
        """
        nid = self.nid()
        if nid:
            return OBJ_nid2ln(nid)
        return None

    def nid (self):
        """Returns the name identifier

        :Return:
            Name identifier
        """
        if self.delegate is not NULL:
            return OBJ_obj2nid(self.delegate)
        return None

    def __str__ (self):
        return "asn1_object{%s(%s)}" % (self.ln(), self.sn())

# ================================================================================

cdef class x509_name_entry:

    cdef X509_NAME_ENTRY *delegate

    def __init__ (self):
        self.delegate = NULL

    def get_object (self):
        cdef asn1_object obj
        if self.delegate is not NULL:
            obj = asn1_object()
            obj.delegate = X509_NAME_ENTRY_get_object(self.delegate)
            return obj
        return None

    def get_data (self):
        cdef asn1_string data
        if self.delegate is not NULL:
            data = asn1_string()
            data.delegate = X509_NAME_ENTRY_get_data(self.delegate)
            return data
        return None

cdef class x509_name:

    cdef X509_NAME *delegate

    def __init__ (self):
        self.delegate = NULL

    def entry_count (self):
        if self.delegate is not NULL:
            return X509_NAME_entry_count(self.delegate)
        return None

    def add_entry_by_txt (self, bytes field, int type, bytes bytes, int len=-1, int loc=-1, int set=0):
        if self.delegate is not NULL:
            return X509_NAME_add_entry_by_txt (self.delegate, field, type, bytes, len, loc, set)
        return None

    def get_entry (self, int i):
        cdef x509_name_entry entry
        if self.delegate is not NULL:
            entry = x509_name_entry()
            entry.delegate = X509_NAME_get_entry (self.delegate, i)
            return entry
        return None

    def add_entries_by_txt (self, fields):
        if self.delegate is not NULL:
            for field, bytes in fields.iteritems():
                if self.add_entry_by_txt (field, MBSTRING_ASC, bytes) == 0:
                    raise_ssl_error()

    def get_entries(self):
        """Retrieve a dictionary of the all the entries

        :Return:
            Dictionary of fields where key is the field name
            and the value is either a string or a list of strings
            to handle duplicates
        """
        entries = {}
        entry_count = self.entry_count()
        if entry_count:
            for i in range(entry_count):

                entry = self.get_entry(i)
                if entry:
                    key = entry.get_object()
                    value = entry.get_data()

                    try:
                        prev = entries[key]
                        if type(prev) is asn1_object:
                            entries[key] = [prev, value]
                        else:
                            entries[key].append(value)
                    except KeyError:
                        entries[key] = value
        return entries

    def print_ex (self, int indent, unsigned long flags):
        cdef mem_bio buf
        if self.delegate is not NULL:
            buf = mem_bio()
            X509_NAME_print_ex(buf.bio, self.delegate, indent, flags)
            return buf.as_string()
        return None

    def __str__ (self):
        return self.print_ex(0, XN_FLAG_SEP_COMMA_PLUS)

cdef class x509_req:

    cdef X509_REQ *delegate

    def __dealloc__ (self):
        if self.delegate is not NULL:
            X509_REQ_free (self.delegate)

    def __init__ (self, value=None, fields={}):
        cdef mem_bio mb

        if type(value) is str:
            mb = mem_bio(value)
            self.delegate = PEM_read_bio_X509_REQ (mb.bio, NULL, NULL, NULL)
            if self.delegate is NULL:
                raise_ssl_error()
        else:
            self.delegate = NULL

    def set_pubkey(self, pkey key):
        if self.delegate is not NULL:
            return X509_REQ_set_pubkey(self.delegate, key.pkey)
        return None

    def get_subject_name(self):
        cdef x509_name name
        if self.delegate is not NULL:
            name = x509_name()
            name.delegate = X509_REQ_get_subject_name(self.delegate)
            return name
        return None

    def get_pubkey (self):
        cdef pkey k
        if self.delegate is not NULL:
            k = pkey()
            k.pkey = X509_REQ_get_pubkey(self.delegate)
            return k
        return None

    def sign (self, pkey key, char *digest=SN_sha1):
        if (self.delegate is not NULL and
            not X509_REQ_sign(self.delegate, key.pkey, EVP_get_digestbyname(digest))):
            raise_ssl_error()

    def as_pem (self):
        cdef mem_bio buf
        if self.delegate is not NULL:
            buf = mem_bio()
            if PEM_write_bio_X509_REQ(buf.bio, self.delegate) == 0:
                raise_ssl_error()
            else:
                return buf.as_string()
        return None

cdef class x509:

    cdef X509 * x509

    def __dealloc__ (self):
        if self.x509 is not NULL:
            X509_free (self.x509)

    def __init__ (self, pem=None):
        cdef mem_bio mb
        if type(pem) is str:
            if len(pem) > 0:
                mb = mem_bio (pem)
                self.x509 = PEM_read_bio_X509 (mb.bio, NULL, NULL, NULL)
                if self.x509 is NULL:
                    raise_ssl_error()
            else:
                self.x509 = X509_new()
        else:
            self.x509 = NULL

    def get_issuer (self):
        cdef x509_name name
        if self.x509 is not NULL:
            name = x509_name()
            name.delegate = X509_get_issuer_name(self.x509)
            return name
        return None

    def get_subject_name (self):
        cdef x509_name name
        if self.x509 is not NULL:
            name = x509_name()
            name.delegate = X509_get_subject_name(self.x509)
            return name
        return None

    def get_version (self):
        """Retrieve the version number

        :Returns:
            A long containing the version number
        """
        return X509_get_version(self.x509)

    def set_version (self, version):
        """Set the version

        :Parameters:
            - `version`: Version number
        """
        cdef int i
        if self.x509 is not NULL:
            i = X509_set_version(self.x509, version)
            return i
        return None

    def get_serialNumber (self):
        cdef asn1_integer serial
        if self.x509 is not NULL:
            serial = asn1_integer()
            serial.delegate = X509_get_serialNumber(self.x509)
            return serial
        return None

    def set_serialNumber (self, serial=None):
        """Set the certificate serial number

        :Parameters:
            - `serial` : Serial number to set.  If None, random number is used
        """
        cdef bignum bn
        cdef asn1_integer ns
        cdef long num
        if self.x509 is not NULL:
            if serial is None:
                bn = bignum()
                bn.pseudo_rand()
                ns = bn.to_asn1_integer()
            else:
                num = serial
                ns = asn1_integer(num)
            X509_set_serialNumber(self.x509, ns.delegate)

    def get_notBefore (self):
        cdef asn1_time time
        if self.x509 is not NULL:
            time = asn1_time()
            time.delegate = X509_get_notBefore(self.x509)
            return time
        return None

    def get_notAfter (self):
        cdef asn1_time time
        if self.x509 is not NULL:
            time = asn1_time()
            time.delegate = X509_get_notAfter(self.x509)
            return time
        return None

    def set_pubkey (self, pkey key):
        if self.x509 is not NULL:
            return X509_set_pubkey(self.x509, key.pkey)
        return None

    def to_x509_req (self, char *digest=SN_sha1):
        cdef x509_req req
        if self.x509 is not NULL:
            req = x509_req()
            req.delegate = X509_to_X509_REQ(self.x509, NULL, EVP_get_digestbyname(digest))
            return req
        return None

    def sign (self, pkey key, char *digest=SN_sha1):
        if (self.x509 is not NULL and
            not X509_sign(self.x509, key.pkey, EVP_get_digestbyname(digest))):
            raise_ssl_error()

    def as_pem (self):
        cdef mem_bio buf
        cdef char * pem
        cdef long pem_size
        if self.x509 is not NULL:
            buf = mem_bio()
            if not PEM_write_bio_X509 (buf.bio, self.x509):
                raise_ssl_error()
            else:
                return buf.as_string()
        else:
            raise Error ("NULL x509 object")

    def print_ex (self, int nmflag, unsigned long cflag):
        cdef mem_bio buf
        if self.x509 is not NULL:
            buf = mem_bio()
            X509_print_ex(buf.bio, self.x509, nmflag, cflag)
            return buf.as_string()
        return None

    def __str__ (self):
        return (
            "x509{\nSubject: %s\nIssuer: %s\n"
            "Version: %d\nSerial Number: %d\n"
            "Not Before: %s\nNot After: %s\n"
            "Certificate:\n%s}" % (
                self.get_subject_name(), self.get_issuer(),
                self.get_version(), self.get_serialNumber().get(),
                self.get_notBefore().to_string(), self.get_notAfter().to_string(),
                self.as_pem()
                )
            )
    
# compatibility
def read_pem_cert (pem):
    return x509 (pem)

# ================================================================================

# Class reperesentation of a PKCS#12 certificate
cdef class pkcs12:

    cdef PKCS12 * delegate

    def __dealloc__ (self):
        if self.delegate is not NULL:
            PKCS12_free (self.delegate)

    def __init__ (self, data=None):
        """Constructs a PKCS#12 certificate

        :Parameters:
            - data: Initial content of the PKCS#12 certificate
        """
        cdef mem_bio mb
        if data:
            mb = mem_bio (data)
            self.delegate = d2i_PKCS12_bio(mb.bio, NULL)
            if self.delegate is NULL:
                raise_ssl_error()
        else:
            self.delegate = NULL

    def parse (self, password):
        """Parses the content of the PKCS#12 certificate

        :Parameters:
            - `password`: Password of the PKCS#12 certificate

        :Return:
            Tuple contain (pkey, x509, [x509...])
        """
        cdef pkey key
        cdef x509 cert
        cdef x509 ca
        cdef stack_st *chain
        cdef list result = []
        key = pkey()
        cert = x509()
        chain = NULL

        if self.delegate is NULL:
            raise Error ("Empty PKCS12 object")

        if PKCS12_parse(self.delegate, password, &key.pkey, &cert.x509, &chain) == 0:
            raise_ssl_error()

        while True:
            ca = x509()
            ca.x509 = <X509 *> sk_pop(chain)
            if ca.x509 is NULL:
                break
            result.append (ca)

        sk_free(chain)

        return key, cert, result

    def create (self, password, pkey key, x509 cert, intermediates=[], name=None):
        """Creates the content of the PKCS#12 certificate

        :Parameters:
            - `password`: Password to assign to the PKCS#12 certificate
            - `key`: Instance of class pkey containing the private key
            - `cert`: Instance of class x509 containing the public certificate
            - `intermediates`: Instances of class x509 containing the intermediate certificates
            - `name`: Name to assign to the PKCS#12 certificate
        """
        cdef stack_st *chain
        cdef x509 ca
        cdef char *n

        n = NULL
        if name is not None:
            n = name

        chain = sk_new_null()
        for ca in intermediates:
            sk_push(chain, <char *> ca.x509)
        self.delegate = PKCS12_create(password, n, key.pkey, cert.x509, chain, 0, 0, 0, 0, 0)
        sk_free(chain)
        if self.delegate is NULL:
            raise_ssl_error()

    def as_data (self):
        """Retrieves the binary representation of the PKCS#12 certifcate

        :Return:
            String containing the binary representation of the PKCS#12 certificate
        """
        cdef mem_bio mb
        if self.delegate is not NULL:
            mb = mem_bio()
            if not i2d_PKCS12_bio(mb.bio, self.delegate):
                raise_ssl_error()
            else:
                return mb.as_string()
        else:
            raise Error("Empty PKCS12 object")

# ================================================================================

cdef class dh_param:

    cdef DH * dh

    def __dealloc__ (self):
        if self.dh is not NULL:
            DH_free (self.dh)

    def __init__ (self, pem):
        cdef mem_bio mb
        mb = mem_bio (pem)
        self.dh = PEM_read_bio_DHparams (mb.bio, NULL, NULL, NULL)
        if self.dh is NULL:
            raise_ssl_error()


# ================================================================================

cdef class ssl_ctx

cdef class ssl:

    cdef SSL * ssl
    cdef readonly x509 cert
    cdef readonly pkey key
    cdef readonly dh_param dh

    def __init__ (self, ssl_ctx c):
        self.ssl = SSL_new (c.ctx)
        if self.ssl is NULL:
            raise_ssl_error()

    def __dealloc__ (self):
        if self.ssl is not NULL:
            SSL_free (self.ssl)

    # Note: there's a separate error mechanism for I/O on ssl objects,
    #   it's easy to confuse it with the more generic error mechanism.
    def raise_error (self, int code):
        error = SSL_get_error (self.ssl, code)
        if error == SSL_ERROR_SYSCALL:
            PyErr_SetFromErrno (OSError)
        elif error == SSL_ERROR_WANT_READ:
            raise WantRead
        elif error == SSL_ERROR_WANT_WRITE:
            raise WantWrite
        else:
            # the error is not related to this ssl objectn
            raise_ssl_error()

    def use_cert (self, x509 cert):
        if SSL_use_certificate (self.ssl, cert.x509) == 0:
            raise_ssl_error()
        else:
            self.cert = cert

    def use_key (self, pkey k):
        if SSL_use_PrivateKey (self.ssl, k.pkey) == 0:
            raise_ssl_error()
        else:
            self.key = k

    def set_ciphers (self, ciphers):
        if SSL_set_cipher_list (self.ssl, ciphers) == 0:
            raise_ssl_error()

    def set_tmp_dh (self, dh_param dh):
        if SSL_set_tmp_dh (self.ssl, dh.dh) == 0:
            raise_ssl_error()
        else:
            self.dh = dh

    def set_verify (self, int mode):
        SSL_set_verify (self.ssl, mode, NULL)

    def check_key (self):
        if SSL_check_private_key (self.ssl) == 0:
            raise_ssl_error()
        else:
            return True

    def get_options (self):
        return SSL_get_options (self.ssl)

    def set_options (self, long options):
        return SSL_set_options (self.ssl, options)

    def get_ciphers (self):
        cdef char * cipher
        cdef int i
        cdef list result = []
        i = 0
        while 1:
            cipher = SSL_get_cipher_list (self.ssl, i)
            if cipher:
                result.append (cipher)
                i = i + 1
            else:
                break
        return result

    def get_cipher (self):
        cdef char * result
        result = SSL_get_cipher (self.ssl)
        if result is NULL:
            return None
        else:
            return result

    def set_connect_state (self):
        SSL_set_connect_state (self.ssl)

    def set_accept_state (self):
        SSL_set_accept_state (self.ssl)

    def set_fd (self, int fd):
        if SSL_set_fd (self.ssl, fd) == 0:
            raise_ssl_error()

    def get_peer_cert (self):
        cdef X509 * cert
        cdef x509 result
        cert = SSL_get_peer_certificate (self.ssl)
        if cert is not NULL:
            result = x509()
            result.x509 = cert
            return result

    def get_peer_cert_chain (self):
        cdef int i, n
        cdef x509 x
        cdef stack_st * chain
        cdef list result = []
        # this is apparently a 'borrowed' reference.
        chain = SSL_get_peer_cert_chain (self.ssl)
        if chain is NULL:
            return result
        else:
            n = sk_num (chain)
            for i from 0 <= i < n:
                x = x509()
                # we need to copy these, otherwise all hell breaks loose.
                x.x509 = X509_dup (<X509 *> sk_value (chain, i))
                result.append (x)
            return result

    def accept (self):
        cdef int r
        r = SSL_accept (self.ssl)
        if r <= 0:
            self.raise_error (r)

    def connect (self):
        cdef int r
        r = SSL_connect (self.ssl)
        if r <= 0:
            self.raise_error (r)

    def read (self, int size):
        cdef int count, error
        cdef bytes result = PyBytes_FromStringAndSize (NULL, size)
        count = SSL_read (self.ssl, <char*>result, size)
        if count < 0:
            self.raise_error (count)
        elif count == 0:
            # you are in a maze of twisty passages, all alike.
            error = SSL_get_error (self.ssl, 0)
            if error == SSL_ERROR_ZERO_RETURN:
                # normal, clean shut down.
                return ''
            elif error == SSL_ERROR_SYSCALL and errno == 0:
                # XXX dunno what the problem is here
                return ''
            else:
                # an unclean shutdown
                self.raise_error (error)
        elif count == size:
            return result
        else:
            return result[:count]

    def write (self, bytes buffer):
        cdef int size, status
        size = len (buffer)
        status = SSL_write (self.ssl, <char*>buffer, size)
        if status <= 0:
            # whether clean or unclean, a shut down during a write
            #   merits an exception.
            self.raise_error (status)
        else:
            return status

    def shutdown (self):
        cdef int status
        status = SSL_shutdown (self.ssl)
        if status < 0:
            self.raise_error (status)
        else:
            return status

    def get_verify_result (self):
        cdef long result
        result = SSL_get_verify_result (self.ssl)
        return result, X509_verify_cert_error_string (result)

    IF NPN:
        def get_next_protos_negotiated (self):
            cdef unsigned char * data
            cdef unsigned int len
            SSL_get0_next_proto_negotiated (self.ssl, &data, &len)
            if data:
                return PyBytes_FromStringAndSize (<char*>data, len)
            else:
                return None

# ================================================================================

cdef class ssl_ctx:

    cdef SSL_CTX * ctx
    cdef readonly x509 cert
    cdef readonly pkey key
    cdef readonly dh_param dh
    cdef bytes next_protos

    def __init__ (self):
        self.ctx = SSL_CTX_new (SSLv23_method())
        if self.ctx is NULL:
            raise_ssl_error()

    def __dealloc__ (self):
        if self.ctx is not NULL:
            SSL_CTX_free (self.ctx)

    def use_cert (self, x509 cert, chain=()):
        cdef x509 link
        cdef X509 * dup
        if SSL_CTX_use_certificate (self.ctx, cert.x509) == 0:
            raise_ssl_error()
        else:
            self.cert = cert
        for link in chain:
            # need to duplicate it
            dup = X509_dup (link.x509)
            if dup is NULL:
                raise_ssl_error()
            elif SSL_CTX_add_extra_chain_cert (self.ctx, dup) == 0:
                raise_ssl_error()

    def use_key (self, pkey k):
        if SSL_CTX_use_PrivateKey (self.ctx, k.pkey) == 0:
            raise_ssl_error()
        else:
            self.key = k

    def set_ciphers (self, ciphers):
        if SSL_CTX_set_cipher_list (self.ctx, ciphers) == 0:
            raise_ssl_error()

    def set_tmp_dh (self, dh_param dh):
        if SSL_CTX_set_tmp_dh (self.ctx, dh.dh) == 0:
            raise_ssl_error()
        else:
            self.dh = dh

    def set_verify (self, int mode):
        SSL_CTX_set_verify (self.ctx, mode, NULL)

    def check_key (self):
        if SSL_CTX_check_private_key (self.ctx) == 0:
            raise_ssl_error()
        else:
            return True

    def ssl (self):
        return ssl (self)

    def load_verify_locations (self, char * file=NULL, char * dir=NULL):
        if SSL_CTX_load_verify_locations (self.ctx, file, dir) == 0:
            if file is NULL and dir is NULL:
                raise ValueError ("<file> or <dir> must be specified")
            else:
                raise_ssl_error()

    def verify_cert (self, x509 cert):
        cdef X509_STORE * store
        cdef X509_STORE_CTX * ctx
        ctx = X509_STORE_CTX_new()
        if ctx is NULL:
            raise_ssl_error()
        try:
            store = SSL_CTX_get_cert_store (self.ctx)
            if store is NULL:
                raise_ssl_error()
            X509_STORE_CTX_init (ctx, store, cert.x509, NULL)
            if X509_verify_cert (ctx) == 0:
                return False
            else:
                return True
        finally:
            X509_STORE_CTX_free (ctx)

    def get_options (self):
        return SSL_CTX_get_options (self.ctx)

    def set_options (self, long options):
        return SSL_CTX_set_options (self.ctx, options)

    IF NPN:
        def set_next_protos (self, list protos):
            r = []
            for proto in protos:
                r.append (chr (len (proto)))
                r.append (proto)
            self.next_protos = b''.join (r)
            SSL_CTX_set_next_protos_advertised_cb (self.ctx, next_protos_server_callback, <void*>self)
            SSL_CTX_set_next_proto_select_cb (self.ctx, next_protos_client_callback, <void*>self)

        cdef next_protos_server_callback (self, unsigned char **out, unsigned int *outlen):
            out[0] = self.next_protos
            outlen[0] = len (self.next_protos)
            return SSL_TLSEXT_ERR_OK

        cdef next_protos_client_callback (self, unsigned char **out, unsigned char *outlen,
                                          unsigned char * server, unsigned int server_len):
            SSL_select_next_proto (out, outlen, server, server_len, self.next_protos, len (self.next_protos))
            return SSL_TLSEXT_ERR_OK

IF NPN:
    cdef int next_protos_server_callback (SSL *ssl, unsigned char **out, unsigned int *outlen, void *arg):
        cdef ssl_ctx ctx = <ssl_ctx> arg
        return ctx.next_protos_server_callback (out, outlen)

    cdef int next_protos_client_callback (SSL *ssl, unsigned char **out, unsigned char *outlen,
                                          unsigned char * server, unsigned int server_len, void *arg):
        cdef ssl_ctx ctx = <ssl_ctx> arg
        return ctx.next_protos_client_callback (out, outlen, server, server_len)

# ================================================================================

cdef class cipher:

    cdef EVP_CIPHER_CTX ctx
    cdef readonly int block_size
    cdef readonly int encrypt
    cdef readonly object key
    cdef readonly object iv

    def __init__ (self, kind, key=None, iv=None, int encrypt=0):
        cdef EVP_CIPHER * cipher
        self.encrypt = encrypt
        cipher = EVP_get_cipherbyname (kind)
        if cipher is NULL:
            raise UnknownCipherType (kind)
        EVP_CIPHER_CTX_init (&self.ctx)
        if EVP_CipherInit_ex (&self.ctx, cipher, NULL, NULL, NULL, encrypt) == 0:
            raise_ssl_error()
        if key is not None:
            self.set_key (key)
        if iv is not None:
            self.set_iv (iv)
        self.block_size = EVP_CIPHER_CTX_block_size (&self.ctx)

    def __dealloc__ (self):
        EVP_CIPHER_CTX_cleanup (&self.ctx)

    def get_key_length (self):
        return EVP_CIPHER_CTX_key_length (&self.ctx)

    def get_iv_length (self):
        return EVP_CIPHER_CTX_iv_length (&self.ctx)

    cpdef set_key (self, bytes key):
        if EVP_CipherInit_ex (&self.ctx, NULL, NULL, <char *> key, NULL, self.encrypt) == 0:
            raise_ssl_error()
        else:
            self.key = key

    cpdef set_iv (self, bytes iv):
        if EVP_CipherInit_ex (&self.ctx, NULL, NULL, NULL, <char *> iv, self.encrypt) == 0:
            raise_ssl_error()
        else:
            self.iv = iv

    def update (self, bytes data):
        cdef int isize = len (data)
        cdef int osize = self.block_size + isize
        out_string = PyBytes_FromStringAndSize (NULL, osize)
        if EVP_CipherUpdate (
            &self.ctx, <char*>out_string, &osize, <char *>data, isize
            ) == 0:
            raise_ssl_error()
        elif osize != len (out_string):
            return out_string[:osize]
        else:
            return out_string

    def final (self):
        cdef int osize = self.block_size
        ostring = PyBytes_FromStringAndSize (NULL, osize)
        if EVP_CipherFinal_ex (&self.ctx, <char *>ostring, &osize) == 0:
            raise_ssl_error()
        elif osize != self.block_size:
            return ostring[:osize]
        else:
            return ostring

# XXX leak check this fast-and-loose object pointer magic
cdef void collect_cipher (OBJ_NAME * name, void * arg):
    (<list>arg).append (name.name)

def get_all_ciphers():
    result = []
    OBJ_NAME_do_all_sorted (
        OBJ_NAME_TYPE_CIPHER_METH,
        collect_cipher,
        <void*>result
        )
    return result

# ================================================================================

cdef class digest:

    cdef EVP_MD_CTX ctx

    def __init__ (self, kind):
        cdef EVP_MD * digest
        digest = EVP_get_digestbyname (kind)
        if digest is NULL:
            raise UnknownDigestType (kind)
        EVP_MD_CTX_init (&self.ctx)
        if EVP_DigestInit_ex (&self.ctx, digest, NULL) == 0:
            raise_ssl_error()

    def __dealloc__ (self):
        EVP_MD_CTX_cleanup (&self.ctx)

    def update (self, bytes data):
        cdef int isize
        if EVP_DigestUpdate (&self.ctx, <char*>data, len(data)) == 0:
            raise_ssl_error()

    def final (self):
        cdef int osize
        cdef bytes ostring = PyBytes_FromStringAndSize (NULL, EVP_MAX_MD_SIZE)
        if EVP_DigestFinal_ex (&self.ctx, <char*>ostring, &osize) == 0:
            raise_ssl_error()
        elif osize != len(ostring):
            return ostring[:osize]
        else:
            return ostring

    def sign (self, pkey key):
        cdef int osize
        cdef bytes sig = PyBytes_FromStringAndSize (NULL, key._size())
        # Finalize/sign the hash
        if EVP_SignFinal (&self.ctx, <char*>sig, &osize, key.pkey) == 0:
            raise_ssl_error()
        elif osize != len(sig):
            return sig[:osize]
        else:
            return sig

    def verify (self, pkey key, sig):
        cdef int result
        # verify this signature
        result = EVP_VerifyFinal (&self.ctx, sig, len(sig), key.pkey)
        if result == 1:
            return True
        elif result == 0:
            return False
        else:
            raise_ssl_error()

# ================================================================================

cdef class ecdsa:

    cdef EC_KEY * key

    def __init__ (self, object curve):
        cdef int nid
        if curve is None:
            # no curve specified
            self.key = EC_KEY_new()
        else:
            if type(curve) is int:
                nid = curve
            else:
                nid = OBJ_sn2nid (curve)
            if nid == 0:
                raise_ssl_error()
            else:
                self.key = EC_KEY_new_by_curve_name (nid)
                if self.key is NULL:
                    raise_ssl_error()

    def __dealloc__ (self):
        if self.key is not NULL:
            EC_KEY_free (self.key)

    def generate (self):
        cdef int status = EC_KEY_generate_key (self.key)
        if status != 1:
            raise_ssl_error()

    def set_privkey (self, bytes pkey):
        cdef const unsigned char * p = pkey
        cdef EC_KEY * result = d2i_ECPrivateKey (&self.key, &p, len(pkey))
        if result is NULL:
            raise_ssl_error()

    def set_pubkey (self, key):
        cdef const unsigned char * p = key
        cdef EC_KEY * result = o2i_ECPublicKey (&self.key, &p, len (key))
        if result is NULL:
            raise_ssl_error()

    def get_privkey (self):
        cdef int r = 0
        cdef int size = i2d_ECPrivateKey (self.key, NULL)
        cdef bytes result
        cdef unsigned char * p
        if size == 0:
            raise_ssl_error()
        else:
            result = PyBytes_FromStringAndSize (NULL, size)
            p = result
            r = i2d_ECPrivateKey (self.key, &p)
            if r == 0:
                raise_ssl_error()
            else:
                return result

    def get_pubkey (self):
        cdef int r = 0
        cdef int size = i2o_ECPublicKey (self.key, NULL)
        cdef bytes result
        cdef unsigned char * p
        if size == 0:
            raise_ssl_error()
        else:
            result = PyBytes_FromStringAndSize (NULL, size)
            p = result
            r = i2o_ECPublicKey (self.key, &p)
            if r == 0:
                raise_ssl_error()
            else:
                return result

    def sign (self, bytes data):
        cdef unsigned int sig_size = ECDSA_size (self.key)
        cdef bytes sig = PyBytes_FromStringAndSize (NULL, sig_size)
        cdef int result = ECDSA_sign (0, data, len(data), sig, &sig_size, self.key)
        if result != 1:
            raise_ssl_error()
        else:
            return sig[:sig_size]

    def verify (self, bytes data, bytes sig):
        cdef int result = ECDSA_verify (0, data, len(data), sig, len(sig), self.key)
        if result == -1:
            raise_ssl_error()
        else:
            return result

    def set_compressed (self, bint compressed):
        cdef point_conversion_form_t form
        if compressed:
            form = POINT_CONVERSION_COMPRESSED
        else:
            form = POINT_CONVERSION_UNCOMPRESSED
        EC_KEY_set_conv_form (self.key, form)

# ================================================================================

def random_status():
    return RAND_status()

def random_bytes (int num):
    result = PyBytes_FromStringAndSize (NULL, num)
    if RAND_bytes (<char*>result, num) == 0:
        raise_ssl_error()
    else:
        return result

class SSL_OP:
    ALL           = SSL_OP_ALL
    NO_SSLv2      = SSL_OP_NO_SSLv2
    NO_SSLv3      = SSL_OP_NO_SSLv3
    NO_TLSv1      = SSL_OP_NO_TLSv1
    SINGLE_DH_USE = SSL_OP_SINGLE_DH_USE

class SSL_VERIFY:
    NONE                 = SSL_VERIFY_NONE
    PEER                 = SSL_VERIFY_PEER
    FAIL_IF_NO_PEER_CERT = SSL_VERIFY_FAIL_IF_NO_PEER_CERT
    CLIENT_ONCE          = SSL_VERIFY_CLIENT_ONCE

openssl_version = OPENSSL_VERSION_TEXT

# initialize the library
SSL_load_error_strings()
ERR_load_crypto_strings()
OpenSSL_add_ssl_algorithms()
OpenSSL_add_all_algorithms()
OpenSSL_add_all_ciphers()
OpenSSL_add_all_digests()
