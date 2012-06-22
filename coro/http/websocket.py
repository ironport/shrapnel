# -*- Mode: Python -*-

import base64
import struct
import coro
import os
import sys
import hashlib

from coro.http.protocol import HTTP_Upgrade

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
        r[i] = chr (ord (data[i]) ^ mask[i%4])
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

    def __init__ (self, path, handler):
        self.path = path
        self.handler = handler
                  
    def match (self, request):
        return request.path == self.path and request.method == 'get' and request['upgrade'] == 'websocket'

    def handle_request (self, request):
        rh = request.request_headers
        key = rh.get_one ('sec-websocket-key')
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
            r.append (
                'Sec-WebSocket-Protocol: %s' % (
                    rh.get_one ('sec-websocket-protocol')
                    )
                )
        conn = request.client.conn
        conn.send ('\r\n'.join (r) + '\r\n\r\n')
        # pass this websocket off to its new life...
        self.handler (request, conn)
        raise HTTP_Upgrade
        
class websocket:

    def __init__ (self, http_request, conn):
        self.conn = conn
        coro.spawn (self.protocol)

    def recv_exact (self, size):
        left = size
        r = []
        while left:
            block = self.conn.recv (left)
            if not block:
                break
            else:
                r.append (block)
                left -= len (block)
        return ''.join (r)

    def protocol (self):
        while 1:
            close_it = self.read_packet()
            if close_it:
                break
        
    def read_packet (self):
        head = self.recv_exact (2)
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
            plen, = struct.unpack ('>H', self.recv_exact (2))
        else: # plen == 127:
            plen, = struct.unpack ('>Q', self.recv_exact (8))
        p.plen = plen
        if p.mask:
            p.masking = struct.unpack ('>BBBB', self.recv_exact (4))
        else:
            p.masking = None
        p.payload = self.recv_exact (plen)
        if p.opcode in (0, 1, 2):
            return self.handle_packet (p)
        elif p.opcode == 8:
            # close
            return True
        elif p.opcode == 9:
            # ping
            assert (p.fin) # probably up to no good...
            self.send_pong (self, p.payload)
            return False
        else:
            raise UnknownOpcode (p)

    def handle_packet (self, p):
        # abstract method, override to implement your own logic
        return False

    def send_text (self, data, fin=True):
        return self.send_packet (0x01, data, fin)

    def send_binary (self, data, fin=True):
        return self.send_packet (0x02, data, fin)

    def send_pong (self, data):
        return self.send_packet (0x0a, data, True)

    def send_packet (self, opcode, data, fin=True):
        head = 0
        if fin:
            head |= 0x8000
        assert opcode in (0, 1, 2, 8, 9, 10)
        head |= opcode << 8
        ld = len (data)
        if ld < 126:
            head |= ld
            p = [ struct.pack ('>H', head), data ]
        elif ld < 1<<16:
            head |= 126
            p = [ struct.pack ('>HH', head, ld), data ]
        elif ld < 1<<32:
            head |= 127
            p = [ struct.pack ('>HQ', head, ld), data ]
        else:
            raise TooMuchData (ld)
        # RFC6455: A server MUST NOT mask any frames that it sends to the client.
        self.conn.writev (p)
