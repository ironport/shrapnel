# -*- Mode: Cython -*-

from libc.stdint cimport uint8_t, uint16_t, uint32_t

cdef extern from "netinet/in.h":
    IF UNAME_SYSNAME == "Linux":
        cdef struct in_addr:
            uint32_t s_addr
        cdef struct sockaddr_in:
            short sin_family
            unsigned short sin_port
            in_addr sin_addr
            char sin_zero[8]
    ELSE:
        pass

cdef extern from "sys/un.h":
    IF UNAME_SYSNAME == "Linux":
        cdef struct sockaddr_un:
            short sun_family
            char sun_path[104]
    ELSE:
        pass

cdef extern from "arpa/inet.h":
    cdef enum:
        INET_ADDRSTRLEN
        INET6_ADDRSTRLEN

    int htons (int)
    int htonl (int)
    int ntohl (int)
    int ntohs (int)

cdef extern from "netdb.h":
    struct addrinfo:
        int ai_flags       # input flags
        int ai_family      # protocol family for socket
        int ai_socktype    # socket type
        int ai_protocol    # protocol for socket
        int ai_addrlen     # length of socket-address
        sockaddr *ai_addr  # socket-address for socket
        char *ai_canonname # canonical name for service location
        addrinfo *ai_next  # pointer to next in list
    int getaddrinfo (const char *hostname, const char *servname, const addrinfo *hints, addrinfo **res)
    void freeaddrinfo (addrinfo *ai)

cdef extern from "sys/socket.h":
    int AF_UNSPEC, AF_INET, AF_INET6, AF_UNIX
    int SOCK_STREAM, SOCK_DGRAM, SOL_SOCKET, INADDR_ANY
    int SHUT_RD, SHUT_WR, SHUT_RDWR

    int SO_DEBUG, SO_REUSEADDR, SO_KEEPALIVE, SO_DONTROUTE, SO_LINGER
    int SO_BROADCAST, SO_OOBINLINE, SO_SNDBUF, SO_RCVBUF, SO_SNDLOWAT
    int SO_RCVLOWAT, SO_SNDTIMEO, SO_RCVTIMEO, SO_TYPE, SO_ERROR
    IF UNAME_SYSNAME == "FreeBSD":
        int SO_REUSEPORT, SO_ACCEPTFILTER

    int SO_DONTROUTE, SO_LINGER, SO_BROADCAST, SO_OOBINLINE, SO_SNDBUF
    int SO_REUSEADDR, SO_DEBUG, SO_RCVBUF, SO_SNDLOWAT, SO_RCVLOWAT
    int SO_SNDTIMEO, SO_RCVTIMEO, SO_KEEPALIVE, SO_TYPE, SO_ERROR

    ctypedef unsigned int sa_family_t
    ctypedef unsigned int in_port_t
    ctypedef unsigned int in_addr_t
    ctypedef unsigned int socklen_t

    cdef struct in_addr:
        in_addr_t s_addr

    union ip__u6_addr:
        uint8_t  __u6_addr8[16]
        uint16_t __u6_addr16[8]
        uint32_t __u6_addr32[4]

    struct in6_addr:
        ip__u6_addr __u6_addr

    IF UNAME_SYSNAME == "FreeBSD" or UNAME_SYSNAME == "Darwin":
        cdef struct sockaddr:
            unsigned char sa_len
            sa_family_t sa_family
            char sa_data[250]

        cdef struct sockaddr_in:
            unsigned char sin_len
            sa_family_t sin_family
            in_port_t sin_port
            in_addr sin_addr
            char sin_zero[8]

        cdef struct sockaddr_in6:
            unsigned char sin6_len
            sa_family_t sin6_family
            in_port_t sin6_port
            unsigned int sin6_flowinfo
            in6_addr sin6_addr
            unsigned int sin6_scope_id

        cdef struct sockaddr_un:
            unsigned char sun_len
            sa_family_t sun_family
            char sun_path[104]

        cdef struct sockaddr_storage:
            unsigned char sa_len
            sa_family_t sa_family
    ELSE:
        cdef struct sockaddr:
            sa_family_t sa_family
            char sa_data[250]

        cdef struct sockaddr_in:
            sa_family_t sin_family
            unsigned short sin_port
            in_addr sin_addr
            char sa_data[250]

        cdef struct sockaddr_in6:
            sa_family_t sin6_family
            unsigned short sin6_port
            uint32_t sin6_flowinfo
            in6_addr sin6_addr
            uint32_t sin6_scope_id
            char sa_data[250]

        cdef struct sockaddr_storage:
            sa_family_t sa_family
            char sa_data[250]

    int socket      (int domain, int type, int protocol)
    int connect     (int fd, sockaddr * addr, socklen_t addr_len)
    int accept      (int fd, sockaddr * addr, socklen_t * addr_len)
    int bind        (int fd, sockaddr * addr, socklen_t addr_len)
    int listen      (int fd, int backlog)
    int shutdown    (int fd, int how)
    int close       (int fd)
    int getsockopt  (int fd, int level, int optname, void * optval, socklen_t * optlen)
    int setsockopt  (int fd, int level, int optname, void * optval, socklen_t optlen)
    int getpeername (int fd, sockaddr * name, socklen_t * namelen)
    int getsockname (int fd, sockaddr * name, socklen_t * namelen)
    int sendto      (int fd, void * buf, size_t len, int flags, sockaddr * addr, socklen_t addr_len)
    int send        (int fd, void * buf, size_t len, int flags)
    int recv        (int fd, void * buf, size_t len, int flags)
    int recvfrom    (int fd, void * buf, size_t len, int flags, sockaddr * addr, socklen_t * addr_len)
    int _c_socketpair "socketpair"  (int d, int type, int protocol, int *sv)
    int inet_pton   (int af, char *src, void *dst)
    char *inet_ntop (int af, void *src, char *dst, socklen_t size)
    char * inet_ntoa (in_addr pin)
    int inet_aton   (char * cp, in_addr * pin)

