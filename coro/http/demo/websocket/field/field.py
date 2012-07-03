# -*- Mode: Python -*-

from coro.http.websocket import handler, websocket
import pickle
import random
import re

import quadtree

import coro
W = coro.write_stderr

colors = ['red', 'green', 'blue', 'magenta', 'purple', 'plum', 'orange']

# sample 'box' object.
class box:
    def __init__ (self, color, rect):
        self.color = color
        self.rect = rect
    def get_rect (self):
        return self.rect
    def __repr__ (self):
        return '<box (%d,%d,%d,%d)>' % self.rect

class field:
    def __init__ (self, w=1024*20, h=1024*20):
        self.w = w
        self.h = h
        self.clients = set()
        self.Q = quadtree.quadtree()
        self.generate_random_field()

    def generate_random_field (self):
        for i in range (5000):
            x = random.randint (0, self.w - 100)
            y = random.randint (0, self.h - 100)
            w = random.randint (50, 300)
            h = random.randint (50, 300)
            c = random.choice (colors)
            b = box (c, (x, y, x+w, y+h))
            self.Q.insert (b)

    def new_conn (self, *args, **kwargs):
        c = field_conn (self, *args, **kwargs)
        self.clients.add (c)

class field_conn (websocket):

    def __init__ (self, field, *args, **kwargs):
        websocket.__init__ (self, *args, **kwargs)
        self.send_mutex = coro.mutex()
        self.field = field
        rx = random.randint (0, self.field.w-1024)
        ry = random.randint (0, self.field.h-1024)
        self.rect = (rx, ry, rx+1024, ry+1024)
        self.draw_window()
        self.mouse_down = None, None

    def move_window (self, mx, my):
        x0, y0, x1, y1 = self.rect
        x0 = x0 + mx; y0 = y0 + my
        x1 = x1 + mx; y1 = y1 + my
        if x0 < 0:
            x0 = 0; x1 = 1024
        if y0 < 0:
            y0 = 0; y1 = 1024
        if x1 > self.field.w-1024:
            x1 = self.field.w-1024; x0 = x1 - 1024
        if y1 > self.field.h-1024:
            y1 = self.field.h-1024; y0 = y1 - 1024
        self.rect = (x0, y0, x1, y1)
        self.draw_window()
        self.send_text ('M pos=%d,%d' % self.rect[:2])

    def draw_window (self):
        r = ['F']
        px, py = self.rect[:2]
        for ob in self.field.Q.search_gen (self.rect):
            c = ob.color
            x0, y0, x1, y1 = ob.get_rect()
            r.append ('B,%s,%d,%d,%d,%d' % (c, x0-px, y0-py, x1-x0, y1-y0))
        self.send_text ('|'.join (r))

    def send_text (self, payload):
        with self.send_mutex:
            websocket.send_text (self, payload)

    def handle_packet (self, p):
        data = p.unpack()
        event = p.unpack().split (',')
        #W ('packet = %r event=%r\n' % (p, event))
        if event[0] == 'KD':
            ascii = int (event[1])
            if ascii == 87: # W
                self.move_window (0, -10)
            elif ascii == 65: # A
                self.move_window (-10, 0)
            elif ascii == 83: # S
                self.move_window (0, 10)
            elif ascii == 68: # D
                self.move_window (10, 0)
            elif ascii == 82: # R
                x0, y0 = self.rect[:2]
                self.move_window (-x0, -y0)
        elif event[0] == 'MD':
            self.on_mouse_down (int (event[1]), int (event[2]))
        elif event[0] == 'MU':
            self.on_mouse_up (int (event[1]), int (event[2]))
        elif event[0] == 'MM':
            self.on_mouse_move (int (event[1]), int (event[2]))
        elif event[0] == 'TS':
            tl = self.unpack_touch_list (event[1:])
            self.last_touch_move = tl[0][0], tl[0][1]
            self.on_mouse_down (tl[0][0], tl[0][1])
        elif event[0] == 'TM':
            tl = self.unpack_touch_list (event[1:])
            self.last_touch_move = tl[0][0], tl[0][1]
            self.on_mouse_move (tl[0][0], tl[0][1])
        elif event[0] == 'TE':
            # emulate mouse up by with saved last touch_move
            x0, y0 = self.last_touch_move
            if x0 is not None:
                self.on_mouse_up (x0, y0)
            self.last_touch_move = None, None
        else:
            W ('unknown event: %r\n' % (event,))
        return False

    def unpack_touch_list (self, tl):
        return [ [int(y) for y in x.split('.')] for x in tl ]

    def on_mouse_down (self, x, y):
        self.mouse_down = x, y
        
    def on_mouse_up (self, x1, y1):
        x0, y0 = self.mouse_down
        self.mouse_down = None, None
        # 1) draw a box in the region chosen
        #if x0 > x1:
        #    x0, x1 = x1, x0
        #if y0 > y1:
        #    y0, y1 = y1, y0
        #px, py = self.rect[:2]
        #b = box (random.choice (colors), (x0+px, y0+py, x1+px, y1+py))
        #self.field.Q.insert (b)
        # 2) or move the window
        if x0 is not None:
            self.move_window (x0-x1, y0-y1)
            self.draw_window()

    def on_mouse_move (self, x1, y1):
        x0, y0 = self.mouse_down
        if x0:
            if abs(x1-x0) > 10 or abs(y1-y0) > 10:
                # moved enough to redraw
                self.mouse_down = x1, y1
                self.move_window (x0-x1, y0-y1)

if __name__ == '__main__':
    import coro.http
    import coro.backdoor
    import os
    cwd = os.getcwd()
    f = field()
    ih = coro.http.handlers.favicon_handler()
    sh = coro.http.handlers.coro_status_handler()
    th = handler ('/field', f.new_conn)
    fh = coro.http.handlers.file_handler (cwd)
    # so you can browse the source
    import mimetypes
    mimetypes.init()
    mimetypes.add_type ('text/plain', '.py')
    handlers = [th, ih, sh, fh]
    #server = coro.http.server (('0.0.0.0', 9001))
    server = coro.http.server()
    for h in handlers:
        server.push_handler (h)
    #coro.spawn (server.start)
    coro.spawn (server.start, ('0.0.0.0', 9001))
    coro.spawn (coro.backdoor.serve, unix_path='/tmp/ws.bd')
    coro.event_loop (30.0)
