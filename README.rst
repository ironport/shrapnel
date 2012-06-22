This Python library was evolved at IronPort Systems and has been provided
as open source by Cisco Systems under an MIT license.

Intro
=====

Shrapnel is a library for high-performance concurrency.  It uses
coroutines to implement user threads on top of either kqueue (FreeBSD,
OS X) or /dev/epoll (linux), and is written mostly in Pyrex/Cython,
supporting both 32-bit and 64-bit platforms.  It is the culmination of
about 8 years of work at IronPort Systems, a provider of high-speed
mail appliances.  It was open-sourced by Cisco Systems in late 2011.

Features
========

 * Lightweight threads, event-driven scheduler.
 * Underneath: non-blocking operations on descriptors, like sockets and pipes.
 * On top, synchronous API for straight-line, simple code.
 * Highly scalable - tens or hundreds of thousands of connections/threads.
 * Thread synchronization primitives, like mutexes, semaphores, etc...
 * Wait on kqueue events like file/directory changes, signals, processes, etc... [kqueue only]
 * DNS stub resolver (full-fledged resolver may be forthcoming)
 * HTTP server and client
 * Support for TLS via tlslite (openssl interface may be forthcoming)
 * other protocols/codecs: ldap, asn1, ftp, mysql, postgres, AMQP_.
 * `MIT License`_.
 
Tutorial
========

See http://ironport.github.com/shrapnel/tutorial.html

API Documentation
=================

See http://ironport.github.com/shrapnel/

.. _MIT License: http://www.opensource.org/licenses/mit-license.html
.. _AMQP: https://github.com/samrushing/amqp-shrapnel
