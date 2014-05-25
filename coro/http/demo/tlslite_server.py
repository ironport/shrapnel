# -*- Mode: Python -*-

# demo an https server using the TLSLite package.

import coro
import coro.http
import coro.backdoor

# -----------------------------------------------------------------------
# --- change the location of the chain and key files on the next line ---
# -----------------------------------------------------------------------
server = coro.http.tlslite_server (
    'cert/server.crt',
    'cert/server.key',
)
server.push_handler (coro.http.handlers.coro_status_handler())
server.push_handler (coro.http.handlers.favicon_handler())
coro.spawn (server.start, ('0.0.0.0', 9443))
coro.spawn (coro.backdoor.serve, unix_path='/tmp/httpsd.bd')
coro.event_loop (30.0)
