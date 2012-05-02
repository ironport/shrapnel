# -*- Mode: Python -*-

import coro
W = coro.write_stderr

class session:
    counter = 0
    def __init__ (self, conn, addr, saddr):
        self.conn = conn
        self.addr = addr
        self.saddr = saddr
        self.id = session.counter
        session.counter += 1
        self.proxy = coro.tcp_sock()
        self.proxy.connect (saddr)
        coro.spawn (self.feed, self.conn, self.proxy, '<==')
        coro.spawn (self.feed, self.proxy, self.conn, '==>')

    def feed (self, c0, c1, dir):
        try:
            while 1:
                block = c0.recv (1000)
                W ('%s %d %r\n' % (dir, self.id, block))
                if not block:
                    break
                else:
                    c1.send (block)
        finally:
            c0.close()

def serve (saddr):
    ip, port = saddr
    s = coro.tcp_sock()
    s.bind (('0.0.0.0', port + 9000))
    s.listen (5)
    while 1:
        conn, caddr = s.accept()
        coro.spawn (session, conn, caddr, saddr)
                
if __name__ == '__main__':
    import sys
    if len (sys.argv) < 3:
        print 'Usage: %s <server-host> <server-port>' % sys.argv[0]
    else:
        coro.spawn (serve, (sys.argv[1], int (sys.argv[2])))
        coro.event_loop()
