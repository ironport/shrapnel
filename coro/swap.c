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

// -*- Mode: C -*-
// $Header: //prod/main/ap/shrapnel/coro/swap.c#5 $

#include "Python.h"
#include "frameobject.h"

// This file contains functions that cannot (for one reason or another) be
// placed in coro.pyx.

// __swap() manages the switch from one coroutine to another.
// It's used for swaps both to and from <main>.  It preserves
// the stack, frame, and insn pointers of the previously-running
// coro, and installs the new values from coro being swapped in.
// The contents of the stack have already been put in place by
// the scheduler._restore() function.

/*
 *
 * cdef struct machine_state:
 *     00 void * stack_pointer
 *     04 void * frame_pointer
 *     08 void * insn_pointer
 *     12 void * ebx
 *     16 void * esi
 *     20 void * edi
 *
 *
 */

int __swap (void * to_state, void * from_state);

#ifdef __i386__
__asm__ (
".globl __swap                                           \n"
".globl ___swap                                          \n"
"__swap:                                                 \n"
"___swap:                                                \n"
"	movl 8(%esp), %edx      # fs->%edx               \n"
"	movl %esp, 0(%edx)      # save stack_pointer     \n"
"	movl %ebp, 4(%edx)      # save frame_pointer     \n"
"	movl (%esp), %eax       # save insn_pointer      \n"
"	movl %eax, 8(%edx)                               \n"
"       movl %ebx, 12(%edx)     # save ebx,esi,edi       \n"
"       movl %esi, 16(%edx)                              \n"
"       movl %edi, 20(%edx)                              \n"
"	movl 4(%esp), %edx      # ts->%edx               \n"
"       movl 20(%edx), %edi     # restore ebx,esi,edi    \n"
"       movl 16(%edx), %esi                              \n"
"       movl 12(%edx), %ebx                              \n"
"	movl 4(%edx), %ebp      # restore frame_pointer  \n"
"	movl 0(%edx), %esp      # restore stack_pointer  \n"
"       movl 8(%edx), %eax      # restore insn_pointer   \n"
"       movl %eax, (%esp)                                \n"
"	ret                                              \n"
);

int SHRAP_STACK_PAD = 3 * sizeof (void *);

#elif defined (__x86_64__)

/*
 *
 * cdef struct machine_state:
 *     00 void * stack_pointer
 *     08 void * frame_pointer
 *     16 void * insn_pointer
 *     24 void * ebx
 *     32 void * r12
 *     40 void * r13
 *     48 void * r14
 *     56 void * r15
 *
 */

/*
 * x86_64 calling convention: args are in rdi,rsi,rdx,rcx,r8,r9
 */

int __swap (void * to_state, void * from_state);

__asm__ (
".globl __swap                                           \n"
".globl ___swap                                          \n"
"__swap:                                                 \n"
"___swap:                                                \n"
"	movq %rsp, 0(%rsi)      # save stack_pointer     \n"
"	movq %rbp, 8(%rsi)      # save frame_pointer     \n"
"	movq (%rsp), %rax       # save insn_pointer      \n"
"	movq %rax, 16(%rsi)                              \n"
"	movq %rbx, 24(%rsi)     # save rbx,r12-r15       \n"
"	movq %r12, 32(%rsi)                              \n"
"	movq %r13, 40(%rsi)                              \n"
"	movq %r14, 48(%rsi)                              \n"
"	movq %r15, 56(%rsi)                              \n"
"	movq 56(%rdi), %r15                              \n"
"	movq 48(%rdi), %r14                              \n"
"	movq 40(%rdi), %r13     # restore rbx,r12-r15    \n"
"	movq 32(%rdi), %r12                              \n"
"	movq 24(%rdi), %rbx                              \n"
"	movq 8(%rdi), %rbp      # restore frame_pointer  \n"
"	movq 0(%rdi), %rsp      # restore stack_pointer  \n"
"	movq 16(%rdi), %rax     # restore insn_pointer   \n"
"	movq %rax, (%rsp)                                \n"
"	ret                                              \n"
);

int SHRAP_STACK_PAD = 1 * sizeof (void *);

#endif

PyObject *
void_as_object (void * p)
{
  PyObject * _p = (PyObject *) p;
  if (!p) {
    _p = Py_None;
  }
  Py_INCREF (_p);
  return _p;
}

// similar to static function in Python/Objects/frameobject.c
int
frame_getlineno (PyFrameObject * f)
{
  int lineno;
  if (f->f_trace) {
    lineno = f->f_lineno;
  } else {
    lineno = PyCode_Addr2Line (f->f_code, f->f_lasti);
  }
  return lineno;
}

int
coro_breakpoint (void)
{
  return 0;
}

extern void _wrap1 (void * co);
extern void __yield (void);

#ifdef __x86_64__
void
_wrap0 (void)
{
  void * co;
  // x86_64 passes args in registers.  but coro.__create() puts
  // the coroutine on the stack.  fetch it from there.
  __asm__ ("movq 16(%%rsp), %[co]" : [co] "=r" (co));
  _wrap1 (co);
  __yield();
}

#else
void
_wrap0 (void * co)
{
  _wrap1 (co);
  __yield();
}
#endif
