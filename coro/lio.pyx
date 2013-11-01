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

__lio_version__ = "$Id: //prod/main/ap/shrapnel/coro/lio.pyx#18 $"

from cpython.string cimport PyString_Check, PyString_AS_STRING,\
                            PyString_FromStringAndSize, PyString_Size
from cpython.list cimport PyList_Size, PyList_Append
from cpython.tuple cimport PyTuple_Size
from libc.string cimport strerror
from libc.errno cimport errno

cdef extern from "aio.h":
    int LIO_READ, LIO_WRITE, LIO_NOP, LIO_WAIT, LIO_NOWAIT
    int lio_listio (int mode, aiocb ** list, int nent, sigevent * sig)

# ================================================================================
#                            lio (list i/o)
# ================================================================================

cdef class lio_control_block:
    """Wrapper for 'struct aiocb'.  This structure holds important information
    in place for the kernel while it performs I/O asynchronously."""
    cdef aiocb cb
    cdef object buffer_string

    def __init__ (self, int fd, off_t offset, str_or_size):
        # format of requests...
        # (<fd>, <offset>, <string>) == WRITE
        # (<fd>, <offset>, <size>)   == READ
        memset (&self.cb, 0, sizeof (aiocb))
        self.cb.aio_fildes = fd
        self.cb.aio_offset = offset
        if PyString_Check (str_or_size):
            self.buffer_string = str_or_size
            self.cb.aio_buf = PyString_AS_STRING (str_or_size)
            self.cb.aio_nbytes = PyString_Size (str_or_size)
            self.cb.aio_lio_opcode = LIO_WRITE
        elif PyInt_Check (str_or_size):
            self.buffer_string = PyString_FromStringAndSize (NULL, str_or_size)
            self.cb.aio_buf = PyString_AS_STRING (self.buffer_string)
            self.cb.aio_nbytes = str_or_size
            self.cb.aio_lio_opcode = LIO_READ
        else:
            raise ValueError, "expected (int <fd>, long <offset>, string|size <str_or_size>)"

    def __repr__ (self):
        if self.cb.aio_lio_opcode == LIO_READ:
            kind = 'LIO_READ'
        elif self.cb.aio_lio_opcode == LIO_WRITE:
            kind = 'LIO_WRITE'
        elif self.cb.aio_lio_opcode == LIO_NOP:
            kind = 'LIO_NOP'
        else:
            kind = 'LIO_???'
        return '<%s request on fd=%d for %d bytes @ %r at 0x%x>' % (
            kind,
            self.cb.aio_fildes,
            self.cb.aio_nbytes,
            self.cb.aio_offset,
            <long><void *>self
            )

class lio_listio_error (Exception):
    pass

