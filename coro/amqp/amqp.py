# -*- Mode: Python -*-

"""
Implements the AMQP protocol for Shrapnel.
"""

import struct
import coro
import spec
import rpc
import sys

from coro.log import Facility

LOG = Facility ('amqp')

from pprint import pprint as pp
is_a = isinstance

W = sys.stderr.write

class AMQPError (Exception):
    pass
class ProtocolError (AMQPError):
    pass
class UnexpectedClose (AMQPError):
    pass
class AuthenticationError (AMQPError):
    pass

def dump_ob (ob):
    W ('%s {\n' % (ob._name,))
    for name in ob.__slots__:
        W ('  %s = %r\n' % (name, getattr (ob, name)))
    W ('}\n')

# sentinel for consumer fifos
connection_closed = 'connection closed'

class client:

    """*auth*: is a tuple of (username, password) for the 'PLAIN' authentication mechanism.

       *host*: string - IP address of the server.

       *port*: int -  TCP port number

       *virtual_host*: string - specifies which 'virtual host' to connect to.

       *heartbeat*: int - whether to request heartbeat mode from the
        server.  A value of 0 indicates no heartbeat wanted.  Any
        other value specifies the number of seconds of idle time from
        either side before a heartbeat frame is sent.
    """

    version = [0, 0, 9, 1]
    buffer_size = 4000
    properties = {
        'product': 'AMQP/shrapnel',
        'version': '0.8',
        'information': 'https://github.com/ironport/shrapnel',
        'capabilities': {
            'publisher_confirms': True,
        }
    }

    # whether to log protocol-level info.
    debug = False

    def __init__ (self, auth, host, port=5672, virtual_host='/', heartbeat=0):
        self.port = port
        self.host = host
        self.auth = auth
        self.virtual_host = virtual_host
        self.heartbeat = heartbeat
        self.frame_state = 0
        self.frames = coro.fifo()
        # collect body parts here.  heh.
        self.body = []
        self.next_content_consumer = None
        self.next_properties = None
        self.consumers = {}
        self.closed_cv = coro.condition_variable()
        self.last_send = coro.now
        self.channels = {}

    # state diagram for connection objects:
    #
    # connection          = open-connection *use-connection close-connection
    # open-connection     = C:protocol-header
    #                       S:START C:START-OK
    #                       *challenge
    #                       S:TUNE C:TUNE-OK
    #                       C:OPEN S:OPEN-OK
    # challenge           = S:SECURE C:SECURE-OK
    # use-connection      = *channel
    # close-connection    = C:CLOSE S:CLOSE-OK
    #                     / S:CLOSE C:CLOSE-OK

    def go (self):
        "Connect to the server.  Spawns a new thread to monitor the connection."
        self.s = coro.tcp_sock()
        self.s.connect ((self.host, self.port))
        self.s.send ('AMQP' + struct.pack ('>BBBB', *self.version))
        self.buffer = self.s.recv (self.buffer_size)
        if self.buffer.startswith ('AMQP'):
            # server rejection
            raise AMQPError (
                "version mismatch: server wants %r" % (
                    struct.unpack ('>4B', self.buffer[4:8])
                )
            )
        else:
            coro.spawn (self.recv_loop)
            # pull the first frame off (should be connection.start)
            ftype, channel, frame = self.expect_frame (spec.FRAME_METHOD, 'connection.start')
            # W ('connection start\n')
            # dump_ob (frame)
            mechanisms = frame.mechanisms.split()
            self.server_properties = frame.server_properties
            if 'PLAIN' in mechanisms:
                response = '\x00%s\x00%s' % self.auth
            else:
                raise AuthenticationError ("no shared auth mechanism: %r" % (mechanisms,))
            reply = spec.connection.start_ok (
                # XXX put real stuff in here...
                client_properties=self.properties,
                response=response
            )
            self.send_frame (spec.FRAME_METHOD, 0, reply)
            # XXX
            # XXX according to the 'grammar' from the spec, we might get a 'challenge' frame here.
            # XXX
            ftype, channel, frame = self.expect_frame (spec.FRAME_METHOD, 'connection.tune')
            self.tune = frame
            # I'm AMQP, and I approve this tune value.
            self.send_frame (
                spec.FRAME_METHOD, 0,
                spec.connection.tune_ok (frame.channel_max, frame.frame_max, self.heartbeat)
            )
            # ok, ready to 'open' the connection.
            self.send_frame (
                spec.FRAME_METHOD, 0,
                spec.connection.open (self.virtual_host)
            )
            ftype, channel, frame = self.expect_frame (spec.FRAME_METHOD, 'connection.open_ok')

    def expect_frame (self, ftype, *names):
        "read/expect a frame from the list *names*"
        ftype, channel, frame = self.frames.pop()
        if frame._name not in names:
            raise ProtocolError ("expected %r frame, got %r" % (names, frame._name))
        else:
            return ftype, channel, frame

    def secs_since_send (self):
        return (coro.now - self.last_send) / coro.ticks_per_sec

    def recv_loop (self):
        try:
            try:
                while 1:
                    while len (self.buffer):
                        self.unpack_frame()
                    if self.heartbeat:
                        block = coro.with_timeout (self.heartbeat * 2, self.s.recv, self.buffer_size)
                    else:
                        block = self.s.recv (self.buffer_size)
                    if not block:
                        break
                    else:
                        self.buffer += block
                    if self.heartbeat and self.secs_since_send() > self.heartbeat:
                        self.send_frame (spec.FRAME_HEARTBEAT, 0, '')
            except coro.TimeoutError:
                # two heartbeat periods have expired with no data, so we let the
                #   connection close.  XXX Should we bother trying to call connection.close()?
                pass
        finally:
            self.notify_channels_of_close()
            self.closed_cv.wake_all()
            self.s.close()

    def unpack_frame (self):
        # unpack the frame sitting in self.buffer
        ftype, chan, size = struct.unpack ('>BHL', self.buffer[:7])
        if self.debug:
            LOG ('frame', ftype, chan, size)
        # W ('<<< frame: ftype=%r channel=%r size=%d\n' % (ftype, chan, size))
        if size + 8 <= len(self.buffer) and self.buffer[7+size] == '\xce':
            # we have the whole frame
            # <head> <payload> <end> ...
            # [++++++++++++++++++++++++]
            payload, self.buffer = self.buffer[7:7+size], self.buffer[8+size:]
        else:
            # we need to fetch more data
            # <head> <payload> <end>
            # [++++++++++][--------]
            payload = self.buffer[7:] + self.s.recv_exact (size - (len(self.buffer) - 7))
            # fetch the frame end separately
            if self.s.recv_exact (1) != '\xce':
                raise ProtocolError ("missing frame end")
            else:
                self.buffer = ''
        # -------------------------------------------
        # we have the payload, what do we do with it?
        # -------------------------------------------
        # W ('<<< frame: ftype=%r channel=%r size=%d payload=%r\n' % (ftype, chan, size, payload))
        if ftype == spec.FRAME_METHOD:
            cm_id = struct.unpack ('>hh', payload[:4])
            ob = spec.method_map[cm_id]()
            ob.unpack (payload, 4)
            if self.debug:
                LOG ('<<<', 'method', repr(ob))
            # W ('<<< ')
            # dump_ob (ob)
            # catch asynchronous stuff here and ship it out...
            if is_a (ob, spec.basic.deliver):
                ch = self.channels.get (chan, None)
                if ch is None:
                    W ('warning, dropping delivery for unknown channel #%d consumer_tag=%r\n' % (chan, ob.consumer_tag))
                else:
                    self.next_content_consumer = (ob, ch)
            else:
                self.frames.push ((ftype, chan, ob))
        elif ftype == spec.FRAME_HEADER:
            cid, weight, size, flags = struct.unpack ('>hhqH', payload[:14])
            # W ('<<< HEADER: cid=%d weight=%d size=%d flags=%x payload=%r\n' % (cid, weight, size, flags, payload))
            # W ('<<< self.buffer=%r\n' % (self.buffer,))
            if self.debug:
                LOG ('<<<', 'header', repr(payload))
            if flags:
                self.next_properties = unpack_properties (flags, payload[14:])
            else:
                self.next_properties = {}
            self.remain = size
        elif ftype == spec.FRAME_BODY:
            # W ('<<< FRAME_BODY, len(payload)=%d\n' % (len(payload),))
            self.remain -= len (payload)
            self.body.append (payload)
            if self.debug:
                LOG ('<<<', 'body', repr(payload))
            if self.remain == 0:
                if self.next_content_consumer is not None:
                    ob, ch = self.next_content_consumer
                    ch.accept_delivery (ob, self.next_properties, self.body)
                    self.next_content_consumer = None
                    self.next_properties = None
                else:
                    W ('dropped data: %r\n' % (self.body,))
                self.body = []
        elif ftype == spec.FRAME_HEARTBEAT:
            # W ('<<< FRAME_HEARTBEAT\n')
            if self.debug:
                LOG ('<<<', 'heartbeat')
            pass
        else:
            if self.debug:
                LOG ('<<<', 'unexpected', ftype)
            self.close (505, "unexpected frame type: %r" % (ftype,))
            raise ProtocolError ("unhandled frame type: %r" % (ftype,))

    def send_frame (self, ftype, channel, ob):
        "send a frame of type *ftype* on this channel.  *ob* is a frame object built by the <spec> module"
        f = []
        if ftype == spec.FRAME_METHOD:
            payload = struct.pack ('>hh', *ob.id) + ob.pack()
        elif ftype in (spec.FRAME_HEADER, spec.FRAME_BODY, spec.FRAME_HEARTBEAT):
            payload = ob
        else:
            raise ProtocolError ("unhandled frame type: %r" % (ftype,))
        frame = struct.pack ('>BHL', ftype, channel, len (payload)) + payload + chr(spec.FRAME_END)
        self.s.send (frame)
        self.last_send = coro.now
        if self.debug:
            LOG ('>>>', repr(ob))
        # W ('>>> send_frame: %r %d\n' % (frame, r))

    def close (self, reply_code=200, reply_text='normal shutdown', class_id=0, method_id=0):
        "http://www.rabbitmq.com/amqp-0-9-1-reference.html#connection.close"
        # close any open channels first.
        self.notify_channels_of_close()
        self.send_frame (
            spec.FRAME_METHOD, 0,
            spec.connection.close (reply_code, reply_text, class_id, method_id)
        )
        ftype, channel, frame = self.expect_frame (spec.FRAME_METHOD, 'connection.close_ok')

    def channel (self, out_of_band=''):
        """Create a new channel on this connection.

        http://www.rabbitmq.com/amqp-0-9-1-reference.html#connection.channel
        """
        chan = channel (self)
        self.send_frame (spec.FRAME_METHOD, chan.num, spec.channel.open (out_of_band))
        ftype, chan_num, frame = self.expect_frame (spec.FRAME_METHOD, 'channel.open_ok')
        assert chan_num == chan.num
        self.channels[chan.num] = chan
        return chan

    def forget_channel (self, num):
        del self.channels[num]

    def notify_channels_of_close (self):
        items = self.channels.items()
        for num, ch in items:
            ch.notify_of_close()

