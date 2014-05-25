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
# $Header: //prod/main/ap/shrapnel/coro/socket.pyx#57 $

__socket_version__ = "$Id: //prod/main/ap/shrapnel/coro/socket.pyx#57 $"

# Note: this file is included by <coro.pyx>

DEF KQUEUE = (UNAME_SYSNAME == "FreeBSD" or UNAME_SYSNAME == "Darwin")

# ================================================================================
#                                socket
# ================================================================================

import socket as __socketmodule

from cpython.int cimport PyInt_Check
from cpython.bytes cimport PyBytes_Size, PyBytes_AsString
from cpython.tuple cimport PyTuple_New, PyTuple_SET_ITEM, PyTuple_GET_ITEM

from libc cimport errno

cdef int min (int a, int b):
    if a < b:
        return a
    else:
        return b

# Number of socket objects.  Note that this also includes closed socket objects.
cdef int live_sockets

live_sockets = 0

cdef _readv_compute(list size_list, tuple buffer_tuple, int n, int received, iovec * iov,
                    int * left, int * iov_pos, int * complete_index, int * partial_size):
    """Compute the IO Vector for the readv method.

    This will take the list of read calls requested by the user, and taking
    into consideration what has been received so far will create an iovec array
    for the readv function.

    :param size_list: A Python object that should be a sequence of integers
          that indicate which blocks are being requested.
    :param buffer_tuple: A tuple of Python strings (should be already
          allocated and should be the same length as size_list).
    :param n: The length of size_list and buffer_tuple.
    :param received: The number of bytes received so far.
    :param iov: The ``iovec`` array.  This should have ``n`` elements.
    :param left: OUTPUT: The number of bytes left to read.
    :param iov_pos: OUTPUT: The number of elements added to ``iov``.
    :param complete_index: The index of the last element in the buffer tuple
          that has been *completely* received.  -1 if nothing has been
          completely received.
    :param partial_index: The index of the element in the buffer tuple that
          has partially received some data.  -1 if none of the elements have
          partial data.
    """
    cdef int i
    cdef int size
    cdef bytes buffer
    iov_pos[0] = 0
    left[0] = 0
    complete_index[0] = -1
    partial_size[0] = -1
    for i from 0 <= i < n:
        size = size_list[i]
        buffer = buffer_tuple[i]
        Py_INCREF(buffer)
        if received >= left[0] + size:
            # This buffer has been completely received.
            complete_index[0] = i
        elif received > left[0]:
            # This buffer has been partially received.
            partial_size[0] = (received - left[0])
            iov[iov_pos[0]].iov_base = <void *> buffer + partial_size[0]
            iov[iov_pos[0]].iov_len = size - partial_size[0]
            iov_pos[0] = iov_pos[0] + 1
        else:
            # This buffer still needs data.
            iov[iov_pos[0]].iov_base = <void *> buffer
            iov[iov_pos[0]].iov_len = size
            iov_pos[0] = iov_pos[0] + 1
        left[0] = left[0] + size
    left[0] = left[0] - received

