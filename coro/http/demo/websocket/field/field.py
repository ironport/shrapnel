# -*- Mode: Python -*-

from coro.http.websocket import handler, websocket
import math
import pickle
import random
import re

import region
import quadtree

import coro
W = coro.write_stderr

# need a way to declare a dirty region, and send a single
#   redraw command for all the dirtied objects.  So we need to separate
#   object movement from redrawing... probably with a timer of some kind,
#   accumulate dirty rects, then redraw in one swell foop
# another thing to consider: sending deltas rather than the entire list.
#  for example, if the viewport hasn't moved, then the list of rectangles
#  won't be changing.  Can we send a diff?  [this might just be easier with layers]

# for layers see: http://stackoverflow.com/questions/3008635/html5-canvas-element-multiple-layers

colors = ['red', 'green', 'blue', 'magenta', 'purple', 'plum', 'orange']

# sample 'box' object.
class box (quadtree.ob):
    def __init__ (self, color, (l,t,r,b)):
        self.color = color
        self.set_rect (l,t,r,b)
    def move (self, dx, dy):
        x0, y0, x1, y1 = self.get_rect()
        self.set_rect (
            int(x0 + dx), int(y0 + dy), int(x1 + dx), int(y0 + dy)
            )
    def cmd (self, xoff, yoff):
        # command to draw me relative to <xoff,yoff>?
        x0, y0, x1, y1 = self.get_rect()
        return 'B,%s,%d,%d,%d,%d' % (self.color, x0-xoff, y0-yoff, x1-x0, y1-y0)
    def __repr__ (self):
        return '<box (%d,%d,%d,%d)>' % self.get_rect()

class circle (box):
    def __init__ (self, color, center, radius):
        x, y = center
        r = radius
        self.color = color
        self.center = center
        self.radius = radius
        self.set_rect (*self.get_rect())
    def get_rect (self):
        x, y = self.center
        r = self.radius
        return x-r, y-r, x+r, y+r
    def move (self, dx, dy):
        x, y = self.center
        self.center = int(x + dx), int(y + dy)
        self.set_rect (*self.get_rect())
    def cmd (self, xoff, yoff):
        # command to draw me relative to <xoff,yoff>?
        x, y = self.center
        return 'C,%s,%d,%d,%d' % (self.color, x-xoff, y-yoff, self.radius)
    def __repr__ (self):
        return '<circle (%d,%d) radius=%d)>' % (self.center[0], self.center[1], self.radius)

# should have multiple qt's:
# 1) for the background, immutable
# 2) for the client viewports
# 3) for moving objects

class field:
    def __init__ (self, w=1024*20, h=1024*20):
        self.w = w
        self.h = h
        self.Q_views = quadtree.quadtree()
        self.Q_back = quadtree.quadtree()
        self.Q_obs = quadtree.quadtree()
        self.generate_random_field()

    def generate_random_field (self):
        for i in range (5000):
            c = random.choice (colors)
            x = random.randint (0, self.w - 100)
            y = random.randint (0, self.h - 100)
            w = random.randint (50, 300)
            h = random.randint (50, 300)
            b = box (c, (x, y, x+w, y+h))
            self.Q_back.insert (b)
        for i in range (1000):
            coro.spawn (self.wanderer)

    def new_conn (self, *args, **kwargs):
        c = field_conn (self, *args, **kwargs)
        self.Q_views.insert (c)

    def new_ob (self, ob):
        self.Q_obs.insert (ob)
        #W ('new ob %r\n' % (self.Q_obs,))
        #self.Q_obs.dump()

    def move_ob (self, ob, dx, dy):
        r0 = ob.get_rect()
        self.Q_obs.delete (ob)
        ob.move (dx, dy)
        r1 = ob.get_rect()
        self.Q_obs.insert (ob)
        #self.Q_obs.dump()
        # notify any viewers
        r2 = region.union (r0, r1)
        for client in self.Q_views.search (r2):
            client.draw_window()

    sleep = 0.1
    def wanderer (self):
        # spawn me!
        x = random.randint (100, self.w - 100)
        y = random.randint (100, self.h - 100)
        c = random.choice (colors)
        ob = circle (c, (x, y), 25)
        self.new_ob (ob)
        while 1:
            # pick a random direction
            heading = random.randint (0, 360) * (math.pi / 180.0)
            speed = (random.random() * 10) + 3
            dx = math.cos (heading) * speed
            dy = math.sin (heading) * speed
            # go that way for 20 steps
            for i in range (20):
                self.move_ob (ob, dx, dy)
                # not working yet...
                ## if not ob.range_check (0, 0, self.w, self.h):
                ##     W ('%r hit an edge!\n' % (ob,))
                ##     dx = - (dx * 5)
                ##     dy = - (dy * 5)
                ##     self.move_ob (ob, dx, dy)
                coro.sleep_relative (self.sleep)

class field_conn (websocket, quadtree.ob):

    def __init__ (self, field, *args, **kwargs):
        websocket.__init__ (self, *args, **kwargs)
        self.send_mutex = coro.mutex()
        self.field = field
        rx = random.randint (0, self.field.w-1024)
        ry = random.randint (0, self.field.h-1024)
        self.set_rect (rx, ry, rx+1024, ry+1024)
        self.draw_window()
        self.mouse_down = None, None

    def move_window (self, mx, my):
        self.field.Q_views.delete (self)
        x0, y0, x1, y1 = self.get_rect()
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
        self.set_rect (x0, y0, x1, y1)
        self.field.Q_views.insert (self)
        self.draw_window()
        self.send_text ('M pos=%d,%d' % self.get_rect()[:2])

    def draw_qt (self, r, Q):
        px, py = self.get_rect()[:2]
        for ob in Q.search (self.rect):
            r.append (ob.cmd (px, py))

    def draw_window (self):
        r = ['F']
        self.draw_qt (r, self.field.Q_back)
        self.draw_qt (r, self.field.Q_obs)
        try:
            self.send_text ('|'.join (r))
        except coro.ClosedError:
            self.handle_close()

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
                x0, y0 = self.get_rect()[:2]
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
