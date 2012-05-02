=============
Shrapnel/Coro
=============

:Date: $Date: 2008/05/06 $
:Author: Sam Rushing

.. contents::
   :depth: 2
   :backlinks: top
.. section-numbering::

Shrapnel/Coro is a cooperative thread facility built on top of Python.

.. note::

   This document was originally written for internal use at
   IronPort.  It refers to several facilities that unfortunately have not
   (yet) been open-sourced, (e.g., the dns resolver and sntp client).
   It also references and describes things that are specific to the
   IronPort mail appliance.  Much of the advice in here is good, though,
   and I hope to revisit it soon.

Threads
=======

The main abstraction is the 'coro', or thread.  A normally-configured
MGA will usually start up with 100+ threads, many of them devoted to
monitoring the system and its configuration.  Others are maintenance
threads which run for a few seconds every 30 minutes or so.  A system
under load can easily have 3000-4000 active threads.

For example, an SNTP (simple network time protocol) client thread will
send a few packets upon startup, until it has synchronized with a
network time server, then it may send a request every 30-60 minutes to
maintain synchronization via the kernel PLL.

Threads are cheap in Shrapnel, especially if they're idle.  The
overhead of a sleeping thread consists of a single entry in a priority
queue, and the memory for the thread object itself.  Don't avoid
dedicating a thread to some task if it's the right abstraction.

kqueue()/kevent()
=================

FreeBSD has a kernel facility for asynchronous events, called
'kqueue'.  It's a generalization of select(), poll(), /dev/poll, and
other event mechanisms.  Shrapnel's main scheduler loop is built
around the kevent() system call.  Whenever the scheduler runs out of
threads that are ready to run, it calls kevent() to wait for an
external event of some kind.

Non-Blocking Operations
=======================

Large-scale concurrency is achieved by avoiding 'blocking' system
calls, or any operation that consumes too much CPU for too long.
Shrapnel scales up by juggling thousands of such operations at the
same time.  Each thread runs for a short 'slice' of time, usually
until it performs an operation that would block, then it yields.  The
general idea is to 'ask' the kernel to start doing something, and
arrange for it to let you know when it's done.

Non-Blocking Sockets
--------------------

For a network server, the most common operation is a socket read() or
write().  A normal call to read() will disappear into the kernel,
locking up the entire process, while waiting for data to be available
for reading on the socket.  But when the socket is in 'non-blocking'
mode, it will return EWOULDBLOCK instead.  Shrapnel catches this
error, and submits a 'kevent' to the kernel.  Then it yield()s the
thread.  When data eventually becomes available, the kevent will
trigger, and shrapnel's scheduler will wake up the thread.

aio(), signals, etc...
----------------------

Any blocking operation can conceivably be converted into a
kevent();yield();...wait...;resume() sequence.  Other examples are
asynchronous disk i/o ('aio'), signals, wait(4).  There are even some
facilities that are new to Unix, like file/directory change
monitoring.

The Scheduler
-------------

At the heart of shrapnel is the 'event loop'.  It acts as the
scheduler for all the threads and events in the system.  It looks
something like this::

    while running:
      schedule_timed_events()
      while len(ready_jobs):
        run_ready_jobs()
      kevent()

The scheduler is very simple - it uses a round-robin algorithm.  There
are no priorities.  [In general, we have avoided adding priorities due
to the complexity and danger of thread starvation].

'Selfishness'
-------------

One subtle issue with regards to starvation needs to be mentioned.

The design of most non-blocking operations on Unix is one of 'attempt,
maybe EWOULDBLOCK'.  That is, a call to send() *may* succeed
immediately.  Only if it cannot do so will it return EWOULDBLOCK.  On
a very fast locally-connected network, it may be possible to call
send() hundreds of times before it will throw EWOULDBLOCK.  Any thread
relying on the 'non-blocking' nature of network communication might
actually run in a tight loop, starving other threads on the system.
To avoid this problem, a simple form of 'selfishness' is associated
with each thread.  A thread's selfishness defaults to a small number
(say, 4 or 5).  It may try and succeed immediately only that many
operations before it is forcibly yielded.  This gives other threads a
chance to run. [see ap/shrapnel/coro/{_coro.pyx,socket.pyx} for the
'try_selfish()' method]

The Priority Queue
------------------

At the top of the event loop you'll see 'schedule_timed_events()'.
The scheduler uses a priority queue to manage timed events.  The
priority queue contains two kinds of objects, threads and timeouts,
sorted by time.  schedule_timed_events() pops off any events that have
'expired' (their trigger times have passed), and schedules either a
thread or an exception (in the case of a timeout).