cdef public class sock [ object sock_object, type sock_type ]:

    """
    Coro socket object.

    This is typically used for network sockets, but can also be used for
    coro-safe IO on any file descriptor that supports kqueue non-blocking
    operations.

    The constructor takes the following parameters:

    :param domain: The socket domain family, defaults to AF_INET (see :class:`AF`).
    :param stype: The socket type, defaults to SOCK_STREAM (see :class:`SOCK`).
    :param protocol: The socket protocol (normally not used, defaults to 0).
    :param fd: The file descriptor to use.  Creates a new socket file
          descriptor if not specified.

    :ivar fd: The file descriptor number.  Set to -1 when the socket is
          closed.
    :ivar orig_fd: The original file descriptor number.  This is left for
          debugging purposes to determine which file descriptor was in use
          before the socket was closed.
    :ivar domain: The socket domain (AF_INET, AF_UNIX, AF_UNSPEC).
    :ivar stype: The socket type (SOCK_STREAM, SOCK_DGRAM)
    """

    #cdef public int fd, orig_fd, domain, stype

    def __init__ (self, int domain=AF_INET, int stype=SOCK_STREAM, int protocol=0, int fd=-1):
        global live_sockets
        if fd == -1:
            fd = socket (domain, stype, protocol)
            if fd == -1:
                raise_oserror()
        the_poller.notify_of_close (fd)
        self.fd = fd
        self.orig_fd = fd
        self.domain = domain
        self.stype = stype
        self.set_nonblocking()
        live_sockets = live_sockets + 1

    def __repr__ (self):
        return '<%s fd=%d/%d domain=%d type=%d at 0x%x>' % (
            self.__class__.__name__,
            self.fd,
            self.orig_fd,
            self.domain,
            self.stype,
            <long><void *>self
            )

    def __dealloc__ (self):
        global live_sockets
        live_sockets = live_sockets - 1
        if self.fd != -1:
            close (self.fd)
            self.fd = -1

    cdef int _try_selfish(self) except -1:
        cdef coro me

        if self.fd == -1:
            raise ClosedError

        me = <coro>the_scheduler._current
        return me.try_selfish()

    def get_fileno (self):
        """Get the current file descriptor.

        :returns: The current file descriptor number.  Returns -1 if the
            socket is closed.
        """
        warnings.warn('socket.get_fileno() is deprecated, use fileno() instead.', DeprecationWarning)
        return self.fd

    def fileno (self):
        """Get the current file descriptor.

        :returns: The current file descriptor number.  Returns -1 if the
            socket is closed.
        """
        return self.fd

    cdef _set_reuse_addr (self):
        cdef int old = 0
        cdef socklen_t optlen
        optlen = sizeof (old)
        getsockopt (self.fd, SOL_SOCKET, SO_REUSEADDR, <void*> &old, &optlen)
        old = old | 1
        setsockopt (self.fd, SOL_SOCKET, SO_REUSEADDR, <void*> &old, optlen)

    def set_reuse_addr (self):
        """Set the SO_REUSEADDR socket option."""
        self._set_reuse_addr()

    cdef set_nonblocking (self):
        cdef int flag
        flag = fcntl (self.fd, F_GETFL, 0)
        if flag == -1:
            raise_oserror()
        elif fcntl (self.fd, F_SETFL, flag | O_NONBLOCK) == -1:
            raise_oserror()

    def getsockopt (self, int level, int optname, socklen_t buflen=0):
        """Get a socket option.

        :param level: The socket level to get (see :class:`SOL`).
        :param optname: The socket option to get (see :class:`SO`).
        :param buflen: The size of the buffer needed to retrieve the value. If
              not specified, it assumes the result is an integer and will
              return an integer.  Otherwise, it will create a new string with
              the result, and you may use the struct module to decode it.

        :returns: An integer if ``buflen`` is zero, otherwise returns a string.

        :raises OSError: OS-level error.
        """
        cdef int flag, r
        cdef socklen_t flagsize
        cdef bytes s
        if buflen == 0:
            flag = 0
            flagsize = sizeof (flag)
            r = getsockopt (self.fd, level, optname, <void*>&flag, &flagsize)
            if r == -1:
                raise_oserror()
            else:
                return flag
        else:
            s = PyBytes_FromStringAndSize (NULL, buflen)
            r = getsockopt (self.fd, level, optname, <void*>PyBytes_AsString (s), &buflen)
            if r == -1:
                raise_oserror()
            else:
                return PyBytes_FromStringAndSize (s, buflen)

    def setsockopt (self, int level, int optname, value):
        """Set a socket option.

        :param level: The socket level to set (see :class:`SOL`).
        :param optname: The socket option to set (see :class:`SO`).
        :param value: The value to set.  May be an integer, or a struct-packed string.

        :raises OSError: OS-level error.
        """
        cdef int flag, r
        cdef socklen_t optlen
        if PyInt_Check (value):
            flag = value
            r = setsockopt (self.fd, level, optname, <void*>&flag, sizeof (flag))
        else:
            optlen = PyBytes_Size (value) # does typecheck
            r = setsockopt (self.fd, level, optname, <void*>PyBytes_AsString (value), optlen)
        if r == -1:
            raise_oserror()

    def close (self):
        """Close the socket.

        It is safe to call this if the socket is already closed.

        :raises OSError: OS-level error.
        """
        cdef int r
        if self.fd != -1:
            r = close (self.fd)
            if r == 0 or (errno.errno == errno.ECONNRESET or errno.errno == errno.ENOTCONN):
                self.fd = -1
                the_poller.notify_of_close (self.orig_fd)
                # XXX: if we are a listening AF_UNIX socket,
                #   it'd be really handy if we automatically
                #   unlink()ed the file here...
            else:
                raise_oserror()

    cpdef int send (self, bytes data) except -1:
        """Send data on the socket.

        This will repeatedly call write to ensure all data has been sent. This
        will raise OSError if it is unable to send all data.

        :param data: The data to send.

        :returns: The number of bytes sent, which should always be the length
            of ``data``.

        :raises OSError: OS-level error.
        """
        cdef char * buffer
        cdef int r, left, sent

        sent = 0
        left = len(data)
        buffer = data
        while left > 0:
            if self._try_selfish() == 1:
                r = write (self.fd, buffer, left)
                #r = send (self.fd, buffer, left, 0)
            else:
                r = -1
                errno.errno = errno.EAGAIN
            if r == -1:
                if errno.errno == errno.EAGAIN:
                    # XXX kqueue can tell us exactly how much
                    #     room is available, is this useful?
                    self._wait_for_write()
                else:
                    raise_oserror()
            else:
                left = left - r
                sent = sent + r
                buffer = buffer + r
                if left == 0:
                    return sent

    cpdef int sendall(self, bytes data) except -1:
        """Send all data.

        This is an alias for the :meth:`send` method.
        """
        return self.send(data)

    cpdef int write (self, bytes data) except -1:
        """Write data.

        This is an alias for the :meth:`send` method.
        """
        return self.send(data)

    cpdef int sendto (self, bytes data, address, int flags=0) except -1:
        """Send data to a specific address.

        :param data: The data to send.
        :param address: The address to send to.  For unix-domain sockets, this
              is a string.  For IP sockets, this is a tuple ``(IP, port)``
              where IP is a string.
              Port is always an integer.
        :param flags: sendto flags to use (defaults to 0) (see sendto(2)
              manpage).

        :returns: The number of bytes sent which may be less than the send
            requested.

        :raises OSError: OS-level error.
        """
        cdef char * buffer
        cdef sockaddr_storage sa
        cdef socklen_t addr_len
        cdef int r

        memset (&sa, 0, sizeof (sockaddr_storage))
        self.parse_address (address, &sa, &addr_len)
        buffer = data
        while 1:
            if self._try_selfish() == 1:
                r = sendto (self.fd, buffer, len(data), flags, <sockaddr*>&sa, addr_len)
            else:
                r = -1
                errno.errno = errno.EAGAIN
            if r == -1:
                if errno.errno == errno.EAGAIN:
                    # XXX kqueue can tell us exactly how much
                    #     room is available, is this useful?
                    self._wait_for_write()
                else:
                    raise_oserror()
            else:
                return r

    cpdef bytes recv (self, int buffer_size):
        """Receive data.

        This may return less data than you request if the socket buffer is not
        large enough.  Use :meth:`recv_exact` to ensure you receive exactly the
        amount requested.

        :param buffer_size: The number of bytes to receive.

        :returns: A string of data.  Returns the empty string when the end of
            the stream is reached.

        :raises OSError: OS-level error.
        """
        cdef bytes buffer
        cdef int r, new_buffer_size
        cdef char * p

        buffer = PyBytes_FromStringAndSize (NULL, buffer_size)
        p = buffer
        while 1:
            if self._try_selfish() == 1:
                r = read (self.fd, p, buffer_size)
            else:
                r = -1
                errno.errno = errno.EAGAIN
            if r == -1:
                if errno.errno == errno.EAGAIN:
                    # kqueue will tell us exactly how many bytes are waiting for us.
                    new_buffer_size = min (self._wait_for_read(), buffer_size)
                    IF KQUEUE:
                        # kqueue will tell us exactly how many bytes are waiting for us.
                        if new_buffer_size != buffer_size:
                            buffer = PyBytes_FromStringAndSize (NULL, new_buffer_size)
                            buffer_size = new_buffer_size
                            p = buffer
                else:
                    raise_oserror()
            elif r == 0:
                return b''
            elif r == buffer_size:
                return buffer
            else:
                return PyBytes_FromStringAndSize (buffer, r)

    cpdef bytes read (self, int buffer_size):
        """Read data.

        This is an alias for the :meth:`recv` method.
        """
        return self.recv (buffer_size)

    cpdef recvfrom (self, int buffer_size, int flags=0):
        """Receive data.

        This may return less data than you request if the socket buffer is not
        large enough.

        :param buffer_size: The number of bytes to receive.
        :param flags: Socket flags to set (defaults to 0) (see recvfrom(2)
              manpage).

        :returns: A tuple ``(data, address)`` where data is a string and
            address is the address of the remote side (string for unix-domain,
            tuple of ``(IP, port)`` for IP where IP is a string and port is an
            integer).  Data is the empty string when the end of the stream is
            reached.

        :raises OSError: OS-level error.
        """
        cdef bytes buffer
        cdef sockaddr_storage sa
        cdef int r, new_buffer_size
        cdef socklen_t addr_len
        cdef char * p

        buffer = PyBytes_FromStringAndSize (NULL, buffer_size)
        p = buffer
        while 1:
            if self._try_selfish() == 1:
                addr_len = sizeof (sockaddr_storage)
                memset (&sa, 0, sizeof (sockaddr_storage))
                r = recvfrom (self.fd, <void*>p, buffer_size, flags, <sockaddr*>&sa, &addr_len)
            else:
                r = -1
                errno.errno = errno.EAGAIN
            if r == -1:
                if errno.errno == errno.EAGAIN:
                    # kqueue will tell us exactly how many bytes are waiting for us.
                    new_buffer_size = min (self._wait_for_read(), buffer_size)
                    IF KQUEUE:
                        # kqueue will tell us exactly how many bytes are waiting for us.
                        if new_buffer_size != buffer_size:
                            buffer = PyBytes_FromStringAndSize (NULL, new_buffer_size)
                            buffer_size = new_buffer_size
                            p = buffer
                else:
                    raise_oserror()
            else:
                address = self.unparse_address (&sa, addr_len)
                if r == 0:
                    result = ''
                elif r == buffer_size:
                    result = buffer
                else:
                    result = PyBytes_FromStringAndSize (buffer, r)
                return (result, address)

    cpdef bytes recv_exact (self, int nbytes):
        """Receive exactly the number of bytes requested.

        This will repeatedly call read until all data is received.

        :param bytes: The number of bytes to receive.

        :returns: The data as a string.

        :raises OSError: OS-level error.
        :raises EOFError: Not all data could be read.  The first argument
              includes any partial data read as a string.
        """
        cdef char * p
        cdef char * p0
        cdef int r
        cdef bytes buffer

        buffer = PyBytes_FromStringAndSize (NULL, nbytes)
        p = buffer
        p0 = p
        while nbytes:
            if self._try_selfish() == 1:
                r = read (self.fd, p, nbytes)
            else:
                r = -1
                errno.errno = errno.EAGAIN
            if r == -1:
                if errno.errno == errno.EAGAIN:
                    self._wait_for_read()
                else:
                    raise_oserror()
            elif r == 0:
                raise EOFError, PyBytes_FromStringAndSize (buffer, p - p0)
            else:
                nbytes -= r
                p = p + r
        return buffer

    cpdef readv (self, list size_list):
        """Read a vector array of data.

        This will repeatedly call readv until all data is received. If the end
        of the stream is reached before all data is received, then the result
        tuple will only contain the elements competely or partially received.

        :param size_list: A sequence of integers that indicates the buffer
              sizes to read.

        :returns: A tuple of strings corresponding to the sizes requested in
            ``size_list``.

        :raises OSError: OS-level error.
        """
        cdef int n, i
        cdef int iov_pos
        cdef int size
        cdef iovec * iov
        cdef int rc
        cdef int received
        cdef int left
        cdef int complete_index
        cdef int partial_size
        cdef bytes buffer, new_buffer
        cdef tuple buffer_tuple, new_buffer_tuple

        received = 0

        n = len (size_list)
        iov = <iovec *> PyMem_Malloc(sizeof(iovec) * n)
        # Prepare string buffers in which to read the result.
        buffer_tuple = PyTuple_New(n)
        for i from 0 <= i < n:
            size = size_list[i]
            buffer = PyBytes_FromStringAndSize(NULL, size)
            buffer_tuple[i] = buffer
            Py_INCREF(buffer)

        try:
            while 1:
                # Build the iov array to point to the correct positions.
                if self._try_selfish() == 1:
                    _readv_compute(size_list, buffer_tuple, n, received, iov,
                                   &left, &iov_pos, &complete_index, &partial_size)

                    rc = readv(self.fd, iov, iov_pos)
                else:
                    rc = -1
                    errno.errno = errno.EAGAIN
                if rc == -1:
                    if errno.errno == errno.EAGAIN:
                        self._wait_for_read()
                    else:
                        raise_oserror()
                elif rc == 0:
                    # Out of data!
                    # Determine the length of the new tuple.
                    _readv_compute(size_list, buffer_tuple, n, received, iov,
                                   &left, &iov_pos, &complete_index, &partial_size)
                    if partial_size == -1:
                        if complete_index == -1:
                            return ()
                        else:
                            return buffer_tuple[:complete_index+1]
                    else:
                        # Unfortunately can't call _PyString_Resize in Pyrex. :(
                        if complete_index == -1:
                            new_buffer_tuple = PyTuple_New(1)
                            buffer = buffer_tuple[0]
                            Py_INCREF(buffer)
                            new_buffer = buffer[:partial_size]
                            PyTuple_SET_ITEM(new_buffer_tuple, 0, new_buffer)
                            Py_INCREF(new_buffer)
                        else:
                            new_buffer_tuple = PyTuple_New(complete_index + 2)
                            for i from 0 <= i <= complete_index:
                                buffer = buffer_tuple[i]
                                Py_INCREF(buffer)
                                PyTuple_SET_ITEM(new_buffer_tuple, i, buffer)
                                Py_INCREF(buffer)
                            buffer = buffer_tuple[complete_index+1]
                            Py_INCREF(buffer)
                            new_buffer = buffer[:partial_size]
                            PyTuple_SET_ITEM(new_buffer_tuple, complete_index+1, new_buffer)
                            Py_INCREF(new_buffer)
                        return new_buffer_tuple
                else:
                    left = left - rc
                    received = received + rc
                    if left == 0:
                        return buffer_tuple
        finally:
            PyMem_Free(iov)

    cpdef int writev (self, list data) except -1:
        """Write a vector array of data.

        This will repeatedly call writev until all data is sent. If it is
        unable to send all data, it will raise an OSError exception.

        :param data: A sequence of strings to write.

        :returns: The number of bytes sent which should always be the sum of
            the lengths of all the strings in the data sequence.

        :raises OSError: OS-level error.
        """
        cdef char * buffer
        cdef int r, left, size, sent
        cdef int n, i, j
        cdef iovec * iov
        cdef bytes elem

        sent = 0
        n = len (data)
        iov = <iovec *> PyMem_Malloc (sizeof (iovec) * n)

        try:
            while 1:
                # we have to adjust iovec to consider portions
                # that we have already sent.
                left = 0
                i = 0
                j = 0
                while i < n:
                    elem = data[i]
                    size = len (elem)
                    # three cases:
                    # [--------][XXXXXXXX][-----------]
                    #       3   |   2     |    1
                    #           left      left+size
                    if sent > left + size:
                        # 1) this buffer is before <sent>
                        # ignore it
                        pass
                    elif sent > left:
                        # 2) this buffer contains <sent>
                        iov[j].iov_base = <void*>(<char*>elem + (sent - left))
                        iov[j].iov_len = size - (sent - left)
                        j = j + 1
                    else:
                        # 3) this buffer is after <sent>
                        iov[j].iov_base = <void*><char*>elem
                        iov[j].iov_len = size
                        j = j + 1
                    left = left + size
                    i = i + 1
                left = left - sent
                if left == 0:
                    return sent
                if self._try_selfish() == 1:
                    r = writev (self.fd, iov, j)
                else:
                    r = -1
                    errno.errno = errno.EAGAIN
                if r == -1:
                    if errno.errno == errno.EAGAIN:
                        self._wait_for_write()
                    else:
                        raise_oserror()
                else:
                    left = left - r
                    sent = sent + r
                    if left == 0:
                        return sent
        finally:
            PyMem_Free (iov)

    # SMR 20120717 temporarily disabling this code, cython does not expose this part
    #   of the 'old' buffer interface.  Looks like there's a new one, and the necessary
    #   compatibility will require updating this code.
    IF False:
        cpdef recv_into (self, buffer, int nbytes=0, int flags=0):
            """Receive data into a Python buffer.

            This is for the Python buffer interface.  If you don't know what that
            is, move along.  This method is for Python socket compatibility.

            :param buffer: A writeable Python buffer object.  Must be a contiguous
                  segment.
            :param nbytes: Number of bytes to read.  Must be less than or equal to
                  the size of the buffer.  Defaults to 0 which means the size of
                  ``buffer``.
            :param flags: Flags for the recv system call (see recv(2) manpage).
                  Defaults to 0.

            :returns: The number of bytes read.

            :raises OSError: OS-level error.
            """
            cdef void *cbuf
            cdef Py_ssize_t cbuflen
            cdef int r

            if nbytes < 0:
                raise ValueError('negative buffersize in recv_into')

            PyObject_AsWriteBuffer(buffer, &cbuf, &cbuflen)

            if nbytes == 0:
                nbytes = cbuflen

            if cbuflen < nbytes:
                raise ValueError('buffer too small for requested bytes')

            while 1:
                if self._try_selfish() == 1:
                    r = recv(self.fd, cbuf, nbytes, flags)
                else:
                    r = -1
                    errno.errno = errno.EAGAIN
                if r == -1:
                    if errno.errno == errno.EAGAIN:
                        self._wait_for_read()
                    else:
                        raise_oserror()
                else:
                    return r

        cpdef recvfrom_into(self, buffer, int nbytes=0, int flags=0):
            """Receive data into a Python buffer.

            This is for the Python buffer interface.  If you don't know what that
            is, move along.  This method is for Python socket compatibility.

            :param buffer: A writeable Python buffer object.  Must be a contiguous
                  segment.
            :param nbytes: Number of bytes to read.  Must be less than or equal to
                  the size of the buffer.  Defaults to 0 which means the size of
                  ``buffer``.
            :param flags: Flags for the recv system call (see recvfrom(2) manpage).
                  Defaults to 0.

            :returns: A tuple ``(nbytes, address)`` where ``bytes`` is the number
                of bytes read and ``address`` then it is the address of the remote
                side.

            :raises OSError: OS-level error.
            """
            cdef sockaddr_storage sa
            cdef void *cbuf
            cdef Py_ssize_t cbuflen
            cdef ssize_t nread
            cdef socklen_t addr_len
            cdef int r

            if nbytes < 0:
                raise ValueError('negative buffersize in recv_into')

            PyObject_AsWriteBuffer(buffer, &cbuf, &cbuflen)

            if nbytes == 0:
                nbytes = cbuflen

            if cbuflen < nbytes:
                raise ValueError('buffer too small for requested bytes')

            while 1:
                if self._try_selfish() == 1:
                    addr_len = sizeof(sockaddr_storage)
                    memset(&sa, 0, sizeof(sockaddr_storage))
                    r = recvfrom(self.fd, cbuf, nbytes, flags, <sockaddr*>&sa, &addr_len)
                else:
                    r = -1
                    errno.errno = errno.EAGAIN
                if r == -1:
                    if errno.errno == errno.EAGAIN:
                        self._wait_for_read()
                    else:
                        raise_oserror()
                else:
                    address = self.unparse_address(&sa, addr_len)
                    return r, address

    cdef parse_address_inet (self, tuple address, sockaddr_storage * sa, socklen_t * addr_len, bint resolve):
        cdef sockaddr_in * sin = <sockaddr_in *>sa
        cdef bytes ip
        cdef uint16_t port
        ip, port = address
        if not ip:
            ip = b'0.0.0.0'
        sin.sin_family = AF_INET
        IF UNAME_SYSNAME == "FreeBSD":
            sin.sin_len = sizeof (sockaddr_in)
        addr_len[0] = sizeof (sockaddr_in)
        sin.sin_port = htons(port)
        r = inet_pton (AF_INET, ip, &sin.sin_addr)
        if r != 1:
            if resolve:
                # recurse
                self.parse_address_inet (
                    (the_resolver.resolve_ipv4 (ip), port), sa, addr_len, False
                    )
            else:
                raise ValueError ("not a valid IPv4 address")

    cdef parse_address_inet6 (self, tuple address, sockaddr_storage * sa, socklen_t * addr_len, bint resolve):
        cdef sockaddr_in6 * sin6 = <sockaddr_in6 *> sa
        cdef bytes ip
        cdef uint16_t port
        cdef int percent
        cdef int flowinfo
        cdef int scope_id
        cdef addrinfo * ai
        if len(address) == 4:
            # as per python return value from getaddrinfo() and arg to connect()
            ip, port, flowinfo, scope_id = address
            sin6.sin6_flowinfo = htonl (flowinfo)
            sin6.sin6_scope_id = scope_id
        elif len(address) == 2:
            ip, port = address
        if not ip:
            ip = b'::'
        percent = ip.find ('%')
        if percent != -1:
            ip = ip[:percent]
            # XXX hack, should make scope id an option?
            sin6.sin6_scope_id = 2
        sin6.sin6_family = AF_INET6
        IF UNAME_SYSNAME == "FreeBSD":
            sin6.sin6_len = sizeof(sockaddr_in6)
        addr_len[0] = sizeof(sockaddr_in6)
        sin6.sin6_port = htons(port)
        r = inet_pton(AF_INET6, ip, &sin6.sin6_addr)
        if r != 1:
            if resolve:
                # recurse
                self.parse_address_inet6 (
                    (the_resolver.resolve_ipv6 (ip), port), sa, addr_len, False
                    )
            else:
                raise ValueError ("not a valid IPv6 address")

    cdef parse_address_unix (self, bytes address, sockaddr_storage * sa, socklen_t * addr_len, bint resolve):
        cdef sockaddr_un * sun
        # AF_UNIX
        # +1 to grab the NUL char
        l = len (address) + 1
        sun = <sockaddr_un *>sa
        sun.sun_family = AF_UNIX
        IF UNAME_SYSNAME == "FreeBSD":
            sun.sun_len = sizeof (sockaddr_un)
        if (l < sizeof (sun.sun_path)):
            memcpy (<void *>sun.sun_path, <void*><char*>address, l)
            addr_len[0] = sizeof (sockaddr_un)
        else:
            raise ValueError, "name too long"

    cdef parse_address (self, object address, sockaddr_storage * sa, socklen_t * addr_len, bint resolve=False):
        """Parse a Python socket address and set the C structure values.

        :param address: The Python address to parse.  For IP, it should be a
              ``(IP, port)`` tuple where the IP is a string. Use the empty
              string to indicate INADDR_ANY.
              The port should always be a host-byte-order integer.
              For Unix-domain sockets, the address should be a string.
        :param sa: OUTPUT: The sockaddr_storage C-structure to store the
              result in.
        :param addr_len: OUTPUT: The size of the structure placed into ``sa``.

        :raises ValueError: The value could not be parsed.
        """
        cdef sockaddr_in * sin
        cdef sockaddr_in6 *sin6
        cdef sockaddr_un * sun
        cdef int r, l
        if self.domain == AF_INET:
            return self.parse_address_inet (address, sa, addr_len, resolve)
        elif self.domain == AF_INET6:
            return self.parse_address_inet6 (address, sa, addr_len, resolve)
        elif self.domain == AF_UNIX:
            return self.parse_address_unix (address, sa, addr_len, resolve)
        else:
            raise ValueError, "can't parse address for this socket domain"

    cdef object unparse_address (self, sockaddr_storage *sa, socklen_t addr_len):
        """Unpack a C-socket address structure and generate a Python address object.

        :param sa: The sockaddr_storage structure to unpack.
        :param addr_len: The length of the ``sa`` structure.

        :returns: A ``(IP, port)`` tuple for IP addresses where IP is a
            string in canonical format for the given address family . Returns a
            string for UNIX-domain sockets.  Returns None for unknown socket
            domains.
        """
        cdef sockaddr_in * sin
        cdef sockaddr_in6 *sin6
        cdef sockaddr_un * sun
        cdef char ascii_buf[INET6_ADDRSTRLEN]

        if (<sockaddr_in *>sa).sin_family == AF_INET:
            sin = <sockaddr_in *> sa
            inet_ntop (AF_INET, &(sin.sin_addr), ascii_buf, INET_ADDRSTRLEN)
            return (ascii_buf, ntohs(sin.sin_port))
        elif (<sockaddr_in6 *>sa).sin6_family == AF_INET6:
            sin6 = <sockaddr_in6 *> sa
            inet_ntop (AF_INET6, &(sin6.sin6_addr), ascii_buf, INET6_ADDRSTRLEN)
            return (ascii_buf, ntohs(sin6.sin6_port))
        elif (<sockaddr_un *>sa).sun_family == AF_UNIX:
            sun = <sockaddr_un *>sa
            return sun.sun_path
        else:
            return None

    def wait_for_read (self):
        """Block until the socket is readable.

        This will block until there is data available to be read.

        :returns: The amount "readable".  For different sockets, this may be
            different values, see the EVFILT_READ section of the kevent manpage
            for details.

        :raises OSError: OS-level error.
        """
        return self._wait_for_read()

    def wait_for_write (self):
        """Block until the socket is writeable.

        This will block until it is possible to write to the socket.

        :returns: The number of bytes writeable on the socket.

        :raises OSError: OS-level error.
        """
        return self._wait_for_write()

    cdef _wait_for_read (self):
        return the_poller._wait_for_read (self.fd)

    cdef _wait_for_write (self):
        return the_poller._wait_for_write (self.fd)

    cpdef connect_addr (self, address, bint resolve=False):
        """Connect the socket.

        :param address: The address to connect to.  For IP, it should be a
              ``(IP, port)`` tuple where the IP is a string.
              The port should always be a host-byte-order integer. For
              Unix-domain sockets, the address should be a string.

        :raises OSError: OS-level error.
        """
        cdef sockaddr_storage sa
        cdef socklen_t addr_len
        cdef int r
        cdef coro me
        me = <coro>the_scheduler._current
        memset (&sa, 0, sizeof (sockaddr_storage))
        self.parse_address (address, &sa, &addr_len, resolve)
        while 1:
            r = connect (self.fd, <sockaddr*>&sa, addr_len)
            if r == -1:
                if errno.errno == errno.EAGAIN or errno.errno == errno.EINPROGRESS:
                    self._wait_for_write()
                    return None
                else:
                    raise_oserror()
            else:
                return None

    cpdef connect (self, address):
        return self.connect_addr (address, True)

    cpdef bind (self, address):
        """Bind the socket.

        :param address: The address to bind to.  For IP, it should be a
              ``(IP, port)`` tuple where the IP is a string.  Use the empty
              string to indicate INADDR_ANY.
              The port should always be a host-byte-order integer.
              For Unix-domain sockets, the address should be a string.

        :raises OSError: OS-level error.
        """
        cdef sockaddr_storage sa
        cdef socklen_t addr_len
        cdef int r

        memset (&sa, 0, sizeof (sockaddr_storage))
        self.parse_address (address, &sa, &addr_len)
        self._set_reuse_addr()
        r = bind (self.fd, <sockaddr*>&sa, addr_len)
        if r == -1:
            raise_oserror()

    cpdef listen (self, int backlog):
        """Set the socket to listen for connections.

        :param backlog: The maximum size of the queue for pending connections.

        :raises OSError: OS-level error.
        """
        cdef int r
        r = listen (self.fd, backlog)
        if r == -1:
            raise_oserror()

    cpdef accept (self):
        """Accept a connection.

        :returns: A tuple ``(socket, address)`` where ``socket`` is a socket
            object and ``address`` is an ``(IP, port)`` tuple for IP
            addresses or a string for UNIX-domain sockets. IP addresses are
            returned as strings.

        :raises OSError: OS-level error.
        """
        cdef sockaddr_storage sa
        cdef socklen_t addr_len
        cdef int r

        while 1:
            if self._try_selfish():
                memset (&sa, 0, sizeof (sockaddr_storage))
                addr_len = sizeof (sockaddr_storage)
                r = accept (self.fd, <sockaddr *>&sa, &addr_len)
            else:
                r = -1
                errno.errno = errno.EAGAIN
            if r == -1:
                if errno.errno == errno.EAGAIN:
                    self._wait_for_read()
                elif errno.errno == errno.ECONNABORTED:
                    pass
                else:
                    raise_oserror()
            else:
                return (
                    sock (self.domain, fd=r),
                    self.unparse_address (&sa, addr_len)
                    )

    cpdef accept_many (self, int max=0):
        """Accept multiple connections.

        This will accept up to ``max`` connections for any connections available
        on the listen queue.  This will block if there are no connections
        waiting.

        :param max: The maximum number of connections to accept.  If not
              specified, defaults to infinity (accept all pending connections).

        :returns: A list of ``(socket, address)`` tuples (see :meth:`accept` method
            for information on return format).

        :raises OSError: OS-level error.
        """
        cdef sockaddr_storage sa
        cdef socklen_t addr_len
        cdef int r, count
        cdef int upper_limit
        cdef coro me
        cdef list result
        count = 0
        result = []
        if max == 0:
            upper_limit = 0x7ffffffe
        else:
            upper_limit = max
        me = <coro>the_scheduler._current
        self._wait_for_read()
        while count < upper_limit:
            memset (&sa, 0, sizeof (sockaddr_storage))
            addr_len = sizeof (sockaddr_storage)
            r = accept (self.fd, <sockaddr *>&sa, &addr_len)
            if r == -1:
                if errno.errno == errno.EAGAIN:
                    return result
                elif errno.errno == errno.ECONNABORTED:
                    pass
                else:
                    raise_oserror()
            else:
                result.append ((
                    sock (self.domain, fd=r),
                    self.unparse_address (&sa, addr_len)
                ))
                count = count + 1
        return result

    cpdef shutdown (self, int how):
        """Shutdown the socket.

        :param how: How to shut down the socket (see the shutdown(2) manpage).

        :raises OSError: OS-level error.
        """
        cdef int r
        r = shutdown (self.fd, how)
        if r == -1:
            raise_oserror()
        else:
            return None

    cpdef getpeername (self):
        """Get the remote-side address.

        :returns: A ``(IP, port)`` tuple for IP addresses where IP is a
            string. Returns a string for UNIX-domain sockets.

        :raises OSError: OS-level error.
        """
        cdef sockaddr_storage sa
        cdef socklen_t addr_len
        cdef int r

        memset (&sa, 0, sizeof (sockaddr_storage))
        addr_len = sizeof (sockaddr_storage)
        r = getpeername (self.fd, <sockaddr *>&sa, &addr_len)
        if r == 1:
            raise_oserror()
        else:
            return self.unparse_address (&sa, addr_len)

    cpdef getsockname (self):
        """Get the local address of the socket.

        :returns: A ``(IP, port)`` tuple for IP addresses where IP is a
            string or an empty string for INADDR_ANY. Returns a
            string for UNIX-domain sockets (empty string if not bound).
        """
        cdef sockaddr_storage sa
        cdef socklen_t addr_len
        cdef int r

        memset (&sa, 0, sizeof (sockaddr_storage))
        addr_len = sizeof (sockaddr_storage)
        r = getsockname (self.fd, <sockaddr *>&sa, &addr_len)
        if r == 1:
            raise_oserror()
        else:
            return self.unparse_address (&sa, addr_len)

    def makefile(self, mode='r', bufsize=-1):
        """Return a regular file object corresponding to the socket.

        The mode and bufsize arguments are as for the built-in open() function.

        The underlying socket is duplicated via ``sock.dup`` to emulate Python's
        reference counting behavior.

        :param mode: The mode of the file, defaults to 'r'.
        :param bufsize: The buffer size (0 is no buffering, 1 is line
              buffering, greater than 1 is the explicit buffer size).
              Defaults to -1 (does not change the default buffering).

        :returns: A file-like object that wraps the socket.
        """
        # Probably unwise to access an underscore private value from the
        # socket module, but it should work OK for the foreseeable future.
        #
        # Last argument indicates we want it to call the real close() since
        # we're using dup.
        #
        # We use dup() unlike Python because we don't use the dummy socket
        # concept to handle file descriptor reference counting (a cross-
        # platform issue).
        return __socketmodule._fileobject(self.dup(), mode, bufsize, True)

    cpdef dup(self):
        """Duplicate the socket object using the OS dup() call.

        :returns: A new sock instance that holds the new file descriptor.
        """
        cdef sock new_sock
        cdef int new_fd

        new_fd = unistd.dup(self.fd)
        if new_fd == -1:
            raise_oserror()

        return sock(self.domain, self.stype, 0, new_fd)


