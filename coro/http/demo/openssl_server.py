# -*- Mode: Python -*-

# demo an https server using OpenSSL.

import coro
import coro.http
import coro.backdoor
from coro.ssl import openssl

ctx = coro.ssl.new_ctx (
    cert = openssl.x509 (open('../cert/server.crt').read()),
    key  = openssl.pkey (open('../cert/server.key').read(), private=True),
    )

server = coro.http.openssl_server (ctx)
server.push_handler (coro.http.handlers.coro_status_handler())
server.push_handler (coro.http.handlers.favicon_handler())
coro.spawn (server.start, ('0.0.0.0', 9443))
coro.spawn (coro.backdoor.serve, unix_path='/tmp/https.bd')
coro.event_loop (30.0)
