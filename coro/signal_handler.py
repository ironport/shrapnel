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

# $Header: //prod/main/ap/shrapnel/coro/signal_handler.py#8 $

"""Signal handler."""

import coro
import signal
import os

UNAME = os.uname()[0]

def register (signum, handler, once_only=False):
    """Register a signal handler.

    :Parameters:
        - `signum`: The signal number to register.
        - `handler`: A callable object that takes one parameter which is the
          signal number that was triggered.
        - `once_only`: If True, will only trigger once, and then disable the
          signal handler.  Defaults to False.

    :Exceptions:
        - `coro.SimultaneousError`: Another handler is already registered for
          this signal.
    """

    if UNAME in ('FreeBSD', 'Darwin'):
        # first, turn *off* normal signal handling...
        signal.signal (signum, signal.SIG_IGN)
        # register with kqueue
        flags = coro.EV.ADD
        if once_only:
            flags |= coro.EV.ONESHOT
        k_handler = lambda x: handler(x.ident)
        coro.set_handler ((signum, coro.EVFILT.SIGNAL), k_handler, flags)
    else:
        signal.signal(signum, handler)


# alias for backward compatibility
register_signal_handler = register