class NameError (Exception):
    pass

cdef class dummy_resolver:
    "blocking name resolver uses socket.getaddrinfo()"
    def resolve_ipv4 (self, bytes address):
        addrs = __socketmodule.getaddrinfo (address, None, __socketmodule.AF_INET)
        if not addrs:
            raise NameError ("unable to resolve host: %r" % address)
        else:
            return addrs[0][4][0]
    def resolve_ipv6 (self, bytes address):
        addrs = __socketmodule.getaddrinfo (address, None, __socketmodule.AF_INET6)
        if not addrs:
            raise NameError ("unable to resolve host: %r" % address)
        else:
            return addrs[0][4][0]

the_resolver = dummy_resolver()

def set_resolver (resolver):
    "replace the default resolver - return previous value"
    global the_resolver
    old_value = the_resolver
    the_resolver = resolver
    return old_value

def get_resolver():
    "return the current resolver"
    return the_resolver

def get_live_sockets():
    """Get the number of live socket objects.  This includes socket objects
    that are closed.

    :returns: The number of socket objects.
    """
    global live_sockets
    return live_sockets

class AF:

    """Socket families."""

    INET = AF_INET
    INET6 = AF_INET6
    UNIX = AF_UNIX
    LOCAL = AF_UNIX

PF = AF

