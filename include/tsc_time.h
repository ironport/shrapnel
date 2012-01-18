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

This header file provides a method to access the C functions from the tsc_time
module directly.

To use, include this header file in your C extension module.  In the
initmodulename function, be sure to call init_tsc_time_pointers().

The raw conversion functions can be called directly like this:

    int64_t t = usec_to_ticks(somevalue);

The constructors can be called like this:

    TSC * t = now_tsc();
    printf("%llu\n", t.tsc);

The structures are provided so that you can access the "tsc" value directly.

The type objects are also available if you need to do type comparisons, but I
suspect this won't be necessary.

Note that there is a small memory leak because there is no finalizer here (when
Python exits).
*/
#ifndef _TSC_TIME_H_
#define _TSC_TIME_H_

#include "Python.h"
#include <inttypes.h>
#include <sys/types.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
  Pointers to the raw low-level conversion functions.
*/
static int64_t (*usec_to_ticks) (int64_t);
static int64_t (*ticks_to_usec) (int64_t);
static int64_t (*sec_to_ticks)  (int64_t);
static int64_t (*ticks_to_sec)  (int64_t);
static double  (*ticks_to_fsec) (int64_t);
static int64_t (*fsec_to_ticks) (double);
static void    (*update_time_relation) (void);
static int64_t (*rdtsc)         (void);

typedef struct Time {
    PyObject_HEAD
    int64_t tsc;
} Time;

typedef struct TSC {
    PyObject_HEAD
    int64_t tsc;
} TSC;

typedef struct Posix {
    PyObject_HEAD
    int64_t tsc;
} Posix;

typedef struct uPosix {
    PyObject_HEAD
    int64_t tsc;
} uPosix;

typedef struct fPosix {
    PyObject_HEAD
    int64_t tsc;
} fPosix;

static PyObject * Time_Type   = NULL;
static PyObject * TSC_Type    = NULL;
static PyObject * Posix_Type  = NULL;
static PyObject * uPosix_Type = NULL;
static PyObject * fPosix_Type = NULL;

/*
  Pointers to construction functions.
*/
static TSC *    (*now_tsc)(void);
static Posix *  (*now_posix_sec)(void);
static uPosix * (*now_posix_usec)(void);
static fPosix * (*now_posix_fsec)(void);

/*
  Initialize pointers to the tsc_time module.

  Returns 0 on success, -1 on failure (with python exception set).
*/
int
init_tsc_time_pointers(void)
{
    PyObject * m = NULL;
    PyObject * c_obj = NULL;
    void ** c_ptr;

    if (Time_Type != NULL) {
        // Already initialized.
        return 0;
    }

    m = PyImport_ImportModule("coro.clocks.tsc_time");
    if (m == NULL) {
        goto fail;
    }

    c_obj = PyObject_GetAttrString(m, "_extern_pointers");
    if (c_obj == NULL) {
        goto fail;
    }

    c_ptr = (void **) PyCObject_AsVoidPtr(c_obj);
    if (c_ptr == NULL) {
        goto fail;
    }

    usec_to_ticks = (int64_t (*)(int64_t)) c_ptr[0];
    ticks_to_usec = (int64_t (*)(int64_t)) c_ptr[1];
    sec_to_ticks =  (int64_t (*)(int64_t)) c_ptr[2];
    ticks_to_sec =  (int64_t (*)(int64_t)) c_ptr[3];
    ticks_to_fsec = (double  (*)(int64_t)) c_ptr[4];
    fsec_to_ticks = (int64_t (*)(double))  c_ptr[5];
    update_time_relation = (void (*)(void)) c_ptr[6];
    now_tsc =             (TSC * (*)(void)) c_ptr[7];
    now_posix_sec =     (Posix * (*)(void)) c_ptr[8];
    now_posix_usec =   (uPosix * (*)(void)) c_ptr[9];
    now_posix_fsec =   (fPosix * (*)(void)) c_ptr[10];
    rdtsc =             (int64_t (*)(void)) c_ptr[11];

    Time_Type   = PyObject_GetAttrString(m, "Time");
    TSC_Type    = PyObject_GetAttrString(m, "TSC");
    Posix_Type  = PyObject_GetAttrString(m, "Posix");
    uPosix_Type = PyObject_GetAttrString(m, "uPosix");
    fPosix_Type = PyObject_GetAttrString(m, "fPosix");

    Py_DECREF(m);
    Py_DECREF(c_obj);
    return 0;

fail:
    Py_XDECREF(m);
    Py_XDECREF(c_obj);
    return -1;
}

#ifdef __cplusplus
} /* extern C */
#endif

#endif /* _TSC_TIME_H_ */
