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

__poller_version__ = "$Id"

# ================================================================================
#                                epoll
# ================================================================================

from libc cimport uint64_t, uint32_t
from libc cimport uint64_t

cdef extern from "sys/time.h":
    cdef struct timespec:
        unsigned int tv_sec
        unsigned int tv_nsec

cdef extern from "sys/epoll.h":
    ctypedef union epoll_data_t:
        void *ptr
        int fd
        uint32_t u32
        uint64_t u64

    cdef struct epoll_event:
        uint32_t events
        epoll_data_t data

    int epoll_create(int size)

    int epoll_ctl (
        int epfd,
        int op,
        int fd,
        epoll_event *event
        )

    int epoll_wait (
        int epfd,
        epoll_event *events,
        int maxevents,
        int timeout
        )

    int EPOLL_CTL_ADD, EPOLL_CTL_MOD, EPOLL_CTL_DEL
    int EPOLLHUP, EPOLLPRI, EPOLLERR, EPOLLET, EPOLLONESHOT, EPOLLRDHUP
    int EPOLLIN, EPOLLOUT

cdef struct fake_epoll_event:
    uint32_t events
    epoll_data_t data
    int op
    int flags
    int err

cdef int SECS_TO_MILLISECS = 1000
cdef double NSECS_TO_MILLISECS = 1000000.0

class EV:

    """epoll flags."""

    ADD      = EPOLL_CTL_ADD        # add event to kq (implies enable)
    DELETE   = EPOLL_CTL_DEL     # delete event from kq
    ONESHOT  = EPOLLONESHOT    # only report one occurrence
    EOF      = EPOLLHUP        # EOF detected
    ERROR    = EPOLLERR      # error, data contains errno

class EFILT:

    """epoll event filters."""

    READ     = EPOLLIN   #
    WRITE    = EPOLLOUT  #

# Definition of epoll status flags:
# - NEW: Target is new, event not yet submitted.
# - SUBMITTED: The event has been submitted to epoll.
# - FIRED: The event has fired.
# - ABORTED: The event has been aborted (typically by Interrupted exception).
#            The event may or may not have already been submitted.
cdef enum:
    EVENT_STATUS_NEW
    EVENT_STATUS_SUBMITTED
    EVENT_STATUS_FIRED
    EVENT_STATUS_ABORTED

# - ONESHOT: Used to indicate that this target should be removed from the
#            event map after it fires.
# - CLOSED: For file-descriptor events, this indicates that the file
#           descriptor has been closed, and that the event key has been
#           removed from the event map.
cdef enum:
    TARGET_FLAG_ONESHOT = 1
    TARGET_CLOSED       = 2

cdef class event_target:
    cdef public int status
    cdef public int index
    cdef public object target
    cdef public int flags

    def __cinit__ (self, target, int index):
        self.status = EVENT_STATUS_NEW
        self.index = index
        self.target = target
        self.flags = 0

    def __repr__ (self):
        return '<event_target status=%r index=%r target=%r flags=%r>' % (self.status,
            self.index, self.target, self.flags)

cdef class py_event:

    """Representation of a epoll event.

    :IVariables:
        - `events`: Epoll events
        - `data`: User data variable
    """

    cdef uint32_t events
    cdef epoll_data_t data
    cdef int flags
    cdef int err

    # cinit cannot take a C struct.
    # It would be nice to support fast-constructor semantics in Cython.
    cdef __fast_init__ (self, fake_epoll_event *e):
        self.events = e.events
        self.data.fd = e.data.fd
        self.flags = e.flags
        self.err = e.err 

    def __repr__(self):
        return '<py_event events=%r>' % (self.events)

cdef class event_key:

    """event key.

    All epoll events are uniquely identified by a key which is a combination of the
    events and fd.

    :IVariables:
        - `events`: The event filter (see `EFILT`).
        - `data`: The data identifier (depends on the filter type, but is
          often a file descriptor).
    """

    cdef int events
    cdef int fd
    cdef int op

    def __cinit__ (self, int events, int fd, int op=EPOLL_CTL_ADD):
        self.events = events
        self.fd = fd
        self.op = op

    def __hash__ (self):
        cdef int value
        value = (self.fd << 4) | (self.events)
        if value == -1:
            value = -2
        return value

    def __repr__ (self):
        return '<event_key events=%d fd=%x>' % (self.events, self.fd)

    def __richcmp__ (event_key self, event_key other, int op):
        # all we need is EQ, ignore the rest
        if op != 2:
            raise ValueError, "event_key() only supports '==' rich comparison"
        else:
            return (self.events == other.events) and (self.fd == other.fd)