class SOCK:

    """Socket types."""

    STREAM = SOCK_STREAM
    DGRAM  = SOCK_DGRAM

class SHUT:

    """Socket shutdown methods."""

    RD = SHUT_RD
    WR = SHUT_WR
    RDWR = SHUT_RDWR

class SOL:

    """Socket levels."""

    SOCKET = SOL_SOCKET

class SO:

    """Socket options."""

    DEBUG = SO_DEBUG                    # enables recording of debugging information
    REUSEADDR = SO_REUSEADDR            # enables local address reuse
    KEEPALIVE = SO_KEEPALIVE            # enables keep connections alive
    DONTROUTE = SO_DONTROUTE            # enables routing bypass for outgoing messages
    LINGER = SO_LINGER                  # linger on close if data present
    BROADCAST = SO_BROADCAST            # enables permission to transmit broadcast messages
    OOBINLINE = SO_OOBINLINE            # enables reception of out-of-band data in band
    SNDBUF = SO_SNDBUF                  # set buffer size for output
    RCVBUF = SO_RCVBUF                  # set buffer size for input
    SNDLOWAT = SO_SNDLOWAT              # set minimum count for output
    RCVLOWAT = SO_RCVLOWAT              # set minimum count for input
    SNDTIMEO = SO_SNDTIMEO              # set timeout value for output
    RCVTIMEO = SO_RCVTIMEO              # set timeout value for input
    IF UNAME_SYSNAME == "FreeBSD":
        ACCEPTFILTER = SO_ACCEPTFILTER  # set accept filter on listening socket
        REUSEPORT = SO_REUSEPORT        # enables duplicate address and port bindings
    TYPE = SO_TYPE                      # get the type of the socket (get only)
    ERROR = SO_ERROR                    # get and clear error on the socket (get only)

