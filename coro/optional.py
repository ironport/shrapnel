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

# $Header: //prod/main/ap/shrapnel/coro/optional.py#3 $

"""Functions that can run in or out of coro.

This module provides emulation for some functions to run whether or not the
coro event loop is running.
"""

import coro
import signal
import time

class _shutdown_sigalrm_exc (Exception):
    pass

def _shutdown_sigalrm_handler(unused_signum, unused_frame):
    raise _shutdown_sigalrm_exc

def with_timeout(timeout, function, *args, **kwargs):
    """Call a function with a timeout.

    This version supports running even if the coro event loop isn't running by
    using SIGALRM.

    See `coro._coro.sched.with_timeout` for more detail.

    :Parameters:
        - `timeout`: The number of seconds to wait before raising the timeout.
          May be a floating point number.
        - `function`: The function to call.

    :Return:
        Returns the return value of the function.

    :Exceptions:
        - `coro.TimeoutError`: The timeout expired.
    """
    if coro.coro_is_running():
        return coro.with_timeout(timeout, function, *args, **kwargs)
    else:
        # Use sigalarm to do the magic.
        old_sigalrm_handler = signal.signal(signal.SIGALRM, _shutdown_sigalrm_handler)
        try:
            try:
                signal.alarm(timeout)
                return function(*args, **kwargs)
            except _shutdown_sigalrm_exc:
                raise coro.TimeoutError
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_sigalrm_handler)

def sleep_relative(delta):
    """Sleep for a period of time.

    :Parameters:
        - `delta`: The number of seconds to sleep.
    """
    time.sleep(delta)
