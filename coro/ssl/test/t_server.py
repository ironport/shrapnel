# -*- Mode: Python -*-

import coro
from coro.ssl import openssl
import coro.ssl
import coro.backdoor

W = coro.write_stderr

ctx = openssl.ssl_ctx()
ctx.use_cert (openssl.x509 (open ('../../http/cert/server.crt').read()))
ctx.use_key (openssl.pkey (open ('../../http/cert/server.key').read(), '', True))
ctx.set_ciphers ('RC4-SHA:RC4-MD5:ALL')
# ctx.set_tmp_dh (openssl.dh_param (open ('../../http/cert/dh_param_1024.pem').read()))
# ctx.set_next_protos (['spdy/2', 'http/1.1'])

def session (conn, addr):
    conn.ssl.set_fd (conn.fd)
    try:
        print 'conn=', conn, conn.__class__
        while 1:
            block = conn.recv (1000)
            if not block:
                break
            else:
                conn.send (block)
    finally:
        coro.sleep_relative (1000)
        W ('why for I exit?\n')

all_conns = []

def serve (port=9000):
    s = coro.ssl.sock (ctx)
    s.bind (('0.0.0.0', port))
    s.listen (50)
    print 's=', s
    while 1:
        conn, addr = s.accept()
        print 'conn, addr=', conn, addr
        all_conns.append (conn)
        coro.spawn (session, conn, addr)

if __name__ == '__main__':
    coro.spawn (coro.backdoor.serve, unix_path='/tmp/xx.bd')
    coro.spawn (serve)
    coro.event_loop()
