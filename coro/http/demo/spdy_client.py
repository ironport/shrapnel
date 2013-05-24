# -*- Mode: Python -*-

import coro
import coro.backdoor
import coro.ssl

from coro.http.spdy import spdy_client
from coro.http.protocol import header_set

W = coro.write_stderr

ctx = coro.ssl.new_ctx (
    #cert=coro.ssl.x509 (open ('cert/server.crt').read()),
    #key=coro.ssl.pkey (open ('cert/server.key').read(), '', True),
    next_protos=['spdy/2', 'http/1.1'],
    proto='tlsv1',
    )

def t0():
    global ctx, s, c
    #ctx = coro.ssl.new_ctx (proto='tlsv1', next_protos=['spdy/2', 'http/1.1'])
    s = coro.ssl.sock (ctx)
    c = spdy_client ('127.0.0.1', 9443, s)
    W ('negotiated: %r\n' % (s.ssl.get_next_protos_negotiated(),))
    h = header_set()
    req = c.send_request ('GET', '/status', h, content=None, force=True)
    req.wait()
    W ('%s\n' % (req.response,))
    print repr(req.rfile.read())
    return req

if __name__ == '__main__':
    coro.spawn (coro.backdoor.serve, unix_path='/tmp/spdy_client.bd')
    coro.event_loop (30.0)
