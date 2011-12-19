/*
 Copyright (c) 2002-2011 IronPort Systems and Cisco Systems

 Permission is hereby granted, free of charge, to any person obtaining a copy  
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights  
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell 
 copies of the Software, and to permit persons to whom the Software is 
 furnished to do so, subject to the following conditions:

 The above copyright notice and this permission notice shall be included in 
 all copies or substantial portions of the Software.

 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
 AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 SOFTWARE.
*/

/*
    Helper functions for Pyrex.

    These will be (hopefully) inlined into your code.  Say:

        include "pyrex_helpers.pyx"

    in your Pyrex file to include these functions.
*/

#ifndef _PYREX_HELPERS_H_
#define _PYREX_HELPERS_H_

#include "Python.h"

#define PyINLINE_FUNC(RTYPE) static __attribute__ ((no_instrument_function)) inline RTYPE

/* Support varargs support.
   If there is a C type that you need that is not here, feel free to add it.
   Someday Pyrex may have native support for this.
*/
#define va_int(ap) va_arg(ap, int)
#define va_charptr(ap) va_arg(ap, char *)

/* Convenience/performance. */
#define IMAX(a,b) ((a) > (b) ? (a) : (b))
#define IMIN(a,b) ((a) < (b) ? (a) : (b))

/* Converting Python builtins to direct calls. */
#define callable(o)             PyCallable_Check(o)
#define type(o)                 PyObject_Type(o)

/* Abstract functions. */
PyINLINE_FUNC(PyObject *)
PySequence_Fast_GET_ITEM_SAFE (PyObject * o, int i)
{
    PyObject * x = PySequence_Fast_GET_ITEM(o, i);
    Py_INCREF(x);
    return x;
}

PyINLINE_FUNC(int)
cmp (PyObject * o1, PyObject * o2)
{
    int result;

    if(PyObject_Cmp(o1, o2, &result)) {
        return -1;
    } else {
        return result;
    }
}

/* List functions. */

PyINLINE_FUNC(PyObject *)
PyList_GET_ITEM_SAFE (PyObject * l, int i)
{
    PyObject * x = PyList_GET_ITEM (l, i);
    Py_INCREF (x);
    return x;
}

PyINLINE_FUNC(void)
PyList_SET_ITEM_SAFE (PyObject * l, int i, PyObject * v)
{
    PyList_SET_ITEM (l, i, v);
    Py_INCREF (v);
}

PyINLINE_FUNC(PyObject *)
PyList_GetItem_SAFE (PyObject * l, int i)
{
    PyObject * x = PyList_GetItem (l, i);
    Py_INCREF (x);
    return x;
}

PyINLINE_FUNC(void)
PyList_SetItem_SAFE (PyObject * l, int i, PyObject * v)
{
    PyList_SetItem (l, i, v);
    Py_INCREF (v);
}

/* Tuple functions. */

PyINLINE_FUNC(PyObject *)
PyTuple_GET_ITEM_SAFE (PyObject * l, int i)
{
    PyObject * x = PyTuple_GET_ITEM (l, i);
    Py_INCREF (x);
    return x;
}

PyINLINE_FUNC(void)
PyTuple_SET_ITEM_SAFE (PyObject * l, int i, PyObject * v)
{
    PyTuple_SET_ITEM (l, i, v);
    Py_INCREF (v);
}

PyINLINE_FUNC(PyObject *)
PyTuple_GetItem_SAFE (PyObject * l, int i)
{
    PyObject * x = PyTuple_GetItem (l, i);
    Py_INCREF (x);
    return x;
}

PyINLINE_FUNC(void)
PyTuple_SetItem_SAFE (PyObject * l, int i, PyObject * v)
{
    PyTuple_SetItem (l, i, v);
    Py_INCREF (v);
}

/* Dict functions. */

/*
  Note, you *must* set ``instead`` to a real Python object, you cannot set it
  to NULL.  Suggest using None.
*/
PyINLINE_FUNC(PyObject *)
PyDict_GET_ITEM_SAFE (PyObject * d, PyObject * k, PyObject * instead)
{
    PyObject * r = PyDict_GetItem (d, k);
    if (r == NULL) {
        r = instead;
    }
    Py_INCREF (r);
    return r;
}

/* Memory functions. */

/*
  These functions are "safe" in that they set MemoryError if it fails.
  Note that "free" doesn't do anything special, it's just here to maintain a
  consistent naming scheme.
*/

PyINLINE_FUNC(void *)
Pyrex_Malloc_SAFE(size_t size)
{
    void * r;

    r = PyMem_Malloc(size);
    if (r == NULL) {
        PyErr_NoMemory();
        return NULL;
    } else {
        return r;
    }
}

PyINLINE_FUNC(void *)
Pyrex_Realloc_SAFE(void * ptr, size_t size)
{
    void * r;

    r = PyMem_Realloc(ptr, size);
    if (r == NULL) {
        PyErr_NoMemory();
        return NULL;
    } else {
        return r;
    }
}

PyINLINE_FUNC(void)
Pyrex_Free_SAFE(void * ptr)
{
    PyMem_Free(ptr);
}


/* Number functions. */
PyINLINE_FUNC(PyObject *)
minimal_ulonglong(unsigned long long value)
{
    if (value > PyInt_GetMax()) {
        return PyLong_FromUnsignedLongLong(value);
    } else {
        return PyInt_FromLong(value);
    }
}

PyINLINE_FUNC(PyObject *)
minimal_long_long(long long value)
{
    if (value > PyInt_GetMax() || value < -PyInt_GetMax()-1) {
        return PyLong_FromLongLong(value);
    } else {
        return PyInt_FromLong(value);
    }
}

PyINLINE_FUNC(PyObject *)
minimal_ulong(unsigned long value)
{
    if (value > PyInt_GetMax()) {
        return PyLong_FromUnsignedLong(value);
    } else {
        return PyInt_FromLong(value);
    }
}

#endif

