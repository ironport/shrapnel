# -*- Mode: Cython -*-

from libc.stdint cimport uint64_t, uint32_t, uint16_t, uint8_t

#define S2N_SSLv2 20
#define S2N_SSLv3 30
#define S2N_TLS10 31
#define S2N_TLS11 32
#define S2N_TLS12 33

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

    int s2n_config_add_cert_chain_and_key (s2n_config *config, char *cert_chain_pem, char *private_key_pem)
    int s2n_config_add_cert_chain_and_key_with_status (
        s2n_config *config,
        char *cert_chain_pem, 
        char *private_key_pem, 
        const uint8_t *status, 
        uint32_t length
    )
    int s2n_config_add_dhparams (s2n_config *config, char *dhparams_pem)
    int s2n_config_set_key_exchange_preferences (s2n_config *config, const char *preferences)
    int s2n_config_set_cipher_preferences (s2n_config *config, const char *version)
    int s2n_config_set_protocol_preferences (s2n_config *config, const char * const *protocols, int protocol_count)
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

class Error (Exception):
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

cdef class config:
    cdef s2n_config * c
    def __init__ (self):
        self.c = s2n_config_new()
        if not self.c:
            raise_s2n_error()
        
    
        
