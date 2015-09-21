import coro
import coro.ssl
import coro.http.spdy
import coro.backdoor

# god how I love openssl.
cipher_suite = "ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-DSS-AES128-GCM-SHA256:kEDH+AESGCM:ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA:ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES256-SHA:ECDHE-ECDSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:DHE-DSS-AES128-SHA256:DHE-RSA-AES256-SHA256:DHE-DSS-AES256-SHA:DHE-RSA-AES256-SHA:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!3DES:!MD5:!PSK"

ctx = coro.ssl.new_ctx (
    cert=coro.ssl.x509 (open ('cert/server.crt').read()),
    key=coro.ssl.pkey (open ('cert/server.key').read(), '', True),
    alpn_protos=['h2'], #, 'http/1.1'],
    proto='tlsv2',
    ciphers = cipher_suite,
    dhparam=coro.ssl.dh_param (open ('cert/dhparam.pem').read()),
)

server = coro.http.h2.h2_openssl_server (ctx)
server.push_handler (coro.http.handlers.favicon_handler())
server.push_handler (coro.http.handlers.coro_status_handler())
server.push_handler (coro.http.handlers.file_handler ('.'))
coro.spawn (server.start, ('0.0.0.0', 8443))
coro.spawn (coro.backdoor.serve, unix_path='/tmp/h2s.bd')
coro.event_loop (30.0)
