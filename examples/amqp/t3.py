# -*- Mode: Python -*-
# companion to t0.py that uses amqp-shrapnel
# ... and uses rabbitmq's 'confirm' extension

import coro.amqp as amqp


def t3():
    global c
    c = amqp.client (('guest', 'guest'), '127.0.0.1')
    print 'connecting...'
    c.go() # i.e., connect...
    print 'channel...'
    ch = c.channel()
    print 'confirm_select...'
    ch.confirm_select()
    print 'entering send loop'
    for i in range (10):
        props = {'content-type':'raw goodness', 'message-id' : 'msg_%d' % (i,)}
        ch.basic_publish ('howdy there!', exchange='ething', routing_key='notification', properties=props)
        print 'sent/confirmed'
        coro.sleep_relative (1)
    coro.set_exit()

import coro
coro.spawn (t3)
coro.event_loop()