cdef public class queue_poller [ object queue_poller_object, type queue_poller_type ]:

    cdef fake_epoll_event * change_list
    cdef int change_list_index
    cdef int ep_fd
    cdef object event_map

    def __cinit__ (self):
        # XXX EVENT_SCALE should be a parameter.
        self.change_list = <fake_epoll_event *>PyMem_Malloc (sizeof (fake_epoll_event) * EVENT_SCALE)

    def __dealloc__ (self):
        PyMem_Free (self.change_list)

    def __init__ (self):
        self.change_list_index = 0
        self.ep_fd = -1
        self.event_map = {}

    cdef set_up(self):
        self.ep_fd = epoll_create(1000)
        if self.ep_fd == -1:
            raise SystemError, "epoll_create() failed"

    cdef tear_down(self):
        if self.ep_fd != -1:
            libc.close(self.ep_fd)
            self.ep_fd = -1

    cdef object set_wait_for (self, event_key ek):
        cdef fake_epoll_event *e
        cdef coro me
        cdef event_target et
        if self.change_list_index < EVENT_SCALE:
            if PyDict_Contains (self.event_map, ek):
                # Should be impossible to have KeyError due to previous line.
                et = self.event_map[ek]
                raise SimultaneousError (the_scheduler._current, et.target, ek)
            else:
                me = the_scheduler._current
                target = event_target (me, self.change_list_index)
                target.flags = TARGET_FLAG_ONESHOT
                self.event_map[ek] = target
                e = &(self.change_list[self.change_list_index])
                e.data.fd = ek.fd
                e.op = EPOLL_CTL_ADD
                e.events = ek.events 
                e.flags = EPOLLONESHOT
                self.change_list_index = self.change_list_index + 1
                return target
        else:
            raise SystemError, "too many events in change_list"

    cdef _wait_for_with_eof (self, int fd, int events):
        cdef py_event event
        event = self._wait_for (fd, events)
        if event.err:
            raise_oserror_with_errno(event.err)
        else:
            return 1024

    cdef _wait_for_read (self, int fd):
        return self._wait_for_with_eof(fd, EPOLLIN)

    cdef _wait_for_write (self, int fd):
        return self._wait_for_with_eof(fd, EPOLLOUT)

    def wait_for_read (self, int fd):
        return self._wait_for_with_eof(fd, EPOLLIN)

    def wait_for_write (self, int fd):
        return self._wait_for_with_eof(fd, EPOLLOUT)

    cdef py_event _wait_for (self, int fd, int events):
        cdef event_target et
        cdef fake_epoll_event *e
        cdef event_key ek
        ek = event_key (events, fd)
        et = self.set_wait_for (ek)
        try:
            return _YIELD()
        finally:
            if et.status == EVENT_STATUS_NEW:
                # still in the change list
                e = &self.change_list[et.index]
                # event() will ignore this entry
                e.events = 0
                e.data.fd = 0
                et.status = EVENT_STATUS_ABORTED
                if not et.flags & TARGET_CLOSED:
                    # remove from event map
                    del self.event_map[ek]
                #W ('wait_for() cleanup: (%d, %d) STATUS_NEW\n' % (ident, filter))
            elif et.status == EVENT_STATUS_SUBMITTED:
                # event submitted, delete it.
                et.status = EVENT_STATUS_ABORTED
                if not et.flags & TARGET_CLOSED:
                    self.delete_event (fd, events)
                    # remove from event map
                    del self.event_map[ek]
                #W ('wait_for() cleanup: (%d, %d) STATUS_SUBMITTED\n' % (ident, filter))
            elif et.status == EVENT_STATUS_FIRED:
                # event already fired! do nothing.
                #W ('wait_for() cleanup: (%d, %d) STATUS_FIRED\n' % (ident, filter))
                pass

    def wait_for (self, int fd, int events):
        """Wait for an event.

        :Parameters:
            - `ident`: The event identifier (depends on the filter type, but
              is often a file descriptor).
            - `filter`: The event filter (see `EVFILT`).

        :Return:
            Returns a `py_event` instance that indicates the event that fired.

        :Exceptions:
            - `SimultaneousError`: Something is already waiting for this event.
        """
        return self._wait_for(fd, events)

    cdef delete_event (self, int fd, int events):
        cdef int r
        cdef epoll_event e
        e.data.fd = fd
        e.events = events | EPOLLONESHOT
        r = epoll_ctl (self.ep_fd, EPOLL_CTL_DEL, fd, &e)
        #if r < 0:
        #    raise_oserror()

    def set_handler (self, object event, object handler, int flags=EPOLLONESHOT, int op=EPOLL_CTL_ADD):
        """Add a event handler.

        This is a low-level interface to register a event handler.

        :Parameters:
            - `event`: A tuple of ``(ident, filter)`` of the event to handle.
            - `handler`: The handler to use,  a callable object which will be
              called with one argument, a `py_event` object.
            - `flags`: Kevent flags to use.  Defaults to ``EV_ADD|EV_ONESHOT``.

        :Exceptions:
            - `SimultaneousError`: There is already a handler set for this
              event.
        """
        cdef int events 
        cdef int fd
        cdef fake_epoll_event * e
        cdef event_key ek
        assert callable(handler)

        fd = PySequence_GetItem(event, 0)
        events = PySequence_GetItem(event, 1)
        #events |= flags          
        ek = event_key (events, fd)
        if PyDict_Contains (self.event_map, ek):
            # Should be impossible to have KeyError due to previous line.
            et = self.event_map[ek]
            raise SimultaneousError (the_scheduler._current, et.target, ek)
        else:
            if self.change_list_index < EVENT_SCALE:
                e = &(self.change_list[self.change_list_index])
                e.data.fd = fd
                e.events = events
                e.op = op
                e.flags = flags
                self.change_list_index = self.change_list_index + 1
                et = event_target (handler, self.change_list_index)
                self.event_map[ek] = et
            else:
                raise SystemError, "too many events in change_list"

    cdef set_event_target (self, object event, event_target et):
        cdef int filter
        cdef int fd
        cdef event_key ek

        fd = PySequence_GetItem(event, 0)
        filter = PySequence_GetItem(event, 1)
        ek = event_key (filter, fd)
        self.event_map[ek] = et

    cdef notify_of_close (self, int fd):
        cdef event_target et
        cdef coro co
        cdef event_key ek
        cdef epoll_event e

        ek = event_key (EPOLLIN, fd)
        if PyDict_Contains(self.event_map, ek):
            et = self.event_map[ek]
            et.flags = et.flags | TARGET_CLOSED
            del self.event_map[ek]
            W ('(notify_of_close (%d) [read])\n' % (fd,))
            co = et.target
            try:
                co.__interrupt (ClosedError(the_scheduler._current))
            except ScheduleError:
                W ('notify_of_close (%d) [read]: unable to interrupt thread: %r\n' % (fd, co))

        ek = event_key (EPOLLOUT, fd)
        if PyDict_Contains(self.event_map, ek):
            et = self.event_map[ek]
            et.flags = et.flags | TARGET_CLOSED
            del self.event_map[ek]
            W ('(notify_of_close (%d) [write])\n' % (fd,))
            co = et.target
            try:
                co.__interrupt (ClosedError(the_scheduler._current))
            except ScheduleError:
                W ('notify_of_close (%d) [write]: unable to interrupt thread: %r\n' % (fd, co))

    def poll (self, timeout=(30,0), int nevents=2000):
        cdef timespec ts
        cdef int r, i
        cdef epoll_event * events, ee
        cdef fake_epoll_event *e, new_e
        cdef epoll_event org_e
        cdef coro co
        cdef event_target et
        cdef event_key ek
        cdef py_event _py_event
        ts.tv_sec, ts.tv_nsec = timeout
        # poll() is only called from <main>, so alloca() is OK.
        events = <epoll_event *> libc.alloca (sizeof (epoll_event) * nevents)

        for i from 0 <= i < self.change_list_index:
            e = &(self.change_list[i])
            org_e.events = e.events | EPOLLET
            org_e.data.fd = e.data.fd
            # try to add fd to epoll
            if e.events != 0:
                r = epoll_ctl (
                    self.ep_fd,
                    e.op,
                    org_e.data.fd,
                    &org_e
                )
                # if fd already exist, then modify to to register intrest in read/write
                if r == -1 and (libc.errno == libc.EEXIST):
                    org_e.events = e.events | EPOLLOUT | EPOLLIN | EPOLLET
                    r = epoll_ctl (
                        self.ep_fd,
                        EPOLL_CTL_MOD,
                        org_e.data.fd,
                        &org_e
                    )
                #print 'epoll_ctl event >>>>>> %s for %s' % (org_e.events, org_e.data.fd)
                if r == -1 and (libc.errno != libc.EEXIST):
                    raise_oserror()
        r = epoll_wait (self.ep_fd, events, nevents, timeout[0] * SECS_TO_MILLISECS + (timeout[1] / NSECS_TO_MILLISECS))

        if the_scheduler.profiling:
            the_profiler.charge_wait()
        if r == -1:
            raise_oserror()
        else:
            for i from 0 <= i < self.change_list_index:
                e = &(self.change_list[i])
                # We mark events with a filter of 0 when we want them ignored
                # (see EVENT_STATUS_NEW in _wait_for).
                if e.events != 0:
                    ek = event_key (e.events, e.data.fd)
                    try:
                        et = self.event_map[ek]
                    except KeyError:
                        # This should never happen.
                        P('Missing event from dictionary for events=%r fd=%r (this should never happen).' % (
                            e.events, e.data.fd))
                    else:
                        et.status = EVENT_STATUS_SUBMITTED


            self.change_list_index = 0
            #W ('{%d}' % (r,))
            #P('mapsize = %i' % len(self.event_map))
            for i from 0 <= i < r:
                new_e.data.fd = events[i].data.fd
                new_e.events = events[i].events
                new_e.err = 0
                #print 'epoll_wait event >>>>>> %s for %s' % (new_e.events, new_e.data.fd)
                tmp = (EPOLLIN, EPOLLOUT)
                if events[i].events & tmp[0] and events[i].events & tmp[1]:
                    pass
                else:
                    tmp = [0]
                for j from 0 <= j < len(tmp):
                    if len(tmp) == 2:
                        if events[i].events & tmp[j]:
                            new_e.events = events[i].events & ~(tmp[j])
 
                    if new_e.events & EPOLLERR or new_e.events & EPOLLHUP:
                        #print 'epoll_wait event >>>>>> %s for %s' % (new_e.events, new_e.data.fd)
                        new_e.events = new_e.events & ~(EPOLLHUP)
                        new_e.events = new_e.events & ~(EPOLLERR)
                        new_e.err = 104
                        # epoll doesn't specify the last event we had registered so make a guess
                        if new_e.events == 0:
                            new_e.events = EPOLLIN
                            try:
                                et = self.event_map[event_key(EPOLLIN, new_e.data.fd)]
                            except KeyError:
                                new_e.events = EPOLLOUT

                    _py_event = py_event()
                    _py_event.__fast_init__(&new_e)
                    ek = event_key (new_e.events, new_e.data.fd)
                    if not PyDict_Contains (self.event_map, ek):
                        continue
                    try:
                        et = self.event_map[ek]
                    except KeyError:
                        W ('un-handled event: fd=%s events=%s\n' % (new_e.data.fd, new_e.events))
                    else:
                        assert et.status != EVENT_STATUS_ABORTED
                        try:
                            et.status = EVENT_STATUS_FIRED
                            if isinstance (et.target, coro):
                                co = et.target
                                co._schedule (_py_event)
                            else:
                                # assumes kt.target is a callable object
                                _spawn(et.target, (_py_event,), {})
                        finally:
                            if et.flags & TARGET_FLAG_ONESHOT:
                                del self.event_map[ek]