class channel:

    """*conn*: the connection object this channel resides on.

    The channel object presents the main interface to the user, exposing most of the 'methods'
      of AMQP, including the 'basic' and 'channel' methods.

    A connection may have multiple channels.

    """

    # state diagram for channel objects:
    #
    # channel             = open-channel *use-channel close-channel
    # open-channel        = C:OPEN S:OPEN-OK
    # use-channel         = C:FLOW S:FLOW-OK
    #                     / S:FLOW C:FLOW-OK
    #                     / functional-class
    # close-channel       = C:CLOSE S:CLOSE-OK
    #                     / S:CLOSE C:CLOSE-OK

    counter = 1
    ack_discards = True

    def __init__ (self, conn):
        self.conn = conn
        self.num = channel.counter
        self.confirm_mode = False
        self.consumers = {}
        channel.counter += 1

    def send_frame (self, ftype, frame):
        self.conn.send_frame (ftype, self.num, frame)

    # Q:, if a method is synchronous, does that mean it is sync w.r.t. this channel only?
    # in other words, might a frame for another channel come in before we get our reply?

    # leaving off all the 'ticket' args since they appear unused/undocumented...

    def exchange_declare (self, exchange=None, type='direct', passive=False,
                          durable=False, auto_delete=False, internal=False, nowait=False, arguments={}):
        "http://www.rabbitmq.com/amqp-0-9-1-reference.html#exchange.declare"
        frame = spec.exchange.declare (0, exchange, type, passive, durable, auto_delete, internal, nowait, arguments)
        self.send_frame (spec.FRAME_METHOD, frame)
        if not nowait:
            ftype, channel, frame = self.conn.expect_frame (spec.FRAME_METHOD, 'exchange.declare_ok')
            assert channel == self.num
            return frame

    def queue_declare (self, queue='', passive=False, durable=False,
                       exclusive=False, auto_delete=False, nowait=False, arguments={}):
        "http://www.rabbitmq.com/amqp-0-9-1-reference.html#queue.declare"
        frame = spec.queue.declare (0, queue, passive, durable, exclusive, auto_delete, nowait, arguments)
        self.send_frame (spec.FRAME_METHOD, frame)
        if not nowait:
            ftype, channel, frame = self.conn.expect_frame (spec.FRAME_METHOD, 'queue.declare_ok')
            assert channel == self.num
            return frame

    def queue_bind (self, queue='', exchange=None, routing_key='', nowait=False, arguments={}):
        "http://www.rabbitmq.com/amqp-0-9-1-reference.html#queue.bind"
        frame = spec.queue.bind (0, queue, exchange, routing_key, nowait, arguments)
        self.send_frame (spec.FRAME_METHOD, frame)
        if not nowait:
            ftype, channel, frame = self.conn.expect_frame (spec.FRAME_METHOD, 'queue.bind_ok')
            assert channel == self.num
            return frame

    def basic_consume (self, queue='', consumer_tag='', no_local=False,
                       no_ack=False, exclusive=False, arguments={}):
        """Start consuming messages from *queue*.

        Returns a new :class:consumer object which spawns a new thread to monitor incoming messages.

        http://www.rabbitmq.com/amqp-0-9-1-reference.html#basic.consume
        """
        # we do not allow 'nowait' since that precludes us from establishing a consumer fifo.
        frame = spec.basic.consume (0, queue, consumer_tag, no_local, no_ack, exclusive, False, arguments)
        self.send_frame (spec.FRAME_METHOD, frame)
        ftype, channel, frame = self.conn.expect_frame (spec.FRAME_METHOD, 'basic.consume_ok')
        assert channel == self.num
        con0 = consumer (self, frame.consumer_tag)
        self.add_consumer (con0)
        return con0

    def basic_cancel (self, consumer_tag='', nowait=False):
        "http://www.rabbitmq.com/amqp-0-9-1-reference.html#basic.cancel"
        frame = spec.basic.cancel (consumer_tag, nowait)
        self.send_frame (spec.FRAME_METHOD, frame)
        if not nowait:
            ftype, channel, frame = self.conn.expect_frame (spec.FRAME_METHOD, 'basic.cancel_ok')
        self.forget_consumer (consumer_tag)

    def basic_get (self, queue='', no_ack=False):
        "http://www.rabbitmq.com/amqp-0-9-1-reference.html#basic.get"
        frame = spec.basic.get (0, queue, no_ack)
        self.send_frame (spec.FRAME_METHOD, frame)
        ftype, channel, frame = self.conn.expect_frame (spec.FRAME_METHOD, 'basic.get_ok', 'basic.empty')
        assert channel == self.num
        return frame

    def basic_publish (self, payload, exchange='', routing_key='', mandatory=False, immediate=False, properties=None):
        "http://www.rabbitmq.com/amqp-0-9-1-reference.html#basic.publish"
        frame = spec.basic.publish (0, exchange, routing_key, mandatory, immediate)
        self.send_frame (spec.FRAME_METHOD, frame)
        class_id = spec.basic.publish.id[0]  # 60
        weight = 0
        size = len (payload)
        if properties:
            flags, pdata = pack_properties (properties)
        else:
            flags = 0
            pdata = ''
        # W ('basic_publish: properties=%r\n' % (unpack_properties (flags, pdata),))
        head = struct.pack ('>hhqH', class_id, weight, size, flags)
        self.send_frame (spec.FRAME_HEADER, head + pdata)
        chunk = self.conn.tune.frame_max
        for i in range (0, size, chunk):
            self.send_frame (spec.FRAME_BODY, payload[i:i+chunk])
        if self.confirm_mode:
            self.conn.expect_frame (spec.FRAME_METHOD, 'basic.ack')

    def basic_ack (self, delivery_tag=0, multiple=False):
        "http://www.rabbitmq.com/amqp-0-9-1-reference.html#basic.ack"
        frame = spec.basic.ack (delivery_tag, multiple)
        self.send_frame (spec.FRAME_METHOD, frame)

    def get_ack (self):
        ftype, channel, frame = self.conn.expect_frame (spec.FRAME_METHOD, 'basic.ack')
        return frame

    def close (self, reply_code=0, reply_text='normal shutdown', class_id=0, method_id=0):
        "http://www.rabbitmq.com/amqp-0-9-1-reference.html#channel.close"
        frame = spec.channel.close (reply_code, reply_text, class_id, method_id)
        self.send_frame (spec.FRAME_METHOD, frame)
        ftype, channel, frame = self.conn.expect_frame (spec.FRAME_METHOD, 'channel.close_ok')
        self.conn.forget_channel (self.num)
        return frame

    def accept_delivery (self, frame, properties, data):
        probe = self.consumers.get (frame.consumer_tag, None)
        if probe is None:
            W ('received data for unknown consumer tag: %r\n' % (frame.consumer_tag,))
            if self.ack_discards:
                self.basic_ack (frame.delivery_tag)
        else:
            probe.push ((frame, properties, data))

    def make_default_consumer (self):
        "create a consumer to catch unexpected deliveries"
        con0 = consumer (self.num, '')
        return self.conn.make_default_consumer (con0)

    def add_consumer (self, con):
        self.consumers[con.tag] = con

    def forget_consumer (self, tag):
        del self.consumers[tag]

    def notify_consumers_of_close (self):
        for _, con in self.consumers.iteritems():
            con.close()

    def notify_of_close (self):
        self.notify_consumers_of_close()

    # rabbit mq extension
    def confirm_select (self, nowait=False):
        "http://www.rabbitmq.com/amqp-0-9-1-reference.html#confirm.select"
        try:
            if self.conn.server_properties['capabilities']['publisher_confirms'] != True:
                raise ProtocolError ("server capabilities says NO to publisher_confirms")
        except KeyError:
                raise ProtocolError ("server capabilities says NO to publisher_confirms")
        else:
            frame = spec.confirm.select (nowait)
            self.send_frame (spec.FRAME_METHOD, frame)
            if not nowait:
                ftype, channel, frame = self.conn.expect_frame (spec.FRAME_METHOD, 'confirm.select_ok')
            self.confirm_mode = True
            return frame

