from cpython.bytes cimport PyBytes_FromStringAndSize, PyBytes_Check, PyBytes_AS_STRING

cdef extern from "stdlib.h":
    int posix_memalign(void **memptr, size_t alignment, size_t size)
    void free(void *ptr)

cdef extern from "libaio.h":
    ctypedef struct io_context_t:
        int a

    cdef struct iocb:
        void *data
        unsigned key
        short aio_lio_opcode
        short aio_reqprio
        int aio_fildes

    cdef struct io_event:
        void *data
        iocb *obj
        long long res

    int io_setup(unsigned nr_events, io_context_t *ctxp)
    int io_destroy(io_context_t ctx)
    void io_prep_pread(iocb *iocb, int fd, void *buf, size_t count, long long offset)
    void io_prep_pwrite(iocb *iocb, int fd, void *buf, size_t count, long long offset)
    int io_submit(io_context_t ctx, long nr, iocb *iocbs[])
    int io_getevents(io_context_t ctx, long min_nr, long nr, io_event *events, timespec *timeout)
    void io_set_eventfd(iocb *iocb, int eventfd)

cdef extern from "sys/eventfd.h":
    int eventfd(unsigned int initval, int flags)
    
    int EFD_NONBLOCK

cdef enum:
    MAX_PENDING_REQS = 1024
    BLOCK_SIZE = 512

cdef int aio_eventfd
cdef io_context_t aio_ioctx
cdef dict aio_event_map
cdef iocb aio_iocb[MAX_PENDING_REQS]

cdef aio_setup():
    cdef int res
    global aio_eventfd, aio_event_map

    res = io_setup(MAX_PENDING_REQS, &aio_ioctx)
    if res:
        raise_oserror_with_errno(res)
    aio_eventfd = eventfd(0, EFD_NONBLOCK)
    if aio_eventfd == -1:
        raise_oserror()
    the_poller._register_fd(aio_eventfd)
    aio_event_map = {}

cdef aio_teardown():
    cdef int res
    
    res = io_destroy(aio_ioctx)
    if res:
        raise_oserror_with_errno(res)
    close(aio_eventfd)

cdef aio_poll():
    cdef int r, fd, res
    cdef long n
    cdef coro co
    cdef io_event aio_io_events[MAX_PENDING_REQS]

    read(aio_eventfd, <char*>&n, 8)
    r = io_getevents(aio_ioctx, 1, n, aio_io_events, NULL)
    if r < 0:
        raise_oserror()
    for i from 0 <= i < r:
        fd = aio_io_events[i].obj.aio_fildes
        res = aio_io_events[i].res
        #print 'POLL: fd=%r, res=%r' % (fd, res)
        co = aio_event_map.pop(fd)
        co._schedule(res)

cdef _aligned_size(size):
    if size % BLOCK_SIZE:
        return (size/BLOCK_SIZE + 1) * BLOCK_SIZE
    else:
        return size

cdef long _aio_wb, _aio_rb, _aio_rnb, _aio_wnb, _aio_rp, _aio_wp, _aio_pending

_aio_wb = 0
_aio_rb = 0
_aio_rnb = 0
_aio_wnb = 0
_aio_rp = 0
_aio_wp = 0
_aio_pending = 0

def aio_stats():
    """Return AIO statistics.

    :Return:
        Returns a tuple of ``(rnb, rb, wnb, wb, rp, wp)``:

        - ``rnb``: Non-blocking reads.
        - ``rb``: Blocking-reads.
        - ``wnb``: Non-blocking writes.
        - ``wb``: Blocking-writes.
        - ``rp``: Pending reads.
        - ``wp``: Pending writes.
    """
    return _aio_rnb, _aio_rb, _aio_wnb, _aio_wb, _aio_rp, _aio_wp

def aio_read (int fd, int nbytes, uint64_t offset):
    """Asynchronously read data from a file. fd should be opened in
       O_DIRECT mode by the caller to make this non blocking.

    :Parameters:
        - `fd`: The file descriptor to read from.
        - `nbytes`: The number of bytes to read.
        - `offset`: The offset to read from.

    :Return:
        Returns a string of data read from the file.

    :Exceptions:
        - `OSError`: OS-level error.
    """
    global _aio_pending, _aio_rb, _aio_rnb, _aio_rp, aio_iocb

    cdef object buf, res
    cdef int aligned_size
    cdef iocb *piocb
    cdef iocb *iocbs[1]
    cdef char *strbuf

    aligned_size = _aligned_size(nbytes)
    posix_memalign(<void**>&strbuf, BLOCK_SIZE, aligned_size)
    me = the_scheduler._current
    piocb = &aio_iocb[_aio_pending]
    _aio_pending += 1
    _aio_rp += 1
    io_prep_pread(piocb, fd, strbuf, aligned_size, offset)
    io_set_eventfd(piocb, aio_eventfd)
    iocbs[0] = piocb
    io_submit(aio_ioctx, 1, iocbs)
    aio_event_map[fd] = me
    res = _YIELD()
    _aio_pending -= 1
    _aio_rp -= 1
    buf = PyBytes_FromStringAndSize (strbuf, nbytes)
    free(strbuf)
    return buf

def aio_write (int fd, object buf, uint64_t offset):
    """Asynchronously write data to a file. fd should be opened in
       O_DIRECT mode by the caller to make this non blocking.

    :Parameters:
        - `fd`: The file descriptor to write to.
        - `buf`: String data to write.
        - `offset`: The offset to write the data.

    :Return:
        Returns the number of bytes written.

    :Exceptions:
        - `OSError`: OS-level error.
    """

    global _aio_pending, _aio_wb, _aio_wnb, _aio_wp, aio_iocb

    cdef object res
    cdef int size, aligned_size
    cdef iocb *piocb
    cdef iocb *iocbs[1]
    cdef void *strbuf

    size = PyBytes_Size(buf)
    aligned_size = _aligned_size(size)

    posix_memalign(&strbuf, BLOCK_SIZE, aligned_size)
    memcpy(strbuf, PyBytes_AS_STRING(buf), size)
    me = the_scheduler._current
    piocb = &aio_iocb[_aio_pending]
    _aio_pending += 1
    _aio_wp += 1
    io_prep_pwrite(piocb, fd, strbuf, aligned_size, offset)
    io_set_eventfd(piocb, aio_eventfd)
    iocbs[0] = piocb
    io_submit(aio_ioctx, 1, iocbs)
    aio_event_map[fd] = me
    res = _YIELD()
    _aio_pending -= 1
    _aio_wp -= 1
    free(strbuf)
    return res
