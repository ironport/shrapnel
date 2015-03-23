
AMQP/Shrapnel
======

This is an implementation of the [AMQP] protocol for [Shrapnel].

Status
------

Implements version 0.9.1 of the protocol.  The basics are there:
channels, queues, exchanges, basic_publish, basic_consume.  Tested
against [RabbitMQ].

Recently added: heartbeats, a `consumer` class that simplifies the
receiving of messages, and classes for rpc servers and clients.

Documentation
-------------

Preliminary documentation is available at http://ironport.github.com/shrapnel/

Also, see the files in the test directory for example usage.

Implementation
--------------
Most of the code is auto-generated from the [RabbitMQ] machine-readable
protocol description file.  See coro/amqp/codegen.py.

Plans
-----

I plan to rewrite the wire codec in [Cython], and then have the code
generator also generate Cython.  Combined with the high performance of
shrapnel itself, this should fairly scream.

[Cython]: http://cython.org/
[Shrapnel]: http://github.com/ironport/shrapnel/
[AMQP]: http://en.wikipedia.org/wiki/Advanced_Message_Queuing_Protocol
[RabbitMQ]: http://www.rabbitmq.com/