There are two common ways for a thread to 'yield': either it's waiting
on an external event, or it's just waiting for a certain amount of
time.  The 'sleep' method on a thread simply places the thread into
the priority queue and yields() itself.

Timeouts
--------

The most important use of the priority queue is for timeouts,
however.  This facility is probably unlike anything you've seen in
other thread packages.  It's designed to be very efficient, so don't
hesitate to use it whenever appropriate.  The interface is through the
'with_timeout()' function.

with_timeout()
~~~~~~~~~~~~~~

Let's say you would like to perform a network operation of some kind,
one that is usually pretty fast, but occasionally might take much
longer, or even forever.  For example, a dns request::

   ...
   ip_addrs = resolver.query (hostname, 'A')
   for ip in ip_addrs:
      ...

You can transform this code to use a five-second timeout easily::

  ...
  try:
     ip_addrs = coro.with_timeout (5, resolver.query, hostname, 'A')
     for ip in ip_addrs:
        ...
  except coro.TimeoutError:
     <handle timeout here>

The first argument is the number of seconds to wait.  The second
argument is the original function.  The remaining arguments are the
original arguments to that function.

If the DNS query doesn't finish in 5 seconds, the scheduler will
resume() this thread with the coro.TimeoutError exception.

with_timeout() Style... High and Low-Level Timeouts.
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There are two main styles of 'with_timeout()' usage.

The first is to wrap a simple operation tightly with a timeout, and is
meant to capture simple network problems with single operations - like
sending a query to a server that's down.  A good example of this would
be to have a timeout on getting a DNS reply from a server.

The second style wraps a complex, high-level operation with a single
'umbrella' timeout - this style is used more to limit the total amount
of time that the task will take, regardless of the underlying reason
for the delay (which might be network, disk, or something else like
waiting on a semaphore or other resource).  An example of this would
be to have a timeout on sending an email message.

Using these two styles, you can avoid using with_timeout() in most of
your code - everything in between the low-level operations and the
outermost task.

A good example of the two styles working together can be found in
godspeed/dns.  In dns_cache.py (the low-level protocol
implementation), you'll see the query_by_ip() method uses a timeout
around a single query/response operation to a single server.  This
timeout defaults to about 5 seconds.

In PrioritizedIP.injector_ip_lookup_ex(), the call to resolver.query()
is protected with a high-level timeout around the PTR lookup.  Due to
the nature of DNS, the PTR query could trigger several low-level DNS
lookups, for things like nameserver and address records.  The
high-level query thus uses a 20-second timeout for the outer
operation.


Synchronization Primitives
--------------------------

Also in the 'coro' module you will find a collection of standard
thread-synchronization primitives, including mutexes, semaphores,
condition variables, read/write locks, etc...

If you're used to 'real' threaded programming, you may be tempted to
make heavy use of these to 'protect' your code against other threads.
In most cases you don't need to do this.  Shrapnel is a 'cooperatively
threaded' system, which means that even on a multi-processor system
only one thread will ever be running at a time.  Only in rare cases do
you need to worry about races.

These facilities are mostly for control over resource usage.  For
example, a semaphore can be used to limit the number of outstanding
requests on an RPC link or DNS socket.  A mutex or read/write lock can
be used to limit access to a file or directory.

Exceptions
----------

Correctly handling exceptions is relatively easy, but there are a few
critical rules that need to be followed.

coro.Interrupted
~~~~~~~~~~~~~~~~

This is an exception that is used internally by shrapnel.  It's used
for the correct propagation of timeout errors, but it is also the base
class for any exception that will interrupt a thread
unexpectedly. (e.g., shutting down a thread asynchronously).
Normally, you shouldn't need to pay attention to coro.Interrupted - 
with the following caveat:

Because coro.Interrupted can be raised anywhere within any system, it
is VERY important that you not mask it through the use of an 'except:'
blanket handler.  [this issue is going to be addressed in future
versions of Python via the introduction of a 'non-maskable' base
class].

In general, using 'except:' is bad form - whether in Shrapnel, Python,
or any other language- but on the rare occasion that you need to write
a blanket handler, here's the safe idiom you should use::

   try:
     do_something()
   except coro.Interrupted:
     raise
   except:
     handle_unexpected_exceptions()

The clause with the 'raise' will allow timeouts and other
interruptions to be processed correctly.

coro.TimeoutError
~~~~~~~~~~~~~~~~~

When a timeout expires, an internal 'Interrupted' exception gets
translated into a coro.TimeoutError.  You may have multiple embedded
timeouts and handlers - the system will delivery the correct timeout
to the correct handler.  [see ap/shrapnel/coro/_coro.pyx for details]

