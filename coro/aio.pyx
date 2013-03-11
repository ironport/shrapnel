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

# -*- Mode: Pyrex -*-

__aio_version__ = "$Id: //prod/main/ap/shrapnel/coro/aio.pyx#19 $"

# XXX todo - tests: coverage, performance, leak.

from cpython.bytes cimport PyBytes_FromStringAndSize, PyBytes_Check, PyBytes_AS_STRING
from libc cimport errno

cdef extern from "signal.h":

    cdef union sigval:
        int sigval_int
        void * sigval_ptr

    cdef struct sigevent:
        int sigev_notify
        int sigev_notify_kqueue # actually a union
        sigval sigev_value

    int SIGEV_KEVENT

cdef extern from "aio.h":

    cdef struct aiocb:
        int      aio_fildes
        off_t    aio_offset
        char *   aio_buf
        size_t   aio_nbytes
        sigevent aio_sigevent
        int      aio_lio_opcode
        int      aio_reqprio

    int _aio_read "aio_read" (aiocb * cb)
    int _aio_write "aio_write" (aiocb * cb)
    int _aio_error "aio_error" (aiocb * cb)
    int _aio_return "aio_return" (aiocb * cb)

# ================================================================================
#                        aio (asynchronous i/o)
# ================================================================================

cdef class aio_control_block:
    """Wrapper for 'struct aiocb'.  This structure holds important information
    in place for the kernel while it performs I/O asynchronously."""
    cdef aiocb cb
    cdef object buffer_string

    def __init__ (self, int kq_fd, int fd, uint64_t offset, str_or_size):
        memset (&self.cb, 0, sizeof (aiocb))
        self.cb.aio_fildes = fd
        self.cb.aio_offset = offset
        self.cb.aio_sigevent.sigev_notify = SIGEV_KEVENT
        self.cb.aio_sigevent.sigev_notify_kqueue = kq_fd
        if PyBytes_Check (str_or_size):
            self.buffer_string = str_or_size
            self.cb.aio_buf = PyBytes_AS_STRING (str_or_size)
            self.cb.aio_nbytes = PyBytes_Size (str_or_size)
        elif PyInt_Check (str_or_size):
            self.buffer_string = PyBytes_FromStringAndSize (NULL, str_or_size)
            self.cb.aio_buf = PyBytes_AS_STRING (self.buffer_string)
            self.cb.aio_nbytes = str_or_size
        else:
            raise ValueError, "expected (int <kq_fd>, int <fd>, long <offset>, bytes|size <str_or_size>)"

    def __repr__ (self):
        return '<aiocb on fd=%d for %d bytes @ %r at 0x%x>' % (
            self.cb.aio_fildes,
            self.cb.aio_nbytes,
            self.cb.aio_offset,
            <long><void *>self
            )

    def abort_cleanup(self, unused):
        """Cleanup AIO data structure after an abort.

        If an AIO request is aborted (such as with coro.Interrupted), the
        kevent is still going to eventually fire.  So we change the target of
        the kevent to be this function instead of the coroutine to do cleanup
        and avoid scheduling the coroutine twice.
        """
        cdef int r
        r = _aio_return (&self.cb)
        # Ignoring the return value for now since there's nothing we can really
        # do about it.


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
    """Asynchronously read data from a file.

    :Parameters:
        - `fd`: The file descriptor to read from.
        - `nbytes`: The number of bytes to read.
        - `offset`: The offset to read from.

    :Return:
        Returns a string of data read from the file.

    :Exceptions:
        - `OSError`: OS-level error.
    """
    global _aio_pending, _aio_rb, _aio_rnb, _aio_rp
    cdef aio_control_block cb
    cdef int r
    cdef coro me
    cdef kevent_target kt
    me = the_scheduler._current
    cb = aio_control_block (the_poller.kq_fd, fd, offset, nbytes)
    r = _aio_read (&cb.cb)
    if r:
        raise_oserror()
    else:
        r = _aio_error (&cb.cb)
        if r == errno.EINPROGRESS:
            # delayed async operation
            # 0 because we're not in the changelist.
            kt = kevent_target (me, 0)
            kt.flags = KTARGET_FLAG_ONESHOT
            the_poller.set_event_target (
                # (ident, filter) == (&cb, EVFILT_AIO)
                (<uintptr_t>&cb.cb, EVFILT_AIO),
                kt
                )
            # wait for the kevent to wake us up
            _aio_rp = _aio_rp + 1
            _aio_pending = _aio_pending + 1
            me = the_scheduler._current
            try:
                try:
                    me.__yield ()
                except:
                    kt.target = cb.abort_cleanup
                    raise
            finally:
                _aio_rb = _aio_rb + 1
                _aio_rp = _aio_rp - 1
                _aio_pending = _aio_pending - 1
        elif r == -1:
            # According to the manpage, this can only happen with EINVAL
            # where the iocb is an invalid pointer.  This should never happen.
            raise_oserror()
        elif r:
            # Call aio_return to clean up kernel data structures.
            # This will delete the kevent so we don't need to yield.
            _aio_return (&cb.cb)
            raise_oserror_with_errno(r)
        else:
            _aio_rnb = _aio_rnb + 1
        # success - return result string
        r = _aio_return (&cb.cb)
        if r == -1:
            raise_oserror()
        return cb.buffer_string[:r]

def aio_write (int fd, object buffer, uint64_t offset):
    """Asynchronously write data to a file.

    :Parameters:
        - `fd`: The file descriptor to write to.
        - `buffer`: String data to write.
        - `offset`: The offset to write the data.

    :Return:
        Returns the number of bytes written.

    :Exceptions:
        - `OSError`: OS-level error.
    """
    global _aio_pending, _aio_wb, _aio_wnb, _aio_wp
    cdef aio_control_block cb
    cdef int r
    cdef coro me
    cdef kevent_target kt
    cdef kevent_key kk

    me = the_scheduler._current
    cb = aio_control_block (the_poller.kq_fd, fd, offset, buffer)
    r = _aio_write (&cb.cb)
    if r:
        raise_oserror()
    else:
        r = _aio_error (&cb.cb)
        if r == errno.EINPROGRESS:
            # delayed async operation
            # wait for the kevent to wake us up
            # 0 because we're not in the changelist.
            kt = kevent_target (me, 0)
            kt.flags = KTARGET_FLAG_ONESHOT
            the_poller.set_event_target (
                # (ident, filter) == (&cb, EVFILT_AIO)
                (<uintptr_t>&cb.cb, EVFILT_AIO),
                kt
                )
            _aio_wp = _aio_wp + 1
            _aio_pending = _aio_pending + 1
            me = the_scheduler._current
            try:
                try:
                    me.__yield ()
                except:
                    kt.target = cb.abort_cleanup
                    raise
            finally:
                _aio_wb = _aio_wb + 1
                _aio_wp = _aio_wp - 1
                _aio_pending = _aio_pending - 1
        elif r == -1:
            # According to the manpage, this can only happen with EINVAL
            # where the iocb is an invalid pointer.  This should never happen.
            raise_oserror()
        elif r:
            # Call aio_return to clean up kernel data structures.
            # This will delete the kevent so we don't need to yield.
            _aio_return (&cb.cb)
            raise_oserror_with_errno(r)
        else:
            _aio_wnb = _aio_wnb + 1
        # success - return result
        r = _aio_return (&cb.cb)
        if r == -1:
            raise_oserror()
        return r