ctypedef public class lio_request [ object lio_request_object, type lio_request_type ] :
    cdef queue_poller poller
    cdef object coro
    cdef object requests
    cdef int num
    cdef aiocb ** aiocbpl

    def __init__ (self, queue_poller poller, requests):
        cdef int i
        cdef lio_control_block cb
        self.num = PyTuple_Size (requests)
        self.requests = PyTuple_New (self.num)
        for i from 0 <= i < self.num:
            PyTuple_SET_ITEM_SAFE (
                self.requests,
                i,
                lio_control_block (*PyTuple_GET_ITEM_SAFE (requests, i))
            )
        self.poller = poller
        self.aiocbpl = <aiocb **> PyMem_Malloc (sizeof (aiocb *) * self.num)
        if self.aiocbpl == NULL:
            raise MemoryError
        else:
            for i from 0 <= i < self.num:
                # this should generate a type-check?
                cb = PyTuple_GET_ITEM_SAFE (self.requests, i)
                self.aiocbpl[i] = &cb.cb

    def __dealloc__ (self):
        if self.aiocbpl != NULL:
            PyMem_Free (self.aiocbpl)

    cdef submit (self):
        """submit() => None
        submit an lio_listio() call to the kernel, with <udata> as the
        kevent user-data entry.  <requests> must be a list of
        <aio_control_block> objects"""
        cdef int r
        cdef sigevent sig
        sig.sigev_notify = SIGEV_KEVENT
        sig.sigev_notify_kqueue = self.poller.kq_fd
        # ensure that self remains valid until
        # the kernel retires the request.
        Py_INCREF (self)
        sig.sigev_value.sigval_ptr = <void*>self
        r = lio_listio (LIO_NOWAIT, self.aiocbpl, self.num, &sig)
        if r == -1:
            raise_oserror()

    def abort_cleanup(self, unused):
        """Cleanup events after an abort.

        If an LIO request is aborted (such as with coro.Interrupted), the
        kevent is still going to eventually fire.  So we change the target of
        the kevent to be this function instead of the coroutine to do cleanup
        and avoid scheduling the coroutine twice.
        """
        cdef lio_control_block cb
        cdef int i, r

        # this matches the Py_INCREF in submit()
        Py_DECREF (self)

        for i from 0 <= i < self.num:
            cb = self.requests[i]
            r = _aio_return(&cb.cb)
            # Ignoring the return value for now since there's nothing we can
            # really do about it.

    cdef retire (self):
        """retire() => <result-list>
        XXX
        Retire an lio_listio() call started with submit_lio_listio().
        <requests> is the original list of <aio_control_block> objects
        as passed to submit_lio_listio().
        <result-list> is a list of: [(<errno-or-None>, <result>), ...]
        where <result> is a string (for LIO_READ requests) or an integer
        (for LIO_WRITE) requests.  If an error has occurred on any of the
        requests, <lio_listio_error> will be raised, with the result list
        as a value.  In this case examine the <errno-or-None> position of
        each element of the result to determine the error.
        """
        cdef int nr, i, r, all_clear
        cdef lio_control_block cb
        all_clear = 1
        # this matches the Py_INCREF in submit()
        Py_DECREF (self)
        if self.num == 0:
            return []
        else:
            result = PyTuple_New (self.num)
            for i from 0 <= i < self.num:
                # this should generate a type-check?
                cb = PyTuple_GET_ITEM_SAFE (self.requests, i)
                # not needed since we do kqueue -> r = aio_error (&cb.cb)
                r = _aio_return (&cb.cb)
                if r == -1:
                    PyTuple_SET_ITEM_SAFE (result, i, OSError(errno, strerror(errno)))
                    all_clear = 0
                else:
                    if cb.cb.aio_lio_opcode == LIO_WRITE:
                        # r is number of bytes written.
                        PyTuple_SET_ITEM_SAFE (result, i, r)
                    elif cb.cb.aio_lio_opcode == LIO_READ:
                        PyTuple_SET_ITEM_SAFE (result, i, cb.buffer_string[:r])
                    elif cb.cb.aio_lio_opcode == LIO_NOP:
                        # why would someone use this?
                        PyTuple_SET_ITEM_SAFE (result, i, None)
                    else:
                        # users can't create an aio_control_block with
                        # an invalid opcode, but Just In Case...
                        PyTuple_SET_ITEM_SAFE (result, i, None)
            if all_clear:
                return result
            else:
                # at least one operation failed.
                raise lio_listio_error (result)