coro.ScheduleError
~~~~~~~~~~~~~~~~~~

This exception will be raised whenever an attempt is made to schedule
a thread to run when it has already been scheduled.  The only way that
this will happen normally is when another thread tries to wake or
interrupt a thread unexpectedly - it's usually the symptom of some
kind of race condition.  There are a few simple techniques to avoid it:

#. Use the builtin synchronization primitives.  Rewrite your code to
   use a semaphore or a condition variable.  The builtin primitives
   already deal with these issues effectively.  [see
   godspeed/coroutine/coro_fifo.py for an example]

#. Use a dedicated thread to manage a queue.  By isolating the
   interaction of many threads through a protected data structure,
   complex thread races can be avoided.  [See
   godspeed/rpc/packet_stream.py or godspeed/ldap/ldap_api.py for
   examples]

Time Scale
----------

User Time
~~~~~~~~~
Shrapnel supports two separate concepts of 'time'.  One is the real
time that users see, which is a standard Unix time_t scale, extended
to microsecond accuracy by FreeBSD.  User time is under the control of
the end user, who can change it at will, including things like time
zone and DST.

TSC Time
~~~~~~~~

For this reason 'user time' is not appropriate for internal scheduler
use.  For example, if we need an event to take place once every 5
minutes, it's important that this happen regardless of how user time
has changed around it.  (If the user moves time forward by a year, we
don't want to trigger 170,000 such events).  TSC Time is named after
the internal Time Stamp Counter register which has been a feature of
the x86 processor line since the days of the Pentium.  The TSC is a
simple 64-bit counter that increments once for each tick of the CPU
clock.

The internal time scale never changes - it always represents the
number of clock ticks since the machine was booted.  The user time
scale is 'pinned' to the TSC timescale by a single value, the
'relative tsc time', which tells us 'what time it was' when the TSC
counter was at zero (i.e., when the machine booted).  When the user
changes time via the OS or NTP, all that's really changed is
coro.relative_tsc_time.

[See ap/shrapnel/coro/time.pyx for more details]

RPC
---

Shrapnel's library includes a fast lightweight RPC system, called
'fast_rpc', that's built around Python's 'pickle' marshalling
facility.  If you need to exchange data between two processes, this is
the preferred method.  [see godspeed/rpc/fast_rpc.py]

Many of the difficult problems with RPC (or even protocols in
general), have been solved in this module, including difficult race
conditions, socket issues, etc.  fast_rpc supports multiple
outstanding requests, out-of-order execution, and pipelining.  Many
threads can make simultaneous requests on the same RPC connection.

Underneath the RPC layer is a simpler abstraction, the
'packet_stream'.  It uses dedicated threads for sending and receiving
packets each stamped with a unique id.  It protects from
thread-related races by using a request queue.  If for some reason
fast_rpc doesn't quite meet your needs, consider using packet_stream
before rolling your own.

SSL
---

The interface to OpenSSL is through a Python extension module, called
'sslip' ('SSL IronPort').  It's a minimalist interface - rather than
trying to put all OpenSSL features in the module, we've added things
as needed over the years.  If you need access to a feature that's not
yet exposed, consider adding it to sslip rather than coding it up
separately.  [It's possible that over the next few years sslip will be
rewritten in Pyrex, so keep that in mind.  Currently the source is in
godspeed/python_modules/sslip.c]

'sslip' is exposed in the coro API via 'coro_ssl.py' [currently in
godspeed/coroutine, but may be moved].  OpenSSL supports non-blocking
sockets directly, so the wrapper passes ssl operations through to the
library via the underlying file descriptor.

Precious Resources
==================

Shrapnel programs are long-running, complex systems that may have
thousands of threads.  In such a crowded environment, it's important
that no one thread or task consume precious resources.  Unlike most
Unix software, a wasteful design won't be whitewashed when your
program exits in a fraction of a second.  Think of your thread as a
single passenger on a crowded train in Tokyo.

Over-consuming any of the following resources can eventually bring the
process down.  Unless you want to be the one losing sleep in order to
make the CEO of a major ISP happy after a major disaster, try to be
frugal with them!

Sometimes there's a trade-off between these - for example, you might
be able to use less memory if you use a little more CPU.  If you're
having trouble deciding, feel free to track down a more experienced
engineer and get some help.

Memory
------

We've touched on this issue already.  Know how much memory you're
using.  Don't cache things unnecessarily.  Avoid keeping many separate
copies of identical objects.  [see godlib/shared_objects.py].

Python can make it difficult to know exactly how much memory you're
using.  Use the 'mstats' module to track memory consumption.  It
allows you to sample *exactly* how much memory you're using.

    Python itself has a few builtin object caches that can confuse
    your measurements.  IronPort has added a function to the 'sys'
    module to clear these caches - sys.free_caches().  You may want to
    call it before and after your test code.

Another useful tool is the 'sizeof' module [see
python_modules/sizeof.c], which can give detailed information about
the memory used by a particular object.

File Descriptors
----------------

In Unix, every socket and file-like object is represented by a 'file
descriptor'.  Internally, a file descriptor is simply a small integer.
Descriptors are managed by the OS, which places a cap on the total
number of descriptors at kernel build time, and descriptor tables are
managed as fixed-size arrays. [So it's a hard limit].

Once a process or kernel starts running out of file descriptors,
things will get ugly, *fast*.  Our system is compiled to allow up to
32K descriptors per-process and per-system.  [The two limits are kept
pretty close because an MGA normally has only one process, hermes,
that consumes large numbers of descriptors].

In Python, the 'os' module exposes many of the standard unix system
calls that work with file descriptors.  Using the functions in that
module, it's possible to create, use, and destroy file desciptors of
various kinds.  If you're not careful, you can create a file
descriptor but forget to destroy it (this usually happens because of
an exception of some kind)... in which case the descriptor will 'leak'
- it will consume a precious entry in the table that will not be freed
until close() is called on it.

If you find youself working with low-level file descriptors (in *any*
language), you should consider using a wrapper class (like the one in
hermes/qstore/gcq.py::os_file] to ensure that the descriptor gets
closed.  Another good technique is to use a try/finally clause with
the call to 'close()' in the finally block.  Most of our objects that
wrap file descriptors already use destructors to close their
descriptors, but it's still good practice to use try/finally anyway.

CPU
---

CPU time is always a precious resource, but in this case we're talking
about something a little more subtle.  In a cooperative multi-tasking
environment, it's important that no task monopolize the CPU for too
long, otherwise other tasks will get locked out.  The shrapnel
scheduler monitors how long each thread runs, and will emit a 'latency
warning' if a thread runs for over 1/5 of a second without yielding.

If you're doing something that needs a lot of CPU - usually processing
a large data structure - you can be a 'good neighbor' by yield()ing
every once in a while inside your main loop.  [see
hermes/omh/omh.py::spawn_all_domains() for a good example of this
technique]

Python is not a good language for low-level 'character' processing,
it's too slow.  Examples would be things like MIME and base64
decoding, parsing, etc... .  If your code needs to do this kind of
work, the recommended approach is to write everything in Python, then
identify the 'hot' spots and re-code only those portions in Pyrex, C,
or C++.  This is exactly the approach used by Python itself [see
Python/Modules/binascii.c]

Coro Profiler
-------------

Shrapnel includes a simple yet powerful profiler.  The 'coro profiler'
[see godspeed/coroutine/coro_profile.py] is a Python profiler
implementation that takes samples of system resources using the
'getrusage()' system call.  It also maintains simple call counts.  You
can wrap calls to the profiler around a single function, or (more
commonly) the entire event loop. [see godspeed/hermes/hermes.py for a
sample profiler usage - the profile line is commented out, right next
to the main call to coro.event_loop()]

The profiler outputs its data into a binary file, which is then
post-processed with 'print_profile.py', which generates an HTML
table.  For more information on the fields in the table, try 'man
getrusage'.

The Back Door
=============

The 'back door' is a externally-accessible Python prompt.  Through it,
you can get into a running coro process to examine, change, or debug
any aspect of the system.  It's invaluable in all stages of
development, QA, and even deployment.  Many bugs have been found
quickly and easily by using the back door to do things like dump
caches, examine and dump data structures, etc... - even in the field.

The back door is implemented as a socket server.  For security
reasons, back doors are usually bound to a unix-domain socket, often
kept in '/tmp' with a name like '/tmp/my_application.bd'.  To connect
to it, simply 'telnet' to the full pathname, like this::

  $ telnet /tmp/my_application.bd

  Python 2.4.3-IronPort (#61, Jun 14 2006, 14:59:13)
  [GCC 3.4.2 [FreeBSD] 20040728]
  [...]
  >>>

From this prompt you can interact with Python normally.

It can be convenient to store some utility functions for use via the
back door in a module that is loaded automatically.  See
godspeed/hermes/service.py for such a utility file, which should also
give you an idea of the kinds of things that are possible via this
feature.

