# -*- Mode: Python -*-

# This is a demo of the rpc client class, compatible with the pika/rabbitmq rpc tutorial.
# see http://www.rabbitmq.com/tutorials/tutorial-six-python.html

import coro.amqp as amqp

def t0():
    c = amqp.client (('guest', 'guest'), '127.0.0.1', heartbeat=30)
    c.go()
    ch = c.channel()
    rpc = amqp.rpc.client (ch)
    frame, props, reply = rpc.call ({}, '19', '', 'rpc_queue')
    # shut it down
    rpc.cancel()
    c.close()
    print 'got a reply...', reply
    coro.sleep_relative (5)
    coro.set_exit (1)

if __name__ == '__main__':
    import coro
    coro.spawn (t0)
    coro.event_loop()
