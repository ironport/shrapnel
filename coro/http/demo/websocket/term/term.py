# -*- Mode: Python -*-

from coro.http.websocket import handler, websocket
import pickle
import pprint
import re

import coro
W = coro.write_stderr

# python3 includes an 'html' module that does this, but it'd be nice
#   if we could just stream this transform somehow... maybe using the
#   string StreamWriter stuff?

def escape (s):
    return s.replace ('&', '&amp;').replace ('<', '&lt;').replace ('>', '&gt;')

class terminal (websocket):

    def __init__ (self, *args, **kwargs):
        websocket.__init__ (self, *args, **kwargs)
        self.send_mutex = coro.mutex()
        self.repl = repl (self)
        self.history = []
        self.history_index = 0
        self.line = []
        self.repl.read_eval_print_loop()

    def handle_close (self):
        pass

    def send_text (self, payload):
        with self.send_mutex:
            websocket.send_text (self, payload)

    def handle_packet (self, p):
        data = p.unpack()
        event = p.unpack().split (',')
        #W ('packet = %r event=%r\n' % (p, event))
        if event[0] == 'K':
            ascii = int (event[1])
            #W ('ascii=%d\n' % (ascii,))
            if ascii in (10, 13): # lf cr
                ascii = 10
                line = ''.join (self.line)
                self.history.append (line)
                self.line = []
                self.send_text ('C')
                self.send_text ('D' + escape (line) + '\n')
                self.repl.inlines.push (line)
            elif ascii == 4: # ctrl-d
                self.repl.inlines.push (None)
            elif ascii in (16, 14): # ctrl-p, ctrl-n
                if ascii == 16:
                    self.history_index = (self.history_index + 1) % len(self.history)
                else:
                    self.history_index = (self.history_index - 1) % len(self.history)                    
                line = self.history[0 - self.history_index]
                # turn into a list of chars...
                self.line = [x for x in line]
                self.send_text ('B' + escape (line))
            else:
                self.line.append (chr (ascii))
                self.send_text ('I' + escape (chr (ascii)))
        elif event[0] == 'B':
            if len(self.line):
                del self.line[-1]
                self.send_text ('B' + ''.join (self.line))
        else:
            W ('unknown event: %r\n' % (event,))
        return False

from coro.backdoor import backdoor

class NotAuthorized (Exception):
    pass

class repl (backdoor):

    def __init__ (self, term):
        backdoor.__init__ (self, term, '\n')
        self.inlines = coro.fifo()

    def login (self):
        self.send ('Username: ')
        u = self.read_line()
        self.send ('Password: ')
        p = self.read_line()
        # XXX self.sock should really be called self.conn
        if self.sock.handler.auth_dict.get (u, None) != p:
            coro.sleep_relative (3)
            self.send ('Sorry, Charlie\n')
            self.sock.conn.close()
            raise NotAuthorized (u)

    def print_result (self, result):
        pprint.pprint (result)

    def read_line (self):
        line = self.inlines.pop()
        if line is None:
            self.sock.send_text ('D' + escape ('goodbye!\n'))
            self.sock.conn.close()
        else:
            return line

    def send (self, data):
        # Note: sock is really a terminal object
        self.sock.send_text ('D' + escape (data))

if __name__ == '__main__':
    import coro.http
    import coro.backdoor
    import os
    ih = coro.http.handlers.favicon_handler()
    sh = coro.http.handlers.coro_status_handler()
    th = handler ('/term', terminal)
    th.auth_dict = {'foo':'bar'}
    # serve files out of this directory
    fh = coro.http.handlers.file_handler (os.getcwd())
    handlers = [th, ih, sh, fh]
    #server = coro.http.server()
    #server = coro.http.tlslite_server (
    #    # should point to the test cert in coro/http/cert/
    #    '../../../cert/server.crt',
    #    '../../../cert/server.key',
    #    )
    import coro.ssl
    from coro.ssl import openssl
    ctx = coro.ssl.new_ctx (
        cert = openssl.x509 (open('../../../cert/server.crt').read()),
        key  = openssl.pkey (open('../../../cert/server.key').read(), private=True),
        )
    server = coro.http.openssl_server (ctx)
    for h in handlers:
        server.push_handler (h)
    #coro.spawn (server.start)
    coro.spawn (server.start, ('0.0.0.0', 9001))
    coro.spawn (coro.backdoor.serve, unix_path='/tmp/ws.bd')
    coro.event_loop (30.0)
