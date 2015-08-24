# -*- Mode: Cython -*-

from cpython.bytes cimport PyBytes_FromStringAndSize
from libc.stdint cimport uint64_t, uint32_t, uint16_t, uint8_t


class S2N:
    SSLv2 = 20
    SSLv3 = 30
    TLS10 = 31
    TLS11 = 32
    TLS12 = 33


cdef extern from "s2n.h":
    struct s2n_config
    int s2n_errno
    int s2n_init ()
    int s2n_cleanup ()

    s2n_config *s2n_config_new ()
    int s2n_config_free (s2n_config *config)
    int s2n_config_free_dhparams (s2n_config *config)
    int s2n_config_free_cert_chain_and_key (s2n_config *config)
    const char *s2n_strerror (int error, const char *lang)
    int s2n_config_add_cert_chain_and_key (
        s2n_config *config,
        char *cert_chain_pem,
        char *private_key_pem
    )
    int s2n_config_add_cert_chain_and_key_with_status (
        s2n_config *config,
        char *cert_chain_pem,
        char *private_key_pem,
        const uint8_t *status,
        uint32_t length
    )
    int s2n_config_add_dhparams (s2n_config *config, char *dhparams_pem)
    int s2n_config_set_key_exchange_preferences (s2n_config *config, const char *preferences)
    int s2n_config_set_cipher_preferences (
        s2n_config *config,
        const char *version
    )
    int s2n_config_set_protocol_preferences (
        s2n_config *config,
        const char * const *protocols,
        int protocol_count
    )

    ctypedef enum s2n_status_request_type:
        S2N_STATUS_REQUEST_NONE = 0,
        S2N_STATUS_REQUEST_OCSP = 1

    int s2n_config_set_status_request_type (s2n_config *config, s2n_status_request_type type)

    struct s2n_connection

    ctypedef enum s2n_mode:
        S2N_SERVER,
        S2N_CLIENT

    s2n_connection *s2n_connection_new (s2n_mode mode)
    int s2n_connection_set_config (s2n_connection *conn, s2n_config *config)

    int s2n_connection_set_fd (s2n_connection *conn, int readfd)
    int s2n_connection_set_read_fd (s2n_connection *conn, int readfd)
    int s2n_connection_set_write_fd (s2n_connection *conn, int readfd)

    ctypedef enum s2n_blinding:
        S2N_BUILT_IN_BLINDING,
        S2N_SELF_SERVICE_BLINDING

    int s2n_connection_set_blinding (s2n_connection *conn, s2n_blinding blinding)
    int s2n_connection_get_delay (s2n_connection *conn)

    int s2n_set_server_name (s2n_connection *conn, const char *server_name)
    const char *s2n_get_server_name (s2n_connection *conn)
    const char *s2n_get_application_protocol (s2n_connection *conn)
    const uint8_t *s2n_connection_get_ocsp_response (s2n_connection *conn, uint32_t *length)

    int s2n_negotiate (s2n_connection *conn, int *more)
    ssize_t s2n_send (s2n_connection *conn, void *buf, ssize_t size, int *more)
    ssize_t s2n_recv (s2n_connection *conn,  void *buf, ssize_t size, int *more)

    int s2n_connection_wipe (s2n_connection *conn)
    int s2n_connection_free (s2n_connection *conn)
    int s2n_shutdown (s2n_connection *conn, int *more)

    uint64_t s2n_connection_get_wire_bytes_in (s2n_connection *conn)
    uint64_t s2n_connection_get_wire_bytes_out (s2n_connection *conn)
    int s2n_connection_get_client_protocol_version (s2n_connection *conn)
    int s2n_connection_get_server_protocol_version (s2n_connection *conn)
    int s2n_connection_get_actual_protocol_version (s2n_connection *conn)
    int s2n_connection_get_client_hello_version (s2n_connection *conn)
    const char *s2n_connection_get_cipher (s2n_connection *conn)
    int s2n_connection_get_alert (s2n_connection *conn)

class MODE:
    SERVER = S2N_SERVER
    CLIENT = S2N_CLIENT

class Error (Exception):
    pass

class Want (Exception):
    pass

class WantRead (Want):
    pass

class WantWrite (Want):
    pass

cdef raise_s2n_error():
    raise Error (s2n_strerror (s2n_errno, "EN"))

cdef check (int n):
    if n != 0:
        raise_s2n_error()

def init():
    check (s2n_init())

def cleanup():
    check (s2n_cleanup())

init()

