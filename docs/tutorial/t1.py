# -*- Mode: Python -*-

import coro
import coro.backdoor

def session (conn, addr):
    while 1:
        block = conn.recv (1000)
        if not block:
            break
        else:
            conn.send (block)

def serve (port=9000):
    s = coro.tcp_sock()
    s.bind (('', port))
    s.listen (50)
    while 1:
        conn, addr = s.accept()
        coro.spawn (session, conn, addr)

if __name__ == '__main__':
    coro.spawn (coro.backdoor.serve, unix_path='/tmp/xx.bd')
    coro.spawn (serve)
    coro.event_loop()
