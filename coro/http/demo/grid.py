# -*- Mode: Python -*-

import coro
import coro.http
import coro.backdoor

# toy: move an X through a grid.
# tests: POST data, compression, persistent connections, shared state

import sys
W = sys.stderr.write

class grid_handler:

    def __init__ (self, w, h):
        self.w = w
        self.h = h
        self.grid = [['.' for x in range (w)] for y in range (h)]
        self.pos = [w / 2, h / 2]
        self.grid[self.pos[1]][self.pos[0]] = 'X'

    def match (self, request):
        return request.path.startswith ('/grid')

    def handle_request (self, request):
        if request.path == '/grid/source':
            request['content-type'] = 'text/plain'
            request.set_deflate()
            request.push (open ('grid.py', 'rb').read())
            request.done()
            return
        request['content-type'] = 'text/html'
        request.set_deflate()
        if request.file:
            data = request.file.read()
            pairs = [x.split('=') for x in data.split ('&')]
            for k, v in pairs:
                if k == 'dir':
                    x0, y0 = self.pos
                    x1, y1 = self.pos
                    if v == 'left':
                        x1 = max (x0 - 1, 0)
                    elif v == 'right':
                        x1 = min (x0 + 1, self.w - 1)
                    elif v == 'up':
                        y1 = max (y0 - 1, 0)
                    elif v == 'down':
                        y1 = min (y0 + 1, self.h - 1)
                    else:
                        pass
                    self.grid[y0][x0] = '*'
                    self.grid[y1][x1] = 'X'
                    self.pos = [x1, y1]
        else:
            pass
        l = []
        for y in self.grid:
            l.append (''.join (y))
        request.push ('<pre>')
        request.push ('\n'.join (l))
        request.push ('\n</pre>\n')
        request.push (
            '<form name="input" action="grid" method="post">'
            '<input type="submit" name="dir" value="left" />'
            '<input type="submit" name="dir" value="right" />'
            '<input type="submit" name="dir" value="up" />'
            '<input type="submit" name="dir" value="down" />'
            '</form>'
            '<a href="/grid/source">source for this handler</a>'
        )
        request.done()

server = coro.http.server()
server.push_handler (grid_handler (50, 30))
server.push_handler (coro.http.handlers.coro_status_handler())
server.push_handler (coro.http.handlers.favicon_handler())
coro.spawn (server.start, ('0.0.0.0', 9001))
coro.spawn (coro.backdoor.serve, unix_path='/tmp/httpd.bd')
coro.event_loop (30.0)
