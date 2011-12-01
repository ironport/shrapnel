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

#include "Python.h"
#include <map>
typedef std::multimap <unsigned long long, PyObject *> event_queue;
typedef event_queue::iterator event_queue_iter;

/* Needed because Pyrex is compiled as a C program and is expecting C-like
   symbols.
*/
extern "C" {

/*
  Create a new event queue.
*/
event_queue *
event_queue_new()
{
    return new event_queue;
}

/*
  Delete the event queue and free all data.
*/
void 
event_queue_dealloc(event_queue * q)
{
    event_queue_iter iter;
    for (iter = q->begin(); iter != q->end(); iter++) {
        Py_DECREF(iter->second);
    }
    delete q;
}

/*
  Returns the length of the queue.
*/
int
event_queue_len(event_queue * q)
{
    return q->size();
}

/*
  Returns a new iterator.
*/
event_queue_iter
event_queue_new_iter(event_queue * q)
{
    return q->begin();
}

/*
  Return the current value of the iterator and move the position forward.
  The timestamp of the first element is stored in time (if not NULL).  The value is returned.
  Returns NULL if the queue is empty with StopIteration set.
*/
PyObject * 
event_queue_iter_next(event_queue * q, event_queue_iter * iter, uint64_t * time)
{
    PyObject * value;
    
    if (*iter == q->end()) {
        PyErr_SetObject(PyExc_StopIteration, NULL);
        return NULL;
    } else {
        if (time) {
            *time = (*iter)->first;
        }
        value = (*iter)->second;
        Py_INCREF(value);
        (*iter)++;
        return value;
    }
}

/*
  Peek at the top of the queue.
  The timestamp of the first element is stored in time (if not NULL).  The value is returned.
  Returns NULL if the queue is empty with IndexError set.
*/
PyObject *
event_queue_top(event_queue * q, uint64_t * time)
{
    PyObject * value;

    if (q->size()) {
        event_queue_iter iter = q->begin();
        if (time) {
            *time = iter->first;
        }
        value = iter->second;
        Py_INCREF(value);
        return value;
    } else {
        PyErr_SetString(PyExc_IndexError, "top of empty queue");    
        return NULL;
    }
}

/*
  Pop the first element off the queue.
  The timestamp of the first element is stored in time (if not NULL).  The value is returned.
  Returns NULL if the queue is empty with IndexError set.
*/
PyObject *
event_queue_pop(event_queue * q, uint64_t * time)
{
    PyObject * value;
    
    if (q->size()) {
        event_queue_iter iter = q->begin();
        if (time) {
            *time = iter->first;
        }
        value = iter->second;
        q->erase (iter);
        return value;
    } else {
        PyErr_SetString(PyExc_IndexError, "pop from empty queue");
        return NULL;
    }
}

/*
  Insert a new entry into the queue.
  Returns 0 on succes, -1 on failure.
  (Currently never fails.)
*/
int
event_queue_insert(event_queue * q, uint64_t time, PyObject * value)
{
    q->insert (std::pair <uint64_t, PyObject *> (time, value));
    Py_INCREF(value);
    return 0;
}

/*
  Delete an entry from the queue.
  Returns 0 on success, -1 on failure with IndexError set.
*/
int
event_queue_delete(event_queue * q, uint64_t time, PyObject * value)
{
    event_queue_iter iter = q->find(time);
    // Iterate since we support duplicate keys.
    while (iter != q->end()) {
        if (iter->first != time) {
            break;
        }
        if (iter->second == value) {
            Py_DECREF(iter->second);
            q->erase(iter);
            return 0;
        } else {
            iter++;
        }
    }
    PyErr_SetString(PyExc_IndexError, "event not found");
    return -1;
}

} /* extern "C" */
