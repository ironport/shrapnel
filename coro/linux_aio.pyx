# -*- Mode: Python -*-
#
# This module provides asynchronous, non blocking disk io support in Linux via libaio.
# For most of the cases one can live with blocking io on Linux since it is buffered and
# this is useful only if you need direct control of disk io and have your own cache etc.
#
# Asynchronous disk io support in Linux is not as good as in FreeBSD. There are bunch of
# options (posix aio, libeio) which uses userland threads to mimic this. This module uses
# libaio which does not need such dependancies and ties the event handling with epoll with
# an eventfd.
#
# libaio asynchronous APIs need the offset and size of reads and writes to be
# block-aligned (512 bytes) on 2.6+ kernels. Consequently this works best when
# the caller takes this into consideration. Currently aio_read() supports any
# offset/size, but aio_write() needs the offset to be aligned.
#
# Note: this file is included by <coro.pyx> if libaio is available.
#

from cpython.bytes cimport PyBytes_FromStringAndSize, PyBytes_Check, PyBytes_AS_STRING

cdef extern from "stdlib.h":
    int posix_memalign(void **memptr, size_t alignment, size_t size)
    void free(void *ptr)

cdef extern from "libaio.h":
    ctypedef struct io_context_t:
        pass

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
cdef coro aio_poller
cdef io_context_t aio_ioctx
cdef dict aio_event_map
cdef iocb aio_iocb[MAX_PENDING_REQS]

cdef _spawn_first(fun):
    # Spawn this function before other pending coros
    cdef coro co

    id = get_coro_id()
    co = coro (fun, [], {}, id)
    _all_threads[id] = co
    co.scheduled = 1
    the_scheduler.pending.insert(0, (co, None))
    return co

cdef aio_setup():
    cdef int res
    global aio_eventfd, aio_poller, aio_event_map

    res = io_setup(MAX_PENDING_REQS, &aio_ioctx)
    if res:
        raise_oserror_with_errno(res)
    aio_eventfd = eventfd(0, EFD_NONBLOCK)
    if aio_eventfd == -1:
        raise_oserror()
    aio_event_map = {}
    # _aio_poll needs to run first to listen for events
    aio_poller = _spawn_first(_aio_poll)

cdef aio_teardown():
    cdef int res
    
    aio_poller.shutdown()
    close(aio_eventfd)
    res = io_destroy(aio_ioctx)
    if res:
        raise_oserror_with_errno(res)

def _aio_poll():
    cdef int r, fd, res
    cdef long n
    cdef coro co
    cdef io_event aio_io_events[MAX_PENDING_REQS]

    while 1:
        try:
            the_poller._wait_for_read(aio_eventfd)
            read(aio_eventfd, <char*>&n, 8)
            if n < 1 or n > MAX_PENDING_REQS:
                raise_oserror()
            r = io_getevents(aio_ioctx, 1, n, aio_io_events, NULL)
            if r < 0:
                raise_oserror()
            for i from 0 <= i < r:
                fd = aio_io_events[i].obj.aio_fildes
                res = aio_io_events[i].res
                co = aio_event_map.pop(fd)
                co._schedule(res)
        except Shutdown:
            break

cdef _align(size, forward=True):
    extra = size % BLOCK_SIZE
    if extra:
        return size - extra + BLOCK_SIZE if forward else size - extra
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
    cdef int aligned_size, aligned_offset
    cdef iocb *piocb
    cdef iocb *iocbs[1]
    cdef char *strbuf

    aligned_offset = _align(offset, forward=False)
    aligned_size = _align(offset+nbytes-aligned_offset)
    res = posix_memalign(<void**>&strbuf, BLOCK_SIZE, aligned_size)
    if res:
        raise_oserror_with_errno(res)
    me = the_scheduler._current
    piocb = &aio_iocb[_aio_pending]
    _aio_pending += 1
    _aio_rp += 1
    io_prep_pread(piocb, fd, strbuf, aligned_size, aligned_offset)
    io_set_eventfd(piocb, aio_eventfd)
    iocbs[0] = piocb
    res = io_submit(aio_ioctx, 1, iocbs)
    if res <= 0:
        raise_oserror_with_errno(res)
    aio_event_map[fd] = me
    res = _YIELD()
    if res <= 0:
        raise_oserror()
    assert res >= nbytes
    _aio_pending -= 1
    _aio_rp -= 1
    buf = PyBytes_FromStringAndSize (strbuf, aligned_size)
    free(strbuf)
    return buf[offset-aligned_offset:offset-aligned_offset+nbytes]

def aio_write (int fd, object buf, uint64_t offset):
    """Asynchronously write data to a file. fd should be opened in
       O_DIRECT mode by the caller to make this non blocking.

    :Parameters:
        - `fd`: The file descriptor to write to.
        - `buf`: String data to write.
        - `offset`: The offset to write data. Must be multiple of BLOCK_SIZE.

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

    assert not offset % BLOCK_SIZE

    size = PyBytes_Size(buf)
    aligned_size = _align(size)

    res = posix_memalign(&strbuf, BLOCK_SIZE, aligned_size)
    if res:
        raise_oserror_with_errno(res)
    memcpy(strbuf, PyBytes_AS_STRING(buf), size)
    me = the_scheduler._current
    piocb = &aio_iocb[_aio_pending]
    _aio_pending += 1
    _aio_wp += 1
    io_prep_pwrite(piocb, fd, strbuf, aligned_size, offset)
    io_set_eventfd(piocb, aio_eventfd)
    iocbs[0] = piocb
    res = io_submit(aio_ioctx, 1, iocbs)
    if res <= 0:
        raise_oserror_with_errno(res)
    aio_event_map[fd] = me
    res = _YIELD()
    if res <= 0:
        raise_oserror()
    assert res == aligned_size
    _aio_pending -= 1
    _aio_wp -= 1
    free(strbuf)
    return size
