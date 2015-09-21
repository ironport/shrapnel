import coro
import coro.ssl.s2n
import coro.http.spdy
import coro.backdoor

cfg = coro.ssl.s2n.Config()
cfg.add_cert_chain_and_key (
    open ('cert/server.crt').read(),
    open ('cert/server.raw.key').read()
)
cfg.add_dhparams (open ('cert/dhparam.pem').read())
cfg.set_cipher_preferences ('default')
cfg.set_protocol_preferences (['spdy/3.1', 'http/1.1'])

server = coro.http.spdy.spdy_s2n_server (cfg)
server.push_handler (coro.http.handlers.favicon_handler())
server.push_handler (coro.http.handlers.coro_status_handler())
server.push_handler (coro.http.handlers.file_handler ('.'))
coro.spawn (server.start, ('0.0.0.0', 7443))
coro.spawn (coro.backdoor.serve, unix_path='/tmp/spdys.bd')
coro.event_loop (30.0)
