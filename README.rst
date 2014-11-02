This Python library was evolved at IronPort Systems and has been provided
as open source by Cisco Systems under an MIT license.

This Branch
===========

This branch is a quick experiment to see if I can get external worker
pthreads to cooperate with Shrapnel, while still avoiding the cost of
CPython's GIL/ThreadState/etc mechanism. [if you don't start a python
thread it never turns that stuff on].

I think the idea may be sound, and this experiment (see
test/test_pthread.py) seems to work, but there are problems.  I get
crashes, I get hang-on-exit, etc...  Someone who groks pthreads might
be able to help.

Intro
=====

Shrapnel is a library for high-performance concurrency.  It uses
coroutines to implement user threads on top of either kqueue (FreeBSD,
OS X) or /dev/epoll (linux), and is written mostly in Pyrex/Cython,
supporting both 32-bit and 64-bit platforms.  It is the culmination of
about 8 years of work at IronPort Systems, a provider of high-speed
mail appliances.  It was open-sourced by Cisco Systems in late 2011.

Status
======

Apr 18, 2013: I've recently merged in a long chain of branches for several
important features:

 * Support for pure-cython servers (branch 'pxdfix')
 * Full DNS resolver implementation (branch 'dns-cache')
 * Updated postgres support (branch 'postgres')
 * Included OpenSSL support


Features
========

 * Lightweight threads, event-driven scheduler.
 * Underneath: non-blocking operations on descriptors, like sockets and pipes.
 * On top, synchronous API for straight-line, simple code.
 * Highly scalable - tens or hundreds of thousands of connections/threads.
 * Thread synchronization primitives, like mutexes, semaphores, etc...
 * with_timeout(): wrap any funcall with a timeout.
 * Wait on kqueue events like file/directory changes, signals, processes, etc... [kqueue only]
 * DNS resolver and cache
 * HTTP server and client (plus WebSocket, RFC6455 & hixie-76)
 * Support for TLS via tlslite and openssl (plus NPN for both)
 * other protocols/codecs: ldap, asn1, ftp, mysql, postgres, AMQP_.
 * `MIT License`_.
 
Advantages
==========

Compared to other concurrency packages available for Python,
Shrapnel gives you:

 * Speed and Efficiency: the entire scheduler, poller, socket layer,
   synchronization objects, etc... are written in Cython, with an
   emphasis on performance and low memory usage.
 * Stock Python: Shrapnel works with out-of-the-box CPython [2.X].  No
   special variants of Python are needed, it will even work with your
   OS's OEM python installation. So you can use all the external
   libraries/modules you've come to rely on.
 * No Callbacks: no need to cuisinart your application into a thousand
   callbacks.  No need to decompose every action into a state
   machine.  Write simple, performant code now without having to send
   your programmers to class.
 * Drop to Cython for speed: all the capabilities of the system are
   available from Cython, so you can e.g. write a server entirely in
   Cython for speed.  You can interface with external libraries, and
   do thread switches from Cython or C.  It's even possible to have
   external C code call back into shrapnel.  This makes it easy to
   prototype your application in Python, and then push only the hot
   spots into Cython.
 * Timeouts: Shrapnel provides a general timeout mechanism that can be
   used to wrap any function call with a timeout.
 * Profiler: Thread-aware profiler generates HTML reports.


Tutorial
========

See http://ironport.github.com/shrapnel/tutorial.html

API Documentation
=================

See http://ironport.github.com/shrapnel/

.. _MIT License: http://www.opensource.org/licenses/mit-license.html
.. _AMQP: https://github.com/samrushing/amqp-shrapnel
