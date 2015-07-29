cdef extern from "stdarg.h":

    # The type of va_list is not a standard definition.
    # This should be a rather opaque type.
    ctypedef void * va_list

    # va_arg support is not possible in Pyrex.  Some hard-coded types
    # are available in pyrex_helpers.pyx.
    void va_start(va_list ap, last)
    void va_copy(va_list dest, va_list src)
    void va_end(va_list ap)
