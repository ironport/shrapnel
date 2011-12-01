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

#ifndef _EVENT_QUEUE_H_
#define _EVENT_QUEUE_H_

#include "Python.h"

/* Types are defined as void * to fake out Pyrex which can't handle C++ types. */

//typedef std::multimap <long long, PyObject *> event_queue;
typedef void * event_queue;

event_queue * event_queue_new(void);
void          event_queue_dealloc(event_queue * q);
PyObject *    event_queue_top(event_queue * q, uint64_t * time);
PyObject *    event_queue_pop(event_queue * q, uint64_t * time);
int           event_queue_insert(event_queue * q, uint64_t time, PyObject * value);
int           event_queue_delete(event_queue * q, uint64_t time, PyObject * value);
int           event_queue_len(event_queue * q);

//typedef event_queue::iterator event_queue_iter;
typedef void * event_queue_iter;
event_queue_iter event_queue_new_iter(event_queue * q);
PyObject *       event_queue_iter_next(event_queue * q, event_queue_iter * iter, uint64_t * time);

#endif /* _EVENT_QUEUE_H_ */
