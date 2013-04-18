# -*- Mode: Python -*-

import coro
from kqueue_events import *

def register (fd, callback, what=NOTE_DELETE, once_only=1):
    # register with kqueue
    # without EV_CLEAR the event triggers repeatedly for a single write
    flags = EV_ADD | EV_CLEAR
    if once_only:
        flags |= EV_ONESHOT

    coro.set_handler ((fd, EVFILT_VNODE), callback, flags, what)