def pack_properties (props):
    sbp = spec.basic.properties
    r = []
    flags = 0
    items = sbp.bit_map.items()
    items.sort()
    items.reverse()
    for bit, name in items:
        if props.has_key (name):
            _, unpack, pack = sbp.name_map[name]
            r.append (pack (props[name]))
            flags |= (1 << bit)
    return flags, ''.join (r)

def unpack_properties (flags, data):
    sbp = spec.basic.properties
    r = {}
    pos = 0
    # these must be unpacked from highest bit to lowest [really?]
    items = sbp.bit_map.items()
    items.sort()
    items.reverse()
    for bit, name in items:
        if flags & (1 << bit):
            _, unpack, pack = sbp.name_map[name]
            r[name], pos = unpack (data, pos)
    return r

class AMQP_Consumer_Closed (Exception):
    pass

class consumer:

    """The consumer object manages the consumption of messages triggered by a call to basic.consume.

    *channel*: the channel object delivering the messages.

    *tag*: the unique consumer tag associated with the call to basic.consume
    """

    def __init__ (self, channel, tag):
        self.channel = channel
        self.tag = tag
        self.fifo = coro.fifo()
        self.closed = False

    def close (self):
        "close this consumer channel"
        self.fifo.push (connection_closed)
        self.closed = True
        self.channel.forget_consumer (self)

    def cancel (self):
        "cancel the basic.consume() call that created this consumer"
        self.closed = True
        self.channel.basic_cancel (self.tag)

    def push (self, value):
        self.fifo.push (value)

    def pop (self, ack=True):
        "pop a new value from this consumer.  Will block if no value is available."
        if self.closed:
            raise AMQP_Consumer_Closed
        else:
            probe = self.fifo.pop()
            if probe == connection_closed:
                self.closed = True
                raise AMQP_Consumer_Closed
            else:
                frame, properties, data = probe
                if ack:
                    self.channel.basic_ack (frame.delivery_tag)
                return frame, properties, ''.join (data)