def pack_blocks_for_write (strings, int block_size):
    """Translate a list of strings into a list of strings of a certain block
    size.

    This will take the list of strings you provide and coalesce strings that
    are smaller than `block_size` into blocks of that size, and break strings
    that are bigger than `block_size`.  The result should be a list of strings
    that are exactly `block_size` in size except for the last element which may
    be equal to or less than `block_size`.

    :Parameters:
        - `strings`: A list of string objects.
        - `block_size`: The maximum block size.

    :Return:
        Returns a list of strings.
    """
    "pack <strings> into blocks of <block_size> with minimal copying"
    cdef int n, i, s, total, n_blocks, buffer_left, total_left, left, spos
    cdef char * buffer
    total = 0
    n = PyList_Size (strings)
    for i from 0 <= i < n:
        ob = PyList_GET_ITEM_SAFE (strings, i)
        total = total + PyString_Size (ob)
    result = []
    total_left = total
    i = 0
    spos = 0
    while total_left > 0:
        if total_left < block_size:
            buffer_left = total_left
        else:
            buffer_left = block_size
        buffer_object = PyString_FromStringAndSize (NULL, buffer_left)
        buffer = PyString_AS_STRING (buffer_object)
        left = buffer_left
        while left:
            # how big is the current string?
            ob = PyList_GET_ITEM_SAFE (strings, i)
            s = PyString_Size (ob)
            # how much of it is left to write?
            s = s - spos
            if s <= left:
                # write all of what's left of ob
                memcpy (buffer, PyString_AS_STRING (ob) + spos, s)
                # scoot buffer pointer
                buffer = buffer + s
                left = left - s
                spos = 0
                # point to next string in list
                i = i + 1
            else:
                # write a portion of what's left of ob
                memcpy (buffer, PyString_AS_STRING (ob) + spos, left)
                spos = spos + left
                buffer = buffer + left
                left = 0
        # buffer should be full, now.
        PyList_Append (result, buffer_object)
        total_left = total_left - buffer_left
    return result

cdef long _lio_pending
_lio_pending = 0

cdef lio_read (requests):
    """Perform many ``aio_read`` calls using the ``lio_listio`` facility.

    :Parameters:
        - `requests`: A list of ``(fd, offset, size)`` tuples where ``fd`` is
          the file descriptor to read from, ``offset`` is the position to read
          from, and ``size`` is the number of bytes to read.

    :Return:
        Returns a list of strings that correspond to the requested blocks.

    :Exceptions:
        - `OSError`: OS-level error.
    """
    global _lio_pending
    # XXX need to have an exception handler here, and an ability to cancel
    #     the outstanding I/O (if possible).  [for example, what if a timeout
    #     expires while waiting on this read?]
    cdef lio_request request
    cdef coro me
    cdef kevent_target kt

    me = the_scheduler._current
    request = lio_request (the_poller, requests)
    # 0 because we're not in the changelist.
    kt = kevent_target (me, 0)
    kt.flags = KTARGET_FLAG_ONESHOT
    the_poller.set_event_target (
        (<uintptr_t>(request.aiocbpl), EVFILT_LIO),
        kt
        )
    request.submit()
    _lio_pending = _lio_pending + 1
    try:
        try:
            me.__yield ()
        except:
            kt.target = request.abort_cleanup
            raise
        return request.retire()
    finally:
        _lio_pending = _lio_pending - 1

cdef lio_write (requests):
    """Perform many ``aio_write`` calls using the ``lio_listio`` facility.

    :Parameters:
        - `requests`: A list of ``(fd, offset, string)`` tuples where ``fd`` is
          the file descriptor to write to, ``offset`` is the position to write
          to, and ``string`` is the string of data to write.

    :Return:
        Returns the total number of bytes written.

    :Exceptions:
        - `OSError`: OS-level error.
    """
    global _lio_pending
    # XXX need to have an exception handler here, and an ability to cancel
    #     the outstanding I/O (if possible).  [for example, what if a timeout
    #     expires while waiting on this write?]
    cdef lio_request request
    cdef coro me
    cdef long total_bytes
    cdef kevent_target kt

    me = the_scheduler._current
    request = lio_request (the_poller, requests)
    # 0 because we're not in the changelist.
    kt = kevent_target (me, 0)
    kt.flags = KTARGET_FLAG_ONESHOT
    the_poller.set_event_target (
        (<uintptr_t>(request.aiocbpl), EVFILT_LIO),
        kt
        )
    request.submit()
    _lio_pending = _lio_pending + 1
    try:
        try:
            me.__yield ()
        except:
            kt.target = request.abort_cleanup
            raise
        result = request.retire()
        total_bytes = 0
        for bytes in result:
            total_bytes = total_bytes + bytes
        return total_bytes
    finally:
        _lio_pending = _lio_pending - 1

