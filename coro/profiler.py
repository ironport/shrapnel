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

# $Header: //prod/main/ap/shrapnel/coro/profiler.py#9 $

"""Coro code profiler.

Introduction
============
This profiler is coro-aware.  It produces output to a binary file on disk. You
then use the :mod:`coro.print_profile` module to convert it to an HTML file.

Using The Profiler
==================
There are two ways to run the profiler.  One is to use the
:func:`coro.profiler.go` function where you give it a python function to run.
Profiling will start and call the function, and then the profiler will
automatically stop when the function exits.

The other method is to call :func:`coro.profiler.start` to start the profiler
and :func:`coro.profiler.stop` when you want to stop profiling.  This can be
conveniently done from the backdoor.

Rendering Output
================
Once you have profiler output, you must use the ``print_profile`` module
to convert it to HTML.  The typical method for doing this is::

    python -m coro.print_profile /tmp/coro_profile.bin > my_profile.html

Then view the profile output in your web browser.

Profiler Types
==============
The profiler supports different ways of gathering statistics.  This is done by
specifying the "bench" object to use (see :func:`go` and :func:`start`).  They
default to the "rusage" method of gathering statistics about every function
call (see the getrusage man page for more detail).  If you want a higher
performance profile, you can use the :class:`coro.bench` object instead which
simply records TSC values for every function call.  If you want to define your
own method of gathering statistics, subclass :class:`coro.bench` and implement
your own techniques.

"""

import coro
import cPickle
import time

MAGIC = 'SHRAP_PROF1'

def _dump(p, filename):
    f = open(filename, 'w')
    f.write(MAGIC)
    data = (p.bench_class.__name__, p.bench_class().get_headings(), time.time())
    cPickle.dump(data, f, -1)

    # Dump profile data.
    data = {}
    for func, bench in p.charges.iteritems():
        data[func.as_str()] = bench.get_data()
    cPickle.dump(data, f, -1)

    # Dump call data.
    data = {}
    for caller, cc in p.call_counts.iteritems():
        count_data = cc.get()
        result = []
        for callee, count in count_data:
            element = (callee.as_str(), count)
            result.append(element)
        data[caller.as_str()] = result
    cPickle.dump(data, f, -1)
    f.close()

def go (fun, *args, **kwargs):
    """Start the profiler on a function.

    This will start the profiler, and then call the provided function.
    The profiler will shut down once the function returns.

    Additional arguments provided are passed to the function.

    This will display the results to stdout after the function is finished.

    :param fun: The function to call.

    :keyword profile_filename: The name of the file to save the profile data.
          Defaults to '/tmp/coro_profile.bin'.
    :keyword profile_bench: The bench object type to use.  Defaults to
          :class:`coro.rusage_bench`.
    """
    if 'profile_filename' in kwargs:
        profile_filename = kwargs['profile_filename']
        del kwargs['profile_filename']
    else:
        profile_filename = '/tmp/coro_profile.bin'

    if 'profile_bench' in kwargs:
        profile_bench = kwargs['profile_bench']
        del kwargs['profile_bench']
    else:
        profile_bench = coro.rusage_bench

    p = coro.new_profiler (profile_bench)
    p.start()
    try:
        return fun (*args, **kwargs)
    finally:
        total_ticks = p.stop()
        user_ticks = _dump (p, profile_filename)

def start(profile_bench=coro.rusage_bench):
    """Start the profiler.

    :Parameters:
        - `profile_bench`: The profiler type to use.
    """
    p = coro.new_profiler(profile_bench)
    p.start()

def stop(filename='/tmp/coro_profile.bin'):
    """Stop the profiler.

    :Parameters:
        - `filename`: The filename to use for the profile output.
    """
    p = coro.get_the_profiler()
    p.stop()
    _dump(p, filename)

def tak1 (x, y, z):
    if y >= x:
        return z
    else:
        return tak1 (
            tak1 (x - 1, y, z),
            tak2 (y - 1, z, x),
            tak2 (z - 1, x, y)
        )

def tak2 (x, y, z):
    if y >= x:
        return z
    else:
        return tak2 (
            tak2 (x - 1, y, z),
            tak1 (y - 1, z, x),
            tak1 (z - 1, x, y)
        )

if __name__ == '__main__':
    go (tak2, 18, 12, 6)
    print 'now run print_profile.py ...'
