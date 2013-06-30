# -*- Mode: Python -*-

import coro
import coro.http
import coro.backdoor
import coro.http.json_rpc
import operator

W = coro.write_stderr

class server_root:

    def handle_json_rpc (self, method, params):
        W ('method=%r params=%r\n' % (method, params))
        if method == 'sum':
            return sum (params)
        else:
            return None

server = coro.http.server()
server.push_handler (coro.http.json_rpc.json_rpc_handler (server_root()))
server.push_handler (coro.http.handlers.coro_status_handler())
server.push_handler (coro.http.handlers.favicon_handler())
coro.spawn (server.start, ('0.0.0.0', 9001))
coro.spawn (coro.backdoor.serve, unix_path='/tmp/httpd.bd')
coro.event_loop (30.0)