# Maximum number of blocks that can be submitted at once.
cdef int _MAX_LIO
_MAX_LIO = get_sysctl_int ('p1003_1b.aio_listio_max')
MAX_LIO = _MAX_LIO

# Maximum size of a block.  This is a restriction from raw-disk I/O.
# Different disk drivers have different limits (see si_iosize_max in the
# kernel), but 64k is safe all around, and larger sizes don't really help
# performance.
#
# We subtract 1 disk block (512) to avoid Python's string overhead from
# creating strings that are actually 96k due to malloc size bump.
cdef int _MAX_AIO_SIZE
_MAX_AIO_SIZE = ((64 * 1024) - 512)
MAX_AIO_SIZE = _MAX_AIO_SIZE

def many_lio_reads (int fd, off_t pos, int bytes):
    """Read from a file descriptor using LIO to break up a large request into
    smaller blocks.

    This will take a read request of any size and break it into requests of at
    most ``MAX_AIO_SIZE`` byte blocks.  This may possibly issue multiple lio
    reads if there are more than ``MAX_LIO`` blocks.

    :Parameters:
        - `fd`: The file descriptor to read from.
        - `pos`: The position to read from.
        - `bytes`: The number of bytes to read.

    :Return:
        Returns a list of strings that were read.
    """
    cdef int total_blocks
    cdef int block_index
    cdef off_t cur_pos
    cdef int n
    cdef int bytes_left
    cdef int batch_size
    cdef int request_index
    cdef int result_index

    # Determine the total number of blocks that it needs to be split into.
    total_blocks = (bytes / _MAX_AIO_SIZE)
    if bytes % _MAX_AIO_SIZE:
        # Extra partial block.
        total_blocks = total_blocks + 1

    result = PyList_New(total_blocks)

    block_index = 0
    bytes_left = bytes
    cur_pos = pos
    result_index = 0
    while block_index < total_blocks:
        # Determine how big this batch is and build a request tuple.
        batch_size = IMIN(_MAX_LIO, total_blocks-block_index)
        request = PyTuple_New(batch_size)
        for request_index from 0 <= request_index < batch_size:
            block_size = IMIN(_MAX_AIO_SIZE, bytes_left)
            PyTuple_SET_ITEM_SAFE(request, request_index, (fd, cur_pos, block_size))
            cur_pos = cur_pos + block_size
            bytes_left = bytes_left - block_size
        block_index = block_index + batch_size
        # Issue the request.
        batch_result = lio_read(request)
        # Add the batch results to our final result.
        for n from 0 <= n < batch_size:
            item = PyTuple_GET_ITEM_SAFE(batch_result, n)
            PyList_SET_ITEM_SAFE(result, result_index, item)
            result_index = result_index + 1

    return result

def many_lio_writes (fd, off_t pos, blocks):
    """Write to a file descriptor using LIO to break up a large request into smaller blocks.

    This will take a list of strings to write, and call `lio_write` repeatedly
    with at most ``MAX_LIO`` entries until all blocks have been written.

    Note that this does not verify that the blocks you are writing do not
    exceed any limits, so you should make sure that you are writing blocks of
    the correct size.

    :Parameters:
        - `fd`: The file descriptor to write to.
        - `pos`: The position to write to.
        - `blocks`: A list of strings to write.

    :Return:
        Returns the total number of bytes written.
    """
    cdef long total_bytes
    cdef int i, n

    total_bytes = 0
    n = PyList_Size (blocks)
    args = PyTuple_New (n)
    for i from 0 <= i < n:
        block = PyList_GetItem_SAFE (blocks, i)
        PyTuple_SET_ITEM_SAFE (args, i, (fd, pos, block))
        pos = pos + PyString_Size (block)
    i = 0
    while i < n:
        total_bytes = total_bytes + lio_write (args[i:i+_MAX_LIO])
        i = i + _MAX_LIO
    return total_bytes
