# -*- Mode: Python -*-

# http://martinsikora.com/nodejs-and-websocket-simple-chat-tutorial

import json
from coro.http.websocket import handler, websocket

import coro
W = coro.write_stderr

class server:

    colors = ['red', 'green', 'blue', 'magenta', 'purple', 'plum', 'orange']

    def __init__ (self):
        self.clients = set()
        self.color_index = 0

    def next_color (self):
        r = self.colors[self.color_index % len (self.colors)]
        self.color_index += 1
        return r

    def new_session (self, *args, **kwargs):
        self.clients.add (connection (self, *args, **kwargs))

    def broadcast (self, name, color, payload):
        to_remove = set()
        for client in self.clients:
            try:
                client.send_message (name, color, payload)
            except:
                to_remove.add (client)
        self.clients.difference_update (to_remove)

class connection (websocket):

    def __init__ (self, server, *args, **kwargs):
        websocket.__init__ (self, *args, **kwargs)
        self.server = server
        self.color = server.next_color()
        self.name = None

    def handle_packet (self, p):
        payload = p.unpack()
        if p.opcode == 0x01:
            if self.name is None:
                reply = json.dumps ({'type':'color', 'data':self.color})
                self.send_text (reply)
                self.name = payload
            else:
                self.server.broadcast (self.name, self.color, payload)
        return False

    def send_message (self, name, color, message):
        #W ('send_message %r %r %r\n' % (name, color, message))
        self.send_text (
            json.dumps ({
                'type':'message',
                'data': {
                    'time' : int (coro.now_usec / 1000000),
                    'text' : message,
                    'author' : name,
                    'color' : color
                    }
                })
            )

if __name__ == '__main__':
    import coro.http
    import coro.backdoor
    import os
    cwd = os.getcwd()

    chat_server = server()

    ih = coro.http.handlers.favicon_handler()
    sh = coro.http.handlers.coro_status_handler()
    fh = coro.http.handlers.file_handler (cwd)
    wh = handler ('/chat', chat_server.new_session)
    handlers = [ih, sh, fh, wh]
    #http_server = coro.http.server (('0.0.0.0', 9001))
    http_server = coro.http.server ()
    for h in handlers:
        http_server.push_handler (h)
    coro.spawn (http_server.start, ('0.0.0.0', 9001))
    coro.spawn (coro.backdoor.serve, unix_path='/tmp/ws_chat.bd')
    coro.event_loop (30.0)
