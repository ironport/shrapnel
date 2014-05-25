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

# Note: this file is included by <coro.pyx>

__poller_version__ = "$Id: //prod/main/ap/shrapnel/coro/poller.pyx#46 $"

# ================================================================================
#                                kqueue
# ================================================================================

cdef extern from "sys/time.h":
    cdef struct timespec:
        unsigned int tv_sec
        unsigned int tv_nsec

from xlibc.stdlib cimport alloca

# XXX consider putting these into a pxd file
cdef extern from "sys/event.h":

    cdef struct kevent:
        uintptr_t ident
        short filter
        unsigned short flags
        unsigned int fflags
        intptr_t data
        void * udata

    int kqueue()

    int _kevent "kevent" (
        int kq,
        kevent * changelist, int nchanges,
        kevent * eventlist,  int nevents,
        timespec * timeout
        )

    void EV_SET (
        kevent * kev, uintptr_t ident, short filter,
        short flags, unsigned int fflags,
        intptr_t data, void * udata
        )

    int EV_ADD, EV_DELETE, EV_ENABLE, EV_DISABLE, EV_ONESHOT
    int EV_CLEAR, EV_SYSFLAGS, EV_FLAG1, EV_EOF, EV_ERROR

    int EVFILT_READ, EVFILT_WRITE, EVFILT_AIO, EVFILT_VNODE, EVFILT_PROC
    int EVFILT_SIGNAL, EVFILT_TIMER
    int EVFILT_FS
    IF COMPILE_NETDEV:
        EVFILT_NETDEV
    IF COMPILE_LIO:
        int EVFILT_LIO

    unsigned int NOTE_LOWAT, NOTE_DELETE, NOTE_WRITE, NOTE_EXTEND, NOTE_ATTRIB
    unsigned int NOTE_LINK, NOTE_RENAME, NOTE_REVOKE, NOTE_EXIT, NOTE_FORK
    unsigned int NOTE_EXEC, NOTE_PCTRLMASK, NOTE_PDATAMASK, NOTE_TRACK
    unsigned int NOTE_TRACKERR, NOTE_CHILD
    IF COMPILE_NETDEV:
        unsigned int NOTE_LINKUP, NOTE_LINKDOWN, NOTE_LINKINV

class EV:

    """Kevent flags."""

    ADD      = EV_ADD        # add event to kq (implies enable)
    DELETE   = EV_DELETE     # delete event from kq
    ENABLE   = EV_ENABLE     # enable event
    DISABLE  = EV_DISABLE    # disable event (not reported)
    ONESHOT  = EV_ONESHOT    # only report one occurrence
    CLEAR    = EV_CLEAR      # clear event state after reporting
    SYSFLAGS = EV_SYSFLAGS   # reserved by system
    FLAG1    = EV_FLAG1      # filter-specific flag
    EOF      = EV_EOF        # EOF detected
    ERROR    = EV_ERROR      # error, data contains errno

class EVFILT:

    """Kevent filters."""

    READ     = EVFILT_READ   #
    WRITE    = EVFILT_WRITE  #
    AIO      = EVFILT_AIO    # attached to aio requests
    VNODE    = EVFILT_VNODE  # attached to vnodes
    PROC     = EVFILT_PROC   # attached to struct proc
    SIGNAL   = EVFILT_SIGNAL # attached to struct proc
    TIMER    = EVFILT_TIMER  # timers
    IF COMPILE_NETDEV:
        NETDEV   = EVFILT_NETDEV # network devices
    FS       = EVFILT_FS     # filesystem events
    IF COMPILE_LIO:
        LIO      = EVFILT_LIO    # lio

