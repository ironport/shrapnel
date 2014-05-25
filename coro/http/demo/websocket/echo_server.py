# -*- Mode: Python -*-

from coro.http.websocket import handler, websocket

import coro
W = coro.write_stderr

class echo_server (websocket):

    def __init__ (self, *args, **kwargs):
        self.pending = []
        websocket.__init__ (self, *args, **kwargs)

    def handle_packet (self, p):
        # W ('packet=%r\n' % (p,))
        self.pending.append (p.unpack())
        if p.fin:
            data, self.pending = self.pending, []
            self.send_text (''.join (data))
        return False

if __name__ == '__main__':
    import coro.http
    import coro.backdoor
    fh = coro.http.handlers.favicon_handler()
    sh = coro.http.handlers.coro_status_handler()
    wh = handler ('/echo', echo_server)
    handlers = [fh, sh, wh]
    # server = coro.http.server (('0.0.0.0', 9001))
    server = coro.http.server ()
    for h in handlers:
        server.push_handler (h)
    # coro.spawn (server.start)
    coro.spawn (server.start, ('0.0.0.0', 9001))
    coro.spawn (coro.backdoor.serve, unix_path='/tmp/ws.bd')
    coro.event_loop (30.0)