cdef class file_sock(sock):

    """A file-object wrapper using the socket object.

    The constructor takes one argument:

    :param fileobj: A Python-like file object.  Currently only needs to
          implement the ``fileno`` method.

    When the object is deallocated, the file descriptor is closed.
    """

    #cdef object _fileobj

    def __init__(self, fileobj):
        # we need to keep the original file object around, because if its
        # refcount goes to zero, the fd will automatically be closed.
        self._fileobj = fileobj
        sock.__init__(self, domain=AF_UNSPEC, fd=fileobj.fileno())

# For backwards compatbility, do not use this.
coro_fd = file_sock

cdef class fd_sock(sock):

    """A file-descriptor wrapper using the socket object.

    The constructor takes one argument:

    :param fd: A file descriptor.

    When the object is deallocated, the file descriptor is closed.
    """

    def __init__(self, fd):
        sock.__init__(self, domain=AF_UNSPEC, fd=fd)


def tcp_sock():
    """Create a streaming IPv4 socket.

    :returns: A socket object.

    :raises OSError: OS-level error.
    """
    return sock (AF_INET, SOCK_STREAM)

def udp_sock():
    """Create a datagram IPv4 socket.

    :returns: A socket object.

    :raises OSError: OS-level error.
    """
    return sock (AF_INET, SOCK_DGRAM)