class NOTE:

    """Kevent filter flags."""

    #
    # data/hint flags for EVFILT_{READ|WRITE}, shared with userspace
    #
    LOWAT = NOTE_LOWAT                  #  low water mark
    #
    # data/hint flags for EVFILT_VNODE, shared with userspace
    #
    DELETE = NOTE_DELETE                #  vnode was removed
    WRITE  = NOTE_WRITE                 #  data contents changed
    EXTEND = NOTE_EXTEND                #  size increased
    ATTRIB = NOTE_ATTRIB                #  attributes changed
    LINK   = NOTE_LINK                  #  link count changed
    RENAME = NOTE_RENAME                #  vnode was renamed
    REVOKE = NOTE_REVOKE                #  vnode access was revoked
    #
    # data/hint flags for EVFILT_PROC, shared with userspace
    #
    EXIT = NOTE_EXIT                    #  process exited
    FORK = NOTE_FORK                    #  process forked
    EXEC = NOTE_EXEC                    #  process exec'd
    PCTRLMASK = NOTE_PCTRLMASK          #  mask for hint bits
    PDATAMASK = NOTE_PDATAMASK          #  mask for pid
    #  additional flags for EVFILT_PROC
    TRACK = NOTE_TRACK                  #  follow across forks
    TRACKERR = NOTE_TRACKERR            #  could not track child
    CHILD = NOTE_CHILD                  #  am a child process
    #
    # data/hint flags for EVFILT_NETDEV, shared with userspace
    #
    IF COMPILE_NETDEV:
        LINKUP = NOTE_LINKUP                #  link is up
        LINKDOWN = NOTE_LINKDOWN            #  link is down
        LINKINV = NOTE_LINKINV              #  link state is invalid

# Definition of kevent status flags:
# - NEW: Target is new, event not yet submitted.
# - SUBMITTED: The event has been submitted to kqueue.
# - FIRED: The event has fired.
# - ABORTED: The event has been aborted (typically by Interrupted exception).
#            The event may or may not have already been submitted.
cdef enum:
    KEVENT_STATUS_NEW
    KEVENT_STATUS_SUBMITTED
    KEVENT_STATUS_FIRED
    KEVENT_STATUS_ABORTED

# - ONESHOT: Used to indicate that this target should be removed from the
#            event map after it fires.  This is necessary since some oneshot
#            kevents (such as AIO) don't set the ONESHOT kevent flag.
# - CLOSED: For file-descriptor events, this indicates that the file
#           descriptor has been closed, and that the kevent key has been
#           removed from the event map.
cdef enum:
    KTARGET_FLAG_ONESHOT = 1
    KTARGET_CLOSED       = 2

cdef class kevent_target:
    cdef public int status
    cdef public int index
    cdef public object target
    cdef public int flags

    def __cinit__ (self, target, int index):
        self.status = KEVENT_STATUS_NEW
        self.index = index
        self.target = target
        self.flags = 0

    def __repr__ (self):
        return '<kevent_target status=%r index=%r target=%r flags=%r>' % (self.status, self.index, self.target, self.flags)

cdef class py_kevent:

    """Representation of a kevent.

    :IVariables:
        - `ident`: The kevent identifier (depends on the filter type, but is
          often a file descriptor).
        - `filter`: The kevent filter (see `EVFILT`).
        - `flags`: The kevent flags.
        - `fflags`: The kevent filter flags.
        - `data`: Filter data value (as an integer).  This is a filter-specific
          return value.
        - `udata`: User-data pointer (C only).
    """

    cdef readonly uintptr_t ident
    cdef readonly short filter
    cdef readonly unsigned short flags
    cdef readonly unsigned int fflags
    cdef readonly intptr_t data
    cdef readonly uintptr_t udata_addr
    cdef void * udata

    # cinit cannot take a C struct.
    # It would be nice to support fast-constructor semantics in Cython.
    cdef __fast_init__ (self, kevent * k):
        self.ident = k.ident
        self.filter = k.filter
        self.flags = k.flags
        self.fflags = k.fflags
        self.data = k.data
        self.udata_addr = <uintptr_t>k.udata
        self.udata = k.udata

    def __repr__(self):
        return '<py_kevent ident=%r filter=%r flags=%r fflags=%r data=%r udata_addr=%r>' % (
            self.ident,
            self.filter,
            self.flags,
            self.fflags,
            self.data,
            self.udata_addr
        )

