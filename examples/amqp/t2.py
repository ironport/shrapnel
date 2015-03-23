# -*- Mode: Python -*-
# companion to t0.py that uses amqp-shrapnel

import coro.amqp as amqp

# set this to see AMQP protocol-level info.
debug = False

def t2():
    global c
    c = amqp.client (('guest', 'guest'), '127.0.0.1')
    c.debug = debug
    c.go() # i.e., connect...
    ch = c.channel()
    for i in range (10):
        ch.basic_publish ('howdy %d' % (i,), exchange='ething', routing_key='notification')
        coro.sleep_relative (5)
    coro.set_exit()

import coro
coro.spawn (t2)
coro.event_loop()
