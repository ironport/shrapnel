# -*- Mode: Python -*-

# http://en.wikipedia.org/wiki/ANSI_escape_code

import array
import coro
import math

W = coro.write_stderr

CSI = '\x1B['

at_format = CSI + '%d;%dH%s' # + CSI + '0m'

def at (x, y, ch):
    return at_format % (y, x, ch)

import random

class arena:
    def __init__ (self, w=150, h=53):
        self.w = w
        self.h = h
        self.data = [ array.array ('c', " " * w) for y in range (h) ]
        # put some walls around the outside
        for i in range (w):
            self.data[0][i] = '='
            self.data[-1][i] = '='
        for j in range (h):
            self.data[j][0] = '|'
            self.data[j][-1] = '|'
        self.data[0][0] = '+'
        self.data[0][-1] = '+'
        self.data[-1][0] = '+'
        self.data[-1][-1] = '+'
        self.worms = []
        self.listeners = []
    def random_pos (self):
        while 1:
            x = random.randrange (1, self.w-1)
            y = random.randrange (1, self.h-1)
            if self[x,y] == ' ':
                break
        return x, y
    def render (self):
        return '\n'.join (x.tostring() for x in self.data)
    def __getitem__ (self, (x, y)):
        return self.data[y][x]
    def draw (self, pos, chr='*'):
        x, y = pos
        if self.data[y][x] in "=|+":
            import pdb; pdb.set_trace()
        self.data[y][x] = chr
        for lx in self.listeners:
            lx.draw (pos, chr)
    def erase (self, pos):
        x, y = pos
        self.data[y][x] = ' '
        for lx in self.listeners:
            lx.erase (pos)
    def populate (self, n=5):
        for i in range (n):
            x, y = self.random_pos()
            self.worms.append (worm (self, x, y))
    def cull (self, hoffa=False):
        for worm in self.worms:
            if worm.stunned:
                W ('culling worm %r\n' % (worm.chr,))
                worm.kill (hoffa)

class worm:

    counter = 0

    # up down left right
    movex = [0,0,-1,1]
    movey = [-1,1,0,0]

    def __init__ (self, arena, x, y, length=10):
        self.arena = arena
        self.head = x, y
        self.tail = []
        self.dir = random.randrange (0, 4)
        self.length = length
        worm.counter += 1
        self.chr = '0123456789abcdefghijklmnopqrstuvwxyz'[worm.counter%36]
        self.speed = random.randrange (200, 400)
        self.exit = False
        self.stunned = False
        W ('new worm %r @ %d, %d speed=%d\n' % (self.chr, x, y, self.speed))
        coro.spawn (self.go)
        
    def go (self):
        try:
            while not self.exit:
                coro.sleep_relative (self.speed / 10000.0)
                if random.randrange (0,20) == 10:
                    if not self.turn():
                        return
                else:
                    nx, ny = self.update()
                    while self.arena[(nx,ny)] != ' ':
                        if not self.turn():
                            return
                        nx, ny = self.update()
                    self.move ((nx, ny))                        
        finally:
            self.arena.worms.remove (self)

    def update (self):
        x, y = self.head
        return (
            x + self.movex[self.dir],
            y + self.movey[self.dir]
            )

    def turn (self):
        while not self.exit:
            x, y = self.head
            a = self.arena
            choices = []
            for i in range (4):
                nx = x + self.movex[i]
                ny = y + self.movey[i]
                if a[nx,ny] == ' ':
                    choices.append (i)
            if not choices:
                return self.stun()
            else:
                self.dir = random.choice (choices)
                return True

    def stun (self):
        self.stunned = True
        for pos in self.tail:
            self.arena.draw (pos, '*')
        coro.sleep_relative (5)
        self.stunned = False
        return not self.exit

    def move (self, pos):
        self.tail.append (self.head)
        self.head = pos
        self.arena.draw (pos, self.chr)
        if len (self.tail) > self.length:
            tpos = self.tail.pop (0)
            self.arena.erase (tpos)

    def kill (self, hoffa=True):
        self.arena.erase (self.head)
        for pos in self.tail:
            if hoffa:
                self.arena.draw (pos, '#')
            else:
                self.arena.erase (pos)
        self.exit = True
        self.head = (None, None)
        self.tail = []

class terminal:
    def __init__ (self, conn):
        self.conn = conn
        self.conn.send (
            '\xff\xfc\x01' # IAC WONT ECHO 
            '\xff\xfb\x03' # IAC WILL SUPPRESS_GO_AHEAD
            '\xff\xfc"'    # IAC WONT LINEMODE
            )
        # turn off the cursor
        self.conn.send (CSI + '?25l')
        self.fifo = coro.fifo()
        self.redraw()
        self.t0 = coro.spawn (self.listen)
        self.t1 = coro.spawn (self.writer)
        self.exit = False
    def redraw (self):
        self.fifo.push (''.join ([
            # clear the screen
            CSI + '2J',
            # move to home
            CSI + '1;1H',
            # draw the arena
            the_arena.render(),
            '\n keys: [q]uit [r]edraw [n]ew [c]ull [l]engthen [h]offa\n',
            ]))
    def draw (self, (x, y), chr):
        chr = (
            CSI
            + '%dm' % (40+ord(chr)%8,)
            + CSI
            + '%dm' % (30+ord(chr)%7,)
            + chr
            + CSI
            + '0m'
            )
        self.fifo.push (at (x+1, y+1, chr))
    def erase (self, (x, y)):
        self.fifo.push (at (x+1, y+1, ' '))
    def writer (self):
        while not self.exit:
            data = self.fifo.pop()
            if data is None:
                break
            else:
                self.conn.send (data)
    def listen (self):
        while not self.exit:
            byte = self.conn.recv (1)
            if byte == '\xff':
                # telnet stuff, dump it
                self.conn.recv (2)
            elif byte == 'r':
                self.redraw()
            elif byte == 'n':
                the_arena.populate (1)
            elif byte == 'c':
                the_arena.cull()
            elif byte == 'l':
                for worm in the_arena.worms:
                    worm.length += 1
            elif byte == 'h':
                the_arena.cull (hoffa=True)
            elif byte == 'q':
                self.exit = True
                # turn the cursor back on...
                self.conn.send (CSI + '?25h')
        the_arena.listeners.remove (self)
        self.conn.close()
        self.fifo.push (None)

def status():
    while 1:
        coro.sleep_relative (2)
        coro.write_stderr ('%5d worms %5d threads\n' % (len(the_arena.worms), len(coro.all_threads)))

def serve():
    s = coro.tcp_sock()
    s.bind (('', 9001))
    s.listen (5)
    while 1:
        c, a = s.accept()
        t = terminal (c)
        the_arena.listeners.append (t)

if __name__ == '__main__':
    import coro.backdoor
    the_arena = arena()
    the_arena.populate (10)
    coro.spawn (status)
    coro.spawn (serve)
    coro.spawn (coro.backdoor.serve, unix_path='/tmp/xx.bd')
    #import coro.profiler
    #coro.profiler.go (coro.event_loop)
    coro.event_loop()