def tcp6_sock():
    """Create a streaming IPv6 socket.

    :returns: A socket object.

    :raises OSError: OS-level error.
    """
    return sock (AF_INET6, SOCK_STREAM)

def udp6_sock():
    """Create a datagram IPv6 socket.

    :returns: A socket object.

    :raises OSError: OS-level error.
    """
    return sock (AF_INET6, SOCK_DGRAM)

def unix_sock():
    """Create a streaming unix-domain socket.

    :returns: A socket object.

    :raises OSError: OS-level error.
    """
    return sock (AF_UNIX, SOCK_STREAM)

def make_socket (int domain, int stype):
    """Create a socket object.

    This is a backwards-compatibility wrapper around the sock object
    constructor.

    :param domain: The socket domain family (see :class:`AF`).
    :param stype: The socket type (see :class:`SOCK`).

    :returns: A socket object.

    :raises OSError: OS-level error.
    """
    return sock (domain, stype)

def has_ipv6():
    """Whether or not this system can create an IPv6 socket.

    :returns: True if this system can create an IPv6 socket, False otherwise
    """
    cdef int s

    s = socket(AF_INET6, SOCK_STREAM, 0)
    if s == -1:
        return False
    else:
        close(s)
        return True


def socketpair(int domain=AF_UNIX, int stype=SOCK_STREAM, int protocol=0):
    """Create an unnamed pair of connected sockets.

    :param domain: The socket domain family (defaults to AF_UNIX).
    :param stype: The socket type (defaults to SOCK_STREAM).
    :param protocol: The socket protocol (normally not used, defaults to 0).

    :returns: A tuple of 2 connected sockets.

    :raises OSError: OS-level error.
    """
    cdef int sv[2]
    cdef int rc

    rc = _c_socketpair(domain, stype, protocol, sv)
    if rc == -1:
        raise_oserror()

    s1 = sock(domain, stype, protocol, sv[0])
    s2 = sock(domain, stype, protocol, sv[1])
    return (s1, s2)
