import coro
import coro.ssl
import coro.http.spdy
import coro.backdoor

ctx = coro.ssl.new_ctx (
    cert=coro.ssl.x509 (open ('cert/server.crt').read()),
    key=coro.ssl.pkey (open ('cert/server.key').read(), '', True),
    next_protos=['spdy/3', 'http/1.1'],
    proto='tlsv1',
    )

server = coro.http.spdy.spdy_openssl_server (ctx)
server.push_handler (coro.http.handlers.favicon_handler())
server.push_handler (coro.http.handlers.coro_status_handler())
coro.spawn (server.start, ('0.0.0.0', 9443))
coro.spawn (coro.backdoor.serve, unix_path='/tmp/spdys.bd')
coro.event_loop (30.0)
