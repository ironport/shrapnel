# -*- Mode: Python -*-

import coro

def client (ip='127.0.0.1', port=9000):
    global alive
    alive += 1
    try:
        s = coro.tcp_sock()
        s.connect ((ip, port))
        for i in range (10):
            s.send ('howdy there\r\n')
            assert (s.recv_exact (13) == 'howdy there\r\n')
        coro.write_stderr ('.')
        s.close()
    finally:
        alive -= 1
        if alive == 0:
            coro.write_stderr ('\ndone.\n')
            coro.set_exit()

if __name__ == '__main__':
    alive = 0
    for i in range (100):
        coro.spawn (client)
    coro.event_loop()
