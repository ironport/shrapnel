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

# Pyrex interface file for inline helpers.
# Use the "include" statement to include these functions.
# You must include "python.pxi" before this file.

cdef object oserrors
from coro import oserrors
from xlibc cimport stdarg

from libc cimport string
from libc cimport errno

cdef raise_oserror():
    oserrors.map_exception (OSError (errno.errno, string.strerror (errno.errno)))

cdef raise_oserror_with_errno (int e):
    oserrors.map_exception (OSError (e, string.strerror (e)))

cdef object __builtin__
import __builtin__

cdef object bool
bool = __builtin__.bool

cdef extern from "pyrex_helpers.h":

    int     va_int(stdarg.va_list)
    char *  va_charptr(stdarg.va_list)

    object  PySequence_Fast_GET_ITEM_SAFE   (object, int)

    object  PyList_GET_ITEM_SAFE    (object, int)
    void    PyList_SET_ITEM_SAFE    (object, int, object)
    object  PyList_GetItem_SAFE     (object, int)
    void    PyList_SetItem_SAFE     (object, int, object)

    object  PyTuple_GET_ITEM_SAFE   (object, int)
    void    PyTuple_SET_ITEM_SAFE   (object, int, object)
    object  PyTuple_GetItem_SAFE    (object, int)
    void    PyTuple_SetItem_SAFE    (object, int, object)

    object  PyDict_GET_ITEM_SAFE    (object, object, object)

    void *  Pyrex_Malloc_SAFE       (size_t) except NULL
    void *  Pyrex_Realloc_SAFE      (void *, size_t) except NULL
    void    Pyrex_Free_SAFE         (void *)

    object  minimal_ulonglong       (unsigned long long)
    object  minimal_long_long       (long long)
    object  minimal_ulong           (unsigned long)

    int     callable                (object)         # Cannot fail.
    int     cmp                     (object, object) except? -1
    object  type                    (object)

    int     IMAX                    (int, int)
    int     IMIN                    (int, int)