cdef extern from "sys/uio.h":
    cdef struct iovec:
        void * iov_base
        size_t iov_len

cdef extern from "unistd.h":
    size_t write (int fd, char * buf, size_t nbytes)
    size_t read  (int fd, char * buf, size_t nbytes)
    size_t writev(int d, iovec *iov, int iovcnt)
    size_t readv (int d, iovec *iov, int iovcnt)

cdef extern from "fcntl.h":
    int fcntl (int fd, int cmd, ...)
    int F_GETFL, O_NONBLOCK, F_SETFL

cdef public class sock [ object sock_object, type sock_type ]:
    cdef public int fd, orig_fd, domain, stype
    #def __init__ (self, int domain=AF_INET, int stype=SOCK_STREAM, int protocol=0, int fd=-1)
    cdef int _try_selfish(self) except -1
    cdef _set_reuse_addr (self)
    cdef set_nonblocking (self)
    cdef parse_address (self, object address, sockaddr_storage * sa, socklen_t * addr_len, bint resolve=?)
    cdef parse_address_inet (self, tuple address, sockaddr_storage * sa, socklen_t * addr_len, bint resolve)
    cdef parse_address_inet6 (self, tuple address, sockaddr_storage * sa, socklen_t * addr_len, bint resolve)
    cdef parse_address_unix (self, bytes address, sockaddr_storage * sa, socklen_t * addr_len, bint resolve)
    cdef object unparse_address (self, sockaddr_storage *sa, socklen_t addr_len)
    cdef _wait_for_read (self)
    cdef _wait_for_write (self)
    cpdef connect_addr (self, address, bint resolve=?)
    cpdef connect (self, address)
    cpdef bytes recv (self, int buffer_size)
    cpdef bytes read (self, int buffer_size)
    cpdef object recvfrom (self, int buffer_size, int flags=?)
    cpdef bytes recv_exact (self, int bytes)
    cpdef readv (self, list size_list)
    cpdef int send (self, bytes data) except -1
    cpdef int sendto (self, bytes data, address, int flags=?) except -1
    cpdef int sendall (self, bytes data) except -1
    cpdef int write (self, bytes data) except -1
    cpdef int writev (self, list data) except -1
    # XXX is there a cpython.type for buffer objects?
    IF False:
        cpdef recv_into (self, buffer, int nbytes=?, int flags=?)
        cpdef recvfrom_into(self, buffer, int nbytes=?, int flags=?)
    cpdef bind (self, address)
    cpdef listen (self, int backlog)
    cpdef accept (self)
    cpdef accept_many (self, int max=?)
    cpdef shutdown (self, int how)
    cpdef getpeername (self)
    cpdef getsockname (self)
    cpdef dup(self)

cdef class file_sock (sock):
    cdef object _fileobj

