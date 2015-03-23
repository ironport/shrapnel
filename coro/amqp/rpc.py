# -*- Mode: Python -*-

"""Provides an easy-to-use implementation of the AMQP 'RPC pattern' that should work for most situations.
"""

import coro
import uuid
import sys

# an attempt to implement the confusing semantics of an RPC system via AMQP
# hopefully this covers enough use cases to be generally useful.

W = sys.stderr.write

def dump_ob (ob):
    W ('%s {\n' % (ob._name,))
    for name in ob.__slots__:
        W ('  %s = %r\n' % (name, getattr (ob, name)))
    W ('}\n')

class server:

    def __init__ (self, channel, queue, exchange):
        self.channel = channel
        self.queue = queue
        self.exchange = exchange
        self.consumer = self.channel.basic_consume (queue=self.queue)
        coro.spawn (self.request_thread)

    def cancel (self):
        self.consumer.cancel()

    def request_thread (self):
        try:
            while 1:
                # W ('request thread waiting...\n')
                frame, props0, request = self.consumer.pop()
                # W ('request thread: got one: %r\n' % (props0['correlation-id'],))
                # dump_ob (frame)
                props1, reply = self.handle_request (props0, request)
                props1['correlation-id'] = props0['correlation-id']
                self.channel.basic_publish (
                    reply,
                    self.exchange,
                    routing_key=props0['reply-to'],
                    properties=props1
                )
                # W ('after basic_publish\n')
        except:
            W ('exiting rpc request thread\n')

class RPC_Client_Error (Exception):
    pass

class client:

    """Create a new RPC client for *channel*.

    *queue*: optional argument.  If not supplied, an
      anonymous/exclusive queue is created automatically.

    *uuid_fun*: a function for generating UUID's for use as correlation-ids.
      If not supplied, defaults to uuid.uuid1.
    """

    def __init__ (self, channel, queue='', uuid_fun=uuid.uuid1):
        self.channel = channel
        if queue == '':
            self.queue = channel.queue_declare (exclusive=True).queue
        else:
            self.queue = queue
        self.uuid_fun = uuid_fun
        self.consumer = self.channel.basic_consume (queue=self.queue)
        self.pending = {}
        coro.spawn (self.reply_thread)

    def cancel (self):
        self.consumer.cancel()

    def call (self, properties, payload, exchange, routing_key):
        """Make an RPC call.

        *properties*: a properties dictionary (e.g. {'content-type':'application/json', ...})

        *payload*: the data/argument to the rpc function.

        *exchange*, *routing_key*: as with basic_publish.
        """
        correlation_id = str (self.uuid_fun())
        properties['correlation-id'] = correlation_id
        properties['reply-to'] = self.queue
        # W ('sending call to rpc server (uuid=%r)\n' % (correlation_id,))
        self.channel.basic_publish (payload, exchange, routing_key, properties=properties)
        self.pending[correlation_id] = coro.current()
        # W ('waiting for reply\n')
        return coro._yield()

    def reply_thread (self):
        try:
            while 1:
                # W ('reply thread: waiting for any replies\n')
                frame, props, data = self.consumer.pop()
                cid = props['correlation-id']
                # W ('reply thread: got one: %r\n' % (cid,))
                probe = self.pending.get (cid, None)
                if probe is None:
                    W ('dropping unknown correlation-id: %r' % (cid,))
                else:
                    del self.pending[cid]
                    coro.schedule (probe, (frame, props, data))
        except:
            W ('exiting rpc reply thread\n')
            for k, v in self.pending.iteritems():
                v.raise_exception (RPC_Client_Error)
