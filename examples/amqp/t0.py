# -*- Mode: Python -*-

import coro
import coro.amqp as amqp

from coro.log import Facility

LOG = Facility ('consumer')

# how to run this test:

# 1) run this script.  it will print something like this:
#   $ /usr/local/bin/python test/t0.py
#
# 2) Now, in another window run either t1.py (uses amqplib) or t2.py (uses this library):
#
#   $ python test/t2.py
#   published!
#   -1: Tue Jan 10 12:49:27 2012 Exiting...
#
#   In the first window you should see the message show up.

# set this to see AMQP protocol-level info.
debug = False

def t0():
    c = amqp.client (('guest', 'guest'), '127.0.0.1', heartbeat=30)
    c.debug = debug
    c.go()
    ch = c.channel()
    ch.exchange_declare (exchange='ething')
    ch.queue_declare (queue='qthing', passive=False, durable=False)
    ch.queue_bind (exchange='ething', queue='qthing', routing_key='notification')
    fifo = ch.basic_consume (queue='qthing')
    while 1:
        LOG ('waiting')
        msg = fifo.pop()
        LOG ('msg', repr(msg))

if __name__ == '__main__':
    coro.spawn (t0)
    coro.event_loop()
