# Copyright (c) 2002-2011 IronPort Systems and Cisco Systems
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

# Definitions from libc.

cdef extern char ** environ

cdef extern from "inttypes.h":
    ctypedef char               int8_t
    ctypedef unsigned char      uint8_t
    ctypedef short              int16_t
    ctypedef unsigned short     uint16_t
    ctypedef int                int32_t
    ctypedef unsigned int       uint32_t
    ctypedef long long          int64_t
    ctypedef unsigned long long uint64_t
    ctypedef long               intptr_t
    ctypedef unsigned long      uintptr_t

cdef extern from "sys/types.h":
    ctypedef unsigned long      size_t
    ctypedef long               ssize_t
    ctypedef int64_t            off_t
    ctypedef uint16_t           mode_t
    ctypedef int32_t            pid_t
    ctypedef long               time_t
    ctypedef long               suseconds_t
    ctypedef uint32_t           gid_t
    ctypedef int64_t            id_t
    ctypedef uint32_t           uid_t
    ctypedef uint32_t           fixpt_t
    ctypedef uint32_t           dev_t
    ctypedef long               segsz_t
    ctypedef unsigned long      vm_size_t

    ctypedef unsigned char      u_char
    ctypedef unsigned short     u_short
    ctypedef unsigned int       u_int
    ctypedef unsigned long      u_long
    ctypedef unsigned short     ushort         # Sys V compatibility
    ctypedef unsigned int       uint           # Sys V compatibility

cdef extern from "stdarg.h":

    # The type of va_list is not a standard definition.
    # This should be a rather opaque type.
    ctypedef void * va_list

    # va_arg support is not possible in Pyrex.  Some hard-coded types
    # are available in pyrex_helpers.pyx.
    void va_start(va_list ap, last)
    void va_copy(va_list dest, va_list src)
    void va_end(va_list ap)

cdef extern from "stdio.h":
    ctypedef struct FILE:
        pass

    void perror(char *string)
    int printf  (char * format, ...)
    int fprintf (FILE * stream, char * format, ...)
    int sprintf (char * str, char * format, ...)
    int snprintf(char * str, size_t size, char * format, ...)
    int asprintf(char **ret, char *format, ...)
    int vprintf (char * format, va_list ap)
    int vfprintf(FILE * stream, char * format, va_list ap)
    int vsprintf(char * str, char * format, va_list ap)
    int vsnprintf(char * str, size_t size, char * format, va_list ap)
    int vasprintf(char **ret, char *format, va_list ap)

    FILE * stderr
    FILE * stdin
    FILE * stdout

cdef extern from "ctype.h":
    int     isalnum (int)
    int     isalpha (int)
    int     iscntrl (int)
    int     isdigit (int)
    int     isgraph (int)
    int     islower (int)
    int     isprint (int)
    int     ispunct (int)
    int     isspace (int)
    int     isupper (int)
    int     isxdigit (int)
    int     tolower (int)
    int     toupper (int)

cdef extern from "errno.h":
    extern int errno
    cdef enum enum_errno:
        EPERM
        ENOENT
        ESRCH
        EINTR
        EIO
        ENXIO
        E2BIG
        ENOEXEC
        EBADF
        ECHILD
        EDEADLK
        ENOMEM
        EACCES
        EFAULT
        ENOTBLK
        EBUSY
        EEXIST
        EXDEV
        ENODEV
        ENOTDIR
        EISDIR
        EINVAL
        ENFILE
        EMFILE
        ENOTTY
        ETXTBSY
        EFBIG
        ENOSPC
        ESPIPE
        EROFS
        EMLINK
        EPIPE
        EDOM
        ERANGE
        EAGAIN
        EWOULDBLOCK
        EINPROGRESS
        EALREADY
        ENOTSOCK
        EDESTADDRREQ
        EMSGSIZE
        EPROTOTYPE
        ENOPROTOOPT
        EPROTONOSUPPORT
        ESOCKTNOSUPPORT
        EOPNOTSUPP
        ENOTSUP
        EPFNOSUPPORT
        EAFNOSUPPORT
        EADDRINUSE
        EADDRNOTAVAIL
        ENETDOWN
        ENETUNREACH
        ENETRESET
        ECONNABORTED
        ECONNRESET
        ENOBUFS
        EISCONN
        ENOTCONN
        ESHUTDOWN
        ETOOMANYREFS
        ETIMEDOUT
        ECONNREFUSED
        ELOOP
        ENAMETOOLONG
        EHOSTDOWN
        EHOSTUNREACH
        ENOTEMPTY
        EPROCLIM
        EUSERS
        EDQUOT
        ESTALE
        EREMOTE
        EBADRPC
        ERPCMISMATCH
        EPROGUNAVAIL
        EPROGMISMATCH
        EPROCUNAVAIL
        ENOLCK
        ENOSYS
        EFTYPE
        EAUTH
        ENEEDAUTH
        EIDRM
        ENOMSG
        EOVERFLOW
        ECANCELED
        EILSEQ
        ENOATTR
        EDOOFUS
        EBADMSG
        EMULTIHOP
        ENOLINK
        EPROTO

