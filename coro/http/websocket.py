# -*- Mode: Python -*-

import base64
import struct
import coro
import os
import sys
import hashlib

W = coro.write_stderr

from coro.http.protocol import HTTP_Upgrade
from coro import read_stream

# RFC 6455

class WebSocketError (Exception):
    pass

class TooMuchData (WebSocketError):
    pass

class UnknownOpcode (WebSocketError):
    pass

def do_mask (data, mask):
    n = len (data)
    r = bytearray (n)
    i = 0
    while i < len (data):
        r[i] = chr (ord (data[i]) ^ mask[i % 4])
        i += 1
    return bytes (r)

class ws_packet:
    fin = 0
    opcode = 0
    mask = 0
    plen = 0
    masking = []
    payload = ''

    def __repr__ (self):
        return '<fin=%r opcode=%r mask=%r plen=%r masking=%r payload=%d bytes>' % (
            self.fin,
            self.opcode,
            self.mask,
            self.plen,
            self.masking,
            len (self.payload),
        )

    def unpack (self):
        if self.mask:
            return do_mask (self.payload, self.masking)
        else:
            return self.payload

class handler:

    magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__ (self, path, factory):
        self.path = path
        self.factory = factory

    def match (self, request):
        # try to catch both versions of the protocol
        return (
            request.path == self.path
            and request.method == 'get'
            and request['upgrade']
            and request['upgrade'].lower() == 'websocket'
        )

    def h76_frob (self, key):
        digits = int (''.join ([x for x in key if x in '0123456789']))
        spaces = key.count (' ')
        return digits / spaces

    def handle_request (self, request):
        rh = request.request_headers
        key = rh.get_one ('sec-websocket-key')
        conn = request.client.conn
        if key:
            d = hashlib.new ('sha1')
            d.update (key + self.magic)
            reply = base64.encodestring (d.digest()).strip()
            r = [
                'HTTP/1.1 101 Switching Protocols',
                'Upgrade: websocket',
                'Connection: Upgrade',
                'Sec-WebSocket-Accept: %s' % (reply,),
            ]
            if rh.has_key ('sec-websocket-protocol'):
                # XXX verify this
                r.append (
                    'Sec-WebSocket-Protocol: %s' % (
                        rh.get_one ('sec-websocket-protocol')
                    )
                )
            conn.send ('\r\n'.join (r) + '\r\n\r\n')
            protocol = 'rfc6455'
        else:
            # for Safari, this implements the obsolete hixie-76 protocol
            # http://tools.ietf.org/html/draft-hixie-thewebsocketprotocol-76
            key1 = self.h76_frob (rh.get_one ('sec-websocket-key1'))
            key2 = self.h76_frob (rh.get_one ('sec-websocket-key2'))
            tail = request.client.stream.read_exact (8)
            key = struct.pack ('>L', key1) + struct.pack ('>L', key2) + tail
            d = hashlib.new ('md5')
            d.update (key)
            reply = d.digest()
            host = rh.get_one ('host')
            r = [
                'HTTP/1.1 101 WebSocket Protocol Handshake',
                'Upgrade: WebSocket',
                'Connection: Upgrade',
                'Sec-WebSocket-Origin: http://%s' % (host,),
                'Sec-WebSocket-Location: ws://%s%s' % (host, request.uri),
            ]
            all = '\r\n'.join (r) + '\r\n\r\n' + reply
            conn.send (all)
            protocol = 'hixie_76'
        # pass this websocket off to its new life...
        self.factory (protocol, request, self)
        raise HTTP_Upgrade

