import coro
import coro.ssl.s2n
import coro.http.h2
import coro.backdoor

cfg = coro.ssl.s2n.Config()
cfg.add_cert_chain_and_key (
    open ('cert/server.crt').read(),
    open ('cert/server.raw.key').read()
)
cfg.add_dhparams (open ('cert/dhparam.pem').read())
cfg.set_cipher_preferences ('default')
cfg.set_protocol_preferences (['h2', 'http/1.1'])
#cfg.set_protocol_preferences (['http/1.1'])

server = coro.http.h2.h2_s2n_server (cfg)
server.push_handler (coro.http.handlers.favicon_handler())
server.push_handler (coro.http.handlers.coro_status_handler())
server.push_handler (coro.http.handlers.file_handler ('.'))
coro.spawn (server.start, ('0.0.0.0', 8443))
coro.spawn (coro.backdoor.serve, unix_path='/tmp/h2s.bd')
coro.event_loop (30.0)