cdef extern from "stdlib.h":
    void *  alloca  (size_t size)
    void    abort   ()
    int     atoi    (char *nptr)
    char *  getenv(char *name)
    int     setenv(char *name, char *value, int overwrite)
    int     putenv(char *string)
    void    unsetenv(char *name)

    void * malloc(size_t size)
    void * calloc(size_t number, size_t size)
    void * realloc(void *ptr, size_t size)
    void free(void *ptr)

    int     daemon(int nochdir, int noclose)

cdef extern from "string.h":
    void *  memset (void *b, int c, size_t len)
    void *  memcpy (void *dst, void *src, size_t len)
    size_t  strlen (char *s)
    int     memcmp (void *b1, void *b2, size_t len)
    char *  strerror(int errnum)
    int     strerror_r(int errnum, char *strerrbuf, size_t buflen)
    int     strncmp(char *s1, char *s2, size_t len)

cdef extern from "unistd.h":
    int     pipe(int *)
    int     close(int)
    pid_t   tcgetpgrp(int)
    pid_t   getpgrp()
    pid_t   getpgid(pid_t)
    pid_t   fork()
    pid_t   getpid()
    pid_t   getppid()
    int     setpgid(pid_t pid, pid_t pgrp)
    int     setpgrp(pid_t pid, pid_t pgrp)
    int     tcsetpgrp(int fd, pid_t pgrp_id)
    int     dup(int oldd)
    int     dup2(int oldd, int newd)
    void    _exit(int status)
    long    sysconf(int name)
    int     chdir(char *path)
    int     fchdir(int fd)
    int     execl(char *path, char *arg, ...)
    int     execlp(char *file, char *arg, ...)
    int     execle(char *path, char *arg, ...)
    int     exect(char *path, char *argv[], char *envp[])
    int     execv(char *path, char *argv[])
    int     execvp(char *file, char *argv[])
    int     execvP(char *file, char *search_path, char *argv[])
    int     execve(char *path, char *argv[], char *envp[])

    int     getgrouplist(char *name, gid_t basegid, gid_t *groups, int *ngroups)
    int     setgroups(int ngroups, gid_t *gidset)
    int     getgroups(int gidsetlen, gid_t *gidset)
    int     initgroups(char *name, gid_t basegid)

    cdef enum:
        NGROUPS_MAX

    cdef enum sysconf_vars:
        _SC_ARG_MAX
        _SC_CHILD_MAX
        _SC_CLK_TCK
        _SC_NGROUPS_MAX
        _SC_OPEN_MAX
        _SC_JOB_CONTROL
        _SC_SAVED_IDS
        _SC_VERSION
        _SC_BC_BASE_MAX
        _SC_BC_DIM_MAX
        _SC_BC_SCALE_MAX
        _SC_BC_STRING_MAX
        _SC_COLL_WEIGHTS_MAX
        _SC_EXPR_NEST_MAX
        _SC_LINE_MAX
        _SC_RE_DUP_MAX
        _SC_2_VERSION
        _SC_2_C_BIND
        _SC_2_C_DEV
        _SC_2_CHAR_TERM
        _SC_2_FORT_DEV
        _SC_2_FORT_RUN
        _SC_2_LOCALEDEF
        _SC_2_SW_DEV
        _SC_2_UPE
        _SC_STREAM_MAX
        _SC_TZNAME_MAX


cdef extern from "fcntl.h":
    int open(char *, int, ...)

    cdef enum open_flags:
        O_RDONLY
        O_WRONLY
        O_RDWR
        O_NONBLOCK
        O_APPEND
        O_CREAT
        O_TRUNC
        O_EXCL
        O_SHLOCK
        O_EXLOCK
        O_DIRECT
        O_FSYNC
        O_NOFOLLOW