class websocket:

    def __init__ (self, proto, http_request, handler):
        self.request = http_request
        self.handler = handler
        self.stream = http_request.client.stream
        self.conn = http_request.client.conn
        self.send_mutex = coro.mutex()
        # tlslite has a deeply buried "except: shutdown()" clause
        #  that breaks coro timeouts.
        self.tlslite = hasattr (self.conn, 'ignoreAbruptClose')
        self.proto = proto
        if proto == 'rfc6455':
            coro.spawn (self.read_thread)
        else:
            coro.spawn (self.read_thread_hixie_76)

    # ------------ RFC 6455 ------------
    def read_thread (self):
        close_it = False
        try:
            while 1:
                try:
                    if not self.tlslite:
                        close_it = coro.with_timeout (10, self.read_packet)
                    else:
                        close_it = self.read_packet()
                except coro.TimeoutError:
                    self.send_pong ('bleep')
                except coro.ClosedError:
                    break
                if close_it:
                    break
        finally:
            self.handle_close()
            self.conn.close()

    def read_packet (self):
        head = self.stream.read_exact (2)
        if not head:
            return True
        head, = struct.unpack ('>H', head)
        p = ws_packet()
        p.fin    = (head & 0x8000) >> 15
        p.opcode = (head & 0x0f00) >> 8
        p.mask   = (head & 0x0080) >> 7
        plen     = (head & 0x007f) >> 0
        if plen < 126:
            pass
        elif plen == 126:
            plen, = struct.unpack ('>H', self.stream.read_exact (2))
        else:  # plen == 127:
            plen, = struct.unpack ('>Q', self.stream.read_exact (8))
        p.plen = plen
        if plen > 1 << 20:
            raise TooMuchData (plen)
        if p.mask:
            p.masking = struct.unpack ('>BBBB', self.stream.read_exact (4))
        else:
            p.masking = None
        p.payload = self.stream.read_exact (plen)
        if p.opcode in (0, 1, 2):
            return self.handle_packet (p)
        elif p.opcode == 8:
            # close
            return True
        elif p.opcode == 9:
            # ping
            assert (p.fin)  # probably up to no good...
            self.send_pong (self, p.payload)
            return False
        else:
            raise UnknownOpcode (p)

    # ----------- hixie-76 -------------
    def read_thread_hixie_76 (self):
        self.stream = self.request.client.stream
        close_it = False
        try:
            while 1:
                try:
                    close_it = self.read_packet_hixie_76()
                except coro.ClosedError:
                    break
                if close_it:
                    break
        finally:
            self.conn.close()

    def read_packet_hixie_76 (self):
        ftype = self.stream.read_exact (1)
        if not ftype:
            return True
        ftype = ord (ftype)
        if ftype & 0x80:
            length = 0
            while 1:
                b = ord (self.stream.read_exact (1))
                length = (length << 7) | (b & 0x7f)
                if not b & 0x80:
                    break
                if length > 1 << 20:
                    raise TooMuchData (length)
            if length:
                payload = self.stream.read_exact (length)
            if ftype == 0xff:
                return True
        else:
            data = self.stream.read_until (b'\xff')
            if ftype == 0x00:
                p = ws_packet()
                p.fin = 1
                p.opcode = 0x01
                p.mask = None
                p.payload = data[:-1]
                self.handle_packet (p)

    # ---

    def handle_packet (self, p):
        # abstract method, override to implement your own logic
        return False

    def handle_close (self):
        # abstract method
        pass

    def send_text (self, data, fin=True):
        return self.send_packet (0x01, data, fin)

    def send_binary (self, data, fin=True):
        return self.send_packet (0x02, data, fin)

    def send_pong (self, data):
        return self.send_packet (0x0a, data, True)

    def send_packet (self, opcode, data, fin=True):
        with self.send_mutex:
            if self.proto == 'rfc6455':
                head = 0
                if fin:
                    head |= 0x8000
                assert opcode in (0, 1, 2, 8, 9, 10)
                head |= opcode << 8
                ld = len (data)
                if ld < 126:
                    head |= ld
                    p = [struct.pack ('>H', head), data]
                elif ld < 1 << 16:
                    head |= 126
                    p = [struct.pack ('>HH', head, ld), data]
                elif ld < 1 << 32:
                    head |= 127
                    p = [struct.pack ('>HQ', head, ld), data]
                else:
                    raise TooMuchData (ld)
                # RFC6455: A server MUST NOT mask any frames that it sends to the client.
                self.writev (p)
            else:
                self.writev (['\x00', data, '\xff'])

    # for socket wrapping layers like tlslite
    def writev (self, data):
        try:
            return self.conn.writev (data)
        except AttributeError:
            return self.conn.write (''.join (data))
