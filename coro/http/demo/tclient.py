# -*- Mode: Python -*-

import coro
W = coro.write_stderr

from coro.http.client import client as http_client
from coro.http.protocol import header_set

def t0():
    c = http_client ('127.0.0.1', 80)
    h = header_set()
    l = [c.send_request ('GET', '/postgresql/html/', h, content=None, force=True) for x in range (10)]
    for req in l:
        req.wait()
        W ('%s\n' % (req.response,))

def t1():
    c = http_client ('127.0.0.1', 80)
    rl = coro.in_parallel ([(c.GET, ('/postgresql/html/',))] * 10)
    for x in rl:
        W ('%s\n' % (x.response,))
    return rl

if __name__ == '__main__':
    import coro.backdoor
    coro.spawn (t0)
    coro.spawn (coro.backdoor.serve, unix_path='/tmp/xx.bd')
    coro.event_loop()