cdef extern from "signal.h":
    ctypedef void (*sig_t)(int)

    cdef extern sig_t SIG_DFL
    cdef extern sig_t SIG_IGN
    cdef extern sig_t SIG_ERR

    ctypedef struct sigset_t:
        pass

    ctypedef struct struct_sigaction "struct sigaction":
        sig_t sa_handler
        int sa_flags
        sigset_t sa_mask

    int sigaction(int sig, struct_sigaction *act, struct_sigaction *oact)
    int sigprocmask(int how, sigset_t *set, sigset_t *oset)

    int sigemptyset(sigset_t *set)
    int sigfillset(sigset_t *set)
    int sigaddset(sigset_t *set, int signo)
    int sigdelset(sigset_t *set, int signo)
    int sigismember(sigset_t *set, int signo)
    sig_t signal(int sig, sig_t func)
    int kill (pid_t pid, int sig)

    cdef enum __signals:
        SIGHUP
        SIGINT
        SIGQUIT
        SIGILL
        SIGTRAP
        SIGABRT
        SIGIOT
        SIGEMT
        SIGFPE
        SIGKILL
        SIGBUS
        SIGSEGV
        SIGSYS
        SIGPIPE
        SIGALRM
        SIGTERM
        SIGURG
        SIGSTOP
        SIGTSTP
        SIGCONT
        SIGCHLD
        SIGTTIN
        SIGTTOU
        SIGIO
        SIGXCPU
        SIGXFSZ
        SIGVTALRM
        SIGPROF
        SIGWINCH
        SIGINFO
        SIGUSR1
        SIGUSR2
        SIGTHR
        SIGLWP

    cdef enum __sigprocmask_flags:
        SIG_BLOCK
        SIG_UNBLOCK
        SIG_SETMASK

cdef extern from "time.h":
    cdef struct tm:
        int tm_sec
        int tm_min
        int tm_hour
        int tm_mday
        int tm_mon
        int tm_year
        int tm_wday
        int tm_yday
        int tm_isdst
        char *tm_zone
        long tm_gmtoff

    char * ctime(time_t *clock)
    tm * localtime(time_t *clock)
    tm * gmtime(time_t *clock)
    size_t strftime(char * buf, size_t maxsize, char * format, tm * timeptr)
    time_t mktime(tm *)


cdef extern from "sys/time.h":
    cdef struct timeval:
        time_t      tv_sec
        suseconds_t tv_usec

    cdef struct timezone:
        int tz_minuteswest
        int dsttime

    int gettimeofday(timeval *tp, timezone *tzp)

cdef extern from "sys/resource.h":
    cdef struct rusage:
        timeval ru_utime
        timeval ru_stime
        long ru_maxrss
        long ru_ixrss
        long ru_idrss
        long ru_isrss
        long ru_minflt
        long ru_majflt
        long ru_nswap
        long ru_inblock
        long ru_oublock
        long ru_msgsnd
        long ru_msgrcv
        long ru_nsignals
        long ru_nvcsw
        long ru_nivcsw

    int getpriority(int which, int who)
    int setpriority(int which, int who, int prio)

    enum PRIO_WHICH:
        PRIO_PROCESS
        PRIO_PGRP
        PRIO_USER

cdef extern from "sys/wait.h":
    pid_t   wait(int *status)
    pid_t   waitpid(pid_t wpid, int *status, int options)
    pid_t   wait3(int *status, int options, rusage *rusage)
    pid_t   wait4(pid_t wpid, int *status, int options, rusage *rusage)

cdef extern from "limits.h":
    # Defining most of these as "int" since Pyrex normally isn't very picky
    # about the type, and it's good enough for these values.
    int CHAR_BIT
    int CHAR_MAX
    int INT_MAX
    int LONG_BIT
    long LONG_MAX
    int SCHAR_MAX
    int SHRT_MAX
    int SSIZE_MAX
    int UCHAR_MAX
    unsigned int UINT_MAX
    unsigned long ULONG_MAX
    int USHRT_MAX
    int WORD_BIT
    int CHAR_MIN
    int INT_MIN
    long LONG_MIN
    int SCHAR_MIN
    int SHRT_MIN