cdef class Config:

    cdef s2n_config * c

    def __init__ (self):
        self.c = s2n_config_new()
        if not self.c:
            raise_s2n_error()

    def __del__ (self):
        if self.c:
            check (s2n_config_free (self.c))

    def set_cipher_preferences (self, bytes version):
        check (s2n_config_set_cipher_preferences (self.c, version))

    def add_cert_chain_and_key (self, bytes chain_pem, bytes skey_pem):
        check (s2n_config_add_cert_chain_and_key (self.c, chain_pem, skey_pem))

    def add_cert_chain_and_key_with_status (self, bytes chain_pem, bytes skey_pem):
        cdef uint8_t status[512]
        check (s2n_config_add_cert_chain_and_key_with_status (self.c, chain_pem, skey_pem, &status[0], sizeof(status)))
        return <char*>status

    def add_dhparams (self, bytes dhparams_pem):
        check (s2n_config_add_dhparams (self.c, dhparams_pem))

    def set_protocol_preferences (self, protocols):
        cdef char * protos[50]
        cdef int count = 0
        assert (len(protocols) < 50)
        for i, proto in enumerate (protocols):
            protos[i] = proto
        count = i
        check (s2n_config_set_protocol_preferences (self.c, protos, count))

    def set_status_request_type (self, s2n_status_request_type stype):
        check (s2n_config_set_status_request_type (self.c, stype))

cdef class Connection:

    cdef s2n_connection * conn

    def __init__ (self, s2n_mode mode):
        self.conn = s2n_connection_new (mode)
        if not self.conn:
            raise_s2n_error()

    def __del__ (self):
        if self.conn:
            check (s2n_connection_free (self.conn))

    def set_config (self, Config cfg):
        check (s2n_connection_set_config (self.conn, cfg.c))

    def set_fd (self, int readfd):
        check (s2n_connection_set_fd (self.conn, readfd))

    def set_read_fd (self, int readfd):
        check (s2n_connection_set_read_fd (self.conn, readfd))

    def set_write_fd (self, int readfd):
        check (s2n_connection_set_write_fd (self.conn, readfd))

    def set_server_name (self, bytes server_name):
        check (s2n_set_server_name (self.conn, server_name))

    def get_server_name (self):
        cdef char * name = s2n_get_server_name (self.conn)
        if name is not NULL:
            return name
        else:
            return None

    def set_blinding (self, s2n_blinding blinding):
        check (s2n_connection_set_blinding (self.conn, blinding))

    def get_delay (self):
        return s2n_connection_get_delay (self.conn)

    def get_wire_bytes (self):
        return (
            s2n_connection_get_wire_bytes_in (self.conn),
            s2n_connection_get_wire_bytes_out (self.conn),
        )

    def get_client_hello_version (self):
        return s2n_connection_get_client_hello_version (self.conn)

    def get_client_protocol_version (self):
        return s2n_connection_get_client_protocol_version (self.conn)

    def get_server_protocol_version (self):
        return s2n_connection_get_server_protocol_version (self.conn)

    def get_actual_protocol_version (self):
        return s2n_connection_get_actual_protocol_version (self.conn)

    def get_application_protocol (self):
        return s2n_get_application_protocol (self.conn)

    def get_ocsp_response (self):
        cdef uint8_t * r
        cdef uint32_t length
        r = s2n_connection_get_ocsp_response (self.conn, &length)
        return r[:length]

    def get_alert (self):
        return s2n_connection_get_alert (self.conn)

    def get_cipher (self):
        return s2n_connection_get_cipher (self.conn)

    # I/O

    def negotiate (self):
        cdef int more
        cdef int r = s2n_negotiate (self.conn, &more)
        if more:
            return more
        else:
            check (r)
            return more

    def send (self, bytes data, int pos=0):
        cdef int more
        cdef ssize_t n
        assert (pos < len(data))
        n = s2n_send (self.conn, <char*>(data) + pos, len(data) - pos, &more)
        if n < 0:
            if more:
                return 0, more
            else:
                raise_s2n_error()
        else:
            return n, more

    def recv (self, ssize_t size):
        cdef int more
        cdef bytes result = PyBytes_FromStringAndSize (NULL, size)
        cdef ssize_t n = s2n_recv (self.conn, <char*>result, size, &more)
        if n < 0:
            if more:
                return b'', more
            else:
                raise_s2n_error()
        else:
            return result[:n], more

    def shutdown (self):
        cdef int more
        check (s2n_shutdown (self.conn, &more))
        return more
