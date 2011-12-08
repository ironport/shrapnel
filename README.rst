This Python library was evolved at IronPort Systems and has been provided
as open source by Cisco Systems under an MIT license.

Purpose
=======
Shrapnel is a high-performance threading/coroutine library built
around FreeBSD's kqueue() system call.  It's designed for
single-process servers that can handle 10,000+ simultaneous network
connections.

Short History Of Python Coroutine Implementations
=================================================

1) eGroups had a coro implementation based on libcoro, which used
multiple separate small stacks, like many user-threads libraries.
It was somewhat unstable, Python 1.X didn't interact with it well.

2) IronPort had a coro implementation based on Stackless Python (the
version based on Python-2.0 that did only 'soft' switching).  This
version used continuation-passing in C.  Complex, but robust.  Two
main drawbacks: we were stuck with Python 2.0, and couldn't move
things into C easily.

3) IronPort rewrote a 'minimalist' version of Stackless (which we call
'minstack') to support our coroutine system with Python 2.3.
Successful, but with many limitations on when you could safely do a
coroutine switch.  Still difficult to write C extensions for.

4) Shrapnel: A new coroutine scheduler, using the stack-copying
technique.  Written completely in Pyrex.  Should remove all
restrictions on coroutine switching, and easily allow for complex
extensions written in C or Pyrex.

  Calling Shrapnel a 'coroutine' package is somewhat misleading.  Shrapnel
  does not provide a 'coroutine' feature.  Rather, it *uses* coroutines
  to implement a cooperative threading system.  You can use it to solve
  similar problems, but at a higher level; e.g. use a fifo to pass values
  from one thread to another.  The package has historically been called
  'coro' at IronPort, and you will see the terms 'coro' and 'thread' used
  interchangeably in the documentation and source.

Design
======
Shrapnel's overall design is very similar to the previous coro
systems.  There is a 'main' coroutine, which acts as the scheduler,
and uses the normal/default stack.  All other coroutines live on a
separately allocated stack.  When a coroutine is swapped out, its
stack contents are evacuated to the heap.  When it's switched back in,
its stack is copied back into place on the 'coro' stack.  This is
somewhat easier than trying to swap everything on and off of a single
stack, and allows the scheduler to run in main and never be
evacuated.  [We may eventually generalize this and use several coro
stacks rather than just one].

 The original version of coro used the unix ucontext API, which on
 FreeBSD 4.X was implemented using very similar assembly.  However,
 FreeBSD 5.X+ moved the ucontext API into the kernel, making it much
 more expensive.  Currently, the 'swap' implementation is about 15
 lines of x86 (or x86_64) assembly.  It saves and restores the stack,
 frame, and insn pointers in/out of the coro structure.

Scheduler
=========
Shrapnel uses a very simple round-robin scheduler.  All ready coros
(in the <staging> list) are run.  When a running coro needs to
schedule itself (or any other coro), it appends the coro to the
<pending> list.  When everything in <staging> has been run, the two
are swapped.  When both lists are exhausted, we call kevent() to see
if any I/O or signal events have fired (these will schedule coros by
adding them to the <pending> list).  Before entering the main run loop
we schedule any time-based events that have expired.

Priority Queue
==============
A priority queue is used to store future events by time.  There are
two kinds of events stored here: timebombs and sleeping coroutines.
At the top of the event loop, events which have expired are popped off
the priority queue and scheduled.  The priority queue is implemented
using a heap.

Timeouts
========
The with_timeout() call places a <timebomb> object onto the priority
queue.  If this object expires *before* the called function has
returned, an Interrupted exception will be raised on that coroutine.
The value of the exception is the timebomb object.  As the stack is
unwound, the Interrupted handler in with_timeout() checks to see if
the expired timebomb is its own, and if so, translates this into a
TimeoutError.  This design allows multiple outstanding timebombs on
the same coroutine.

Sleeping
========
A coroutine goes to sleep by calling sleep_relative() or
sleep_absolute().  This places the coroutine on the priority queue
with the desired trigger time.  Once this time has arrived, the
event loop will schedule it to run again.