cdef class kevent_key:

    """Kevent key.

    All kevents are uniquely identified by a key which is a combination of the
    filter and ident.

    :IVariables:
        - `filter`: The kevent filter (see `EVFILT`).
        - `ident`: The kevent identifier (depends on the filter type, but is
          often a file descriptor).
    """

    cdef public short filter
    cdef public uintptr_t ident

    def __cinit__ (self, short filter, uintptr_t ident):
        self.filter = filter
        self.ident = ident

    def __hash__ (self):
        cdef int value
        value = (self.ident << 4) | (-self.filter)
        if value == -1:
            value = -2
        return value

    def __repr__ (self):
        return '<kevent_key filter=%d ident=%x>' % (self.filter, self.ident)

    def __richcmp__ (kevent_key self, kevent_key other, int op):
        # all we need is EQ, ignore the rest
        if op != 2:
            raise ValueError, "kevent_key() only supports '==' rich comparison"
        else:
            return (self.filter == other.filter) and (self.ident == other.ident)

from posix cimport unistd

cdef public class queue_poller [ object queue_poller_object, type queue_poller_type ]:

    cdef kevent * change_list
    cdef int change_list_index
    cdef int kq_fd
    cdef dict event_map

    def __cinit__ (self):
        # XXX EVENT_SCALE should be a parameter.
        self.change_list = <kevent *>PyMem_Malloc (sizeof (kevent) * EVENT_SCALE)

    def __dealloc__ (self):
        PyMem_Free (self.change_list)

    def __init__ (self):
        self.change_list_index = 0
        self.kq_fd = -1
        self.event_map = {}

    cdef set_up(self):
        self.kq_fd = kqueue()
        if self.kq_fd == -1:
            raise SystemError, "kqueue() failed"

    cdef tear_down(self):
        if self.kq_fd != -1:
            unistd.close (self.kq_fd)
            self.kq_fd = -1

    cdef object set_wait_for (self, kevent_key kk, unsigned int fflags):
        cdef kevent * k
        cdef coro me
        cdef kevent_target kt
        if self.change_list_index < EVENT_SCALE:
            if self.event_map.has_key (kk):
                # Should be impossible to have KeyError due to previous line.
                kt = self.event_map[kk]
                raise SimultaneousError (the_scheduler._current, kt.target, kk)
            else:
                me = the_scheduler._current
                target = kevent_target (me, self.change_list_index)
                self.event_map[kk] = target
                k = &(self.change_list[self.change_list_index])
                EV_SET (k, kk.ident, kk.filter, EV_ADD | EV_ONESHOT, fflags, 0, NULL)
                self.change_list_index = self.change_list_index + 1
                return target
        else:
            raise SystemError, "too many kevents in change_list"

    cdef _wait_for_with_eof (self, uintptr_t ident, int filter):
        cdef py_kevent event
        event = self._wait_for (ident, filter, 0)
        if event.flags & EV_EOF and event.fflags != 0:
            # fflags is errno
            raise_oserror_with_errno(event.fflags)
        else:
            return event.data

    cdef _wait_for_read (self, int fd):
        return self._wait_for_with_eof(fd, EVFILT_READ)

    cdef _wait_for_write (self, int fd):
        return self._wait_for_with_eof(fd, EVFILT_WRITE)

    def wait_for_read (self, int fd):
        return self._wait_for_with_eof(fd, EVFILT_READ)

    def wait_for_write (self, int fd):
        return self._wait_for_with_eof(fd, EVFILT_WRITE)

    cdef py_kevent _wait_for (self, uintptr_t ident, int filter, unsigned int fflags):
        cdef kevent_target kt
        cdef kevent * k
        cdef kevent_key kk
        kk = kevent_key (filter, ident)
        kt = self.set_wait_for (kk, fflags)
        try:
            return _YIELD()
        finally:
            if kt.status == KEVENT_STATUS_NEW:
                # still in the change list
                k = &self.change_list[kt.index]
                # kevent() will ignore this entry
                k.filter = 0
                k.ident = 0
                kt.status = KEVENT_STATUS_ABORTED
                if not kt.flags & KTARGET_CLOSED:
                    # remove from event map
                    del self.event_map[kk]
                #W ('wait_for() cleanup: (%d, %d) STATUS_NEW\n' % (ident, filter))
            elif kt.status == KEVENT_STATUS_SUBMITTED:
                # kevent submitted, delete it.
                kt.status = KEVENT_STATUS_ABORTED
                if not kt.flags & KTARGET_CLOSED:
                    self.delete_kevent (ident, filter)
                    # remove from event map
                    del self.event_map[kk]
                #W ('wait_for() cleanup: (%d, %d) STATUS_SUBMITTED\n' % (ident, filter))
            elif kt.status == KEVENT_STATUS_FIRED:
                # kevent already fired! do nothing.
                #W ('wait_for() cleanup: (%d, %d) STATUS_FIRED\n' % (ident, filter))
                pass

    def wait_for (self, uintptr_t ident, int filter, unsigned int fflags=0):
        """Wait for an event.

        :Parameters:
            - `ident`: The kevent identifier (depends on the filter type, but
              is often a file descriptor).
            - `filter`: The kevent filter (see `EVFILT`).
            - `fflags`: Filter flags (defaults to 0).

        :Return:
            Returns a `py_kevent` instance that indicates the event that fired.

        :Exceptions:
            - `SimultaneousError`: Something is already waiting for this event.
        """
        return self._wait_for(ident, filter, fflags)

    cdef delete_kevent (self, uintptr_t ident, int filter):
        cdef int r
        cdef kevent k
        k.ident = ident
        k.filter = filter
        k.flags = EV_DELETE | EV_ONESHOT
        k.fflags = 0
        k.data = 0
        k.udata = NULL
        r = _kevent (self.kq_fd, &k, 1, NULL, 0, NULL)
        if r < 0:
            raise_oserror()

    def set_handler (self, tuple event, object handler, int flags=(EV_ADD|EV_ONESHOT), unsigned int fflags=0):
        """Add a kevent handler.

        This is a low-level interface to register a kevent handler.

        :Parameters:
            - `event`: A tuple of ``(ident, filter)`` of the kevent to handle.
            - `handler`: The handler to use,  a callable object which will be
              called with one argument, a `py_kevent` object.
            - `flags`: Kevent flags to use.  Defaults to ``EV_ADD|EV_ONESHOT``.
            - `fflags``: Kevent filter flags to use.  Defaults to 0.

        :Exceptions:
            - `SimultaneousError`: There is already a handler set for this
              event.
        """
        cdef short filter
        cdef uintptr_t ident
        cdef kevent * k
        cdef kevent_key kk
        assert callable(handler)

        ident, filter = event
        kk = kevent_key (filter, ident)
        # for kqueue, event == (ident, filter)
        if self.event_map.has_key (kk):
            # Should be impossible to have KeyError due to previous line.
            kt = self.event_map[kk]
            raise SimultaneousError (the_scheduler._current, kt.target, kk)
        else:
            if self.change_list_index < EVENT_SCALE:
                k = &(self.change_list[self.change_list_index])
                EV_SET (k, ident, filter, flags, fflags, 0, NULL)
                self.change_list_index = self.change_list_index + 1
                kt = kevent_target (handler, self.change_list_index)
                self.event_map[kk] = kt
            else:
                raise SystemError, "too many kevents in change_list"

    cdef set_event_target (self, tuple event, kevent_target kt):
        cdef short filter
        cdef uintptr_t ident
        cdef kevent_key kk

        ident, filter = event
        kk = kevent_key (filter, ident)
        self.event_map[kk] = kt

    cdef notify_of_close (self, int fd):
        cdef kevent_target kt
        cdef coro co
        cdef kevent_key kk

        kk = kevent_key (EVFILT_READ, fd)
        if self.event_map.has_key (kk):
            kt = self.event_map[kk]
            kt.flags = kt.flags | KTARGET_CLOSED
            del self.event_map[kk]
            W ('(notify_of_close (%d) [read])\n' % (fd,))
            co = kt.target
            try:
                co.__interrupt (ClosedError(the_scheduler._current))
            except ScheduleError:
                W ('notify_of_close (%d) [read]: unable to interrupt thread: %r\n' % (fd, co))

        kk = kevent_key (EVFILT_WRITE, fd)
        if self.event_map.has_key (kk):
            kt = self.event_map[kk]
            kt.flags = kt.flags | KTARGET_CLOSED
            del self.event_map[kk]
            W ('(notify_of_close (%d) [write])\n' % (fd,))
            co = kt.target
            try:
                co.__interrupt (ClosedError(the_scheduler._current))
            except ScheduleError:
                W ('notify_of_close (%d) [write]: unable to interrupt thread: %r\n' % (fd, co))

    def poll (self, timeout=(30,0), int nevents=2000):
        cdef timespec ts
        cdef int r, i
        cdef kevent * events
        cdef kevent * k
        cdef coro co
        cdef kevent_target kt
        cdef kevent_key kk
        cdef py_kevent py_event
        ts.tv_sec, ts.tv_nsec = timeout
        # poll() is only called from <main>, so alloca() is OK.
        events = <kevent *> alloca (sizeof (kevent) * nevents)
        if the_scheduler.profiling:
            the_profiler.charge_main()
        # Loop to handle EINTR.
        while 1:
            r = _kevent (
                self.kq_fd,
                self.change_list,
                self.change_list_index,
                events,
                nevents,
                &ts
                )
            if not (r==-1 and errno.errno==errno.EINTR):
                break
        if the_scheduler.profiling:
            the_profiler.charge_wait()
        if r == -1:
            raise_oserror()
        else:
            for i from 0 <= i < self.change_list_index:
                k = &(self.change_list[i])
                # We mark kevents with a filter of 0 when we want them ignored
                # (see KEVENT_STATUS_NEW in _wait_for).
                if k.filter != 0:
                    kk = kevent_key (k.filter, k.ident)
                    try:
                        kt = self.event_map[kk]
                    except KeyError:
                        # This should never happen.
                        P('Missing kevent from dictionary for filter=%r ident=%r (this should never happen).' % (
                            k.filter, k.ident))
                    else:
                        kt.status = KEVENT_STATUS_SUBMITTED


            self.change_list_index = 0
            #W ('{%d}' % (r,))
            #P('mapsize = %i' % len(self.event_map))
            for i from 0 <= i < r:
                k = &(events[i])
                if k.flags & EV_ERROR:
                    W ('Error submitting kevent filter=%r ident=%r flags=%r fflags=%r data=%r.  Errno is in `data`.\n' % (
                        k.filter, k.ident, k.flags, k.fflags, k.data
                      ))
                else:
                    #W ('k: filter=%d ident=%x flags=%x fflags=%x data=%d\n' % (
                    #    k.filter, <unsigned long>k.ident, k.flags, k.fflags, k.data
                    #    ))
                    py_event = py_kevent()
                    py_event.__fast_init__(k)
                    kk = kevent_key (k.filter, k.ident)
                    try:
                        kt = self.event_map[kk]
                    except KeyError:
                        W ('un-handled kevent: ident=%x filter=%x\n' % (k.ident, k.filter))
                    else:
                        assert kt.status != KEVENT_STATUS_ABORTED
                        try:
                            kt.status = KEVENT_STATUS_FIRED
                            if isinstance (kt.target, coro):
                                co = kt.target
                                co._schedule (py_event)
                            else:
                                # assumes kt.target is a callable object
                                _spawn(kt.target, (py_event,), {})
                        finally:
                            if k.flags & EV_ONESHOT or kt.flags & KTARGET_FLAG_ONESHOT:
                                del self.event_map[kk]
