# -*- Mode: Python -*-

from coro.http.websocket import handler, websocket
import pickle
import re

import coro
W = coro.write_stderr

def timestamp():
    return coro.now / 1000000

drawing_re = re.compile ('drawing_([0-9]+).bin')
draw_re = re.compile ('D,([0-9]+),([0-9]+),([0-9]+),([0-9]+)')

class server:

    def __init__ (self):
        self.clients = set()
        self.dead = set()
        self.drawing = []
        self.timestamp = timestamp()
        all = self.get_all_drawings()
        if len (all):
            self.set_drawing (all[0])

    def new_session (self, *args, **kwargs):
        client = sketch_conn (self, *args, **kwargs)
        self.clients.add (client)
        for payload in self.drawing:
            client.send_text (payload)

    def clear_drawing (self):
        self.save_drawing()
        self.broadcast ('CD', False)

    def get_all_drawings (self):
        import os
        files = os.listdir ('.')
        r = []
        for path in files:
            m = drawing_re.match (path)
            if m:
                stamp = int (m.group(1))
                r.append (stamp)
        r.sort()
        return r

    def get_path (self, stamp):
        return 'drawing_%d.bin' % (stamp,)

    def save_drawing (self):
        if len(self.drawing):
            W ('saving %r\n' % (self.timestamp,))
            f = open (self.get_path (self.timestamp), 'wb')
            drawing, self.drawing = self.drawing, []
            self.timestamp = timestamp()
            pickle.dump (drawing, f)
            f.close()
        else:
            W ('empty drawing [no save]\n')

    def next_drawing (self):
        all = self.get_all_drawings()
        for t in all:
            if t > self.timestamp:
                self.set_drawing (t)
                return

    def prev_drawing (self):
        all = self.get_all_drawings()
        all.reverse()
        for t in all:
            if t < self.timestamp:
                self.set_drawing (t)
                return

    def set_drawing (self, stamp):
        self.save_drawing()
        self.timestamp = stamp
        self.drawing = pickle.load (open (self.get_path (stamp)))
        self.broadcast ('CD', False)
        W ('set drawing %d [%d lines]\n' % (stamp, len(self.drawing)))
        for payload in self.drawing:
            self.broadcast (payload, False)
        W ('done\n')

    def broadcast (self, payload, save=True):
        if save:
            self.drawing.append (payload)
        # copy to avoid "Set changed size during iteration"
        for client in list (self.clients):
            try:
                client.send_text (payload)
            except:
                self.dead.add (client)
                tb = coro.compact_traceback()
                W ('error: tb=%r' % (tb,))
        self.clients.difference_update (self.dead)
        self.dead = set()

    def undo (self):
        if len (self.drawing):
            last = self.drawing.pop()
            m = draw_re.match (last)
            if m:
                self.broadcast ('E,%s,%s,%s,%s' % m.groups(), save=False)

class sketch_conn (websocket):

    def __init__ (self, server, *args, **kwargs):
        self.send_mutex = coro.mutex()
        self.server = server
        self.mouse_down = False
        self.line_start = None, None
        websocket.__init__ (self, *args, **kwargs)

    def handle_close (self):
        self.server.dead.add (self)

    def send_text (self, payload):
        with self.send_mutex:
            websocket.send_text (self, payload)

    def handle_packet (self, p):
        event = p.unpack().split (',')
        #W ('packet = %r event=%r\n' % (p, event))
        if event[0] == 'MD':
            self.mouse_down = True
            self.line_start = int (event[1]), int (event[2])
        elif event[0] == 'MU':
            self.mouse_down = False
        elif event[0] == 'MM':
            if self.mouse_down:
                x1, y1 = int (event[1]), int (event[2])
                self.server.broadcast (
                    'D,%d,%d,%s,%s' % (
                        self.line_start[0], self.line_start[1], x1, y1
                        )
                    )
                self.line_start = x1, y1
        elif event[0] == 'CD':
            self.server.clear_drawing()
        elif event[0] == 'ND':
            self.server.next_drawing()
        elif event[0] == 'PD':
            self.server.prev_drawing()
        elif event[0] == 'KD':
            if event[1] == '85': # 'U'
                self.server.undo()
            elif event[1] == '82': # 'R'
                self.server.set_drawing (self.server.timestamp)
        else:
            W ('unknown event: %r\n' % (event,))
        return False

if __name__ == '__main__':
    import coro.http
    import coro.backdoor
    import os
    cwd = os.getcwd()
    sketch_server = server()
    ih = coro.http.handlers.favicon_handler()
    sh = coro.http.handlers.coro_status_handler()
    wh = handler ('/sketch', sketch_server.new_session)
    fh = coro.http.handlers.file_handler (cwd)
    handlers = [wh, ih, sh, fh]
    #server = coro.http.server (('0.0.0.0', 9001))
    server = coro.http.server()
    for h in handlers:
        server.push_handler (h)
    #coro.spawn (server.start)
    coro.spawn (server.start, ('0.0.0.0', 9001))
    coro.spawn (coro.backdoor.serve, unix_path='/tmp/ws.bd')
    coro.event_loop (30.0)
