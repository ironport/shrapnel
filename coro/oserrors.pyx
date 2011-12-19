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

"""OSError mapping.

This module maps OSErrors to specific, catchable exceptions.  For example, an
OSError with an errno of ENOENT will be raised as the ENOENT exception.  All
exceptions derive from OSError, so it is compatible with regular OSError
handling.
"""

include "python.pxi"

import errno
import new
import sys
cimport libc

err_map = {}

def map_exception(e):
    """Raise an errno-specific exception.

    :Parameters:
        - `e`: The OSError instance.
    """
    # Ignoring e.filename since it seems less than useful to me.
    try:
        raise err_map[e.errno](e.errno, e.strerror)
    except KeyError:
        raise e

def raise_oserror(int error_number):
    """Raise an OSError exception by errno.

    :Parameters:
        - `error_number`: The errno value to raise.
    """
    map_exception(OSError(error_number, libc.strerror(error_number)))

__m = sys.modules['coro.oserrors']
__g = __m.__dict__
for errcode, errname in errno.errorcode.items():
    # Not sure why __module__ is not getting set properly.  Python looks at
    # globals() to fine __name__ to set the value, and it appears to be
    # set to __main__ for some odd reason.
    c = new.classobj(errname, (OSError,), {'__module__': 'coro.oserrors'})
    err_map[errcode] = c
    __g[errname] = c
