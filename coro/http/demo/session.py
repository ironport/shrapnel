# -*- Mode: Python -*-

import coro
import coro.http
import coro.backdoor

# demonstrate the session handler

import sys
W = sys.stderr.write

def session (sid, fifo):
    i = 0
    while 1:
        try:
            # wait a half hour for a new hit
            request = coro.with_timeout (1800, fifo.pop)
        except coro.TimeoutError:
            break
        else:
            request['content-type'] = 'text/html'
            if i == 10:
                request.push (
                    '<html><h1>Session Over!  Bye!</h1>'
                    '<a href="session">start over</a>'
                    '</html>'
                )
                request.done()
                break
            else:
                request.push (
                    '<html><h1>Session Demo</h1><br><h2>Hit=%d</h2>'
                    '<a href="session">hit me!</a>'
                    '</html>' % (i,)
                )
                request.done()
            i += 1

server = coro.http.server()
server.push_handler (coro.http.handlers.coro_status_handler())
server.push_handler (coro.http.session_handler.session_handler ('session', session))
server.push_handler (coro.http.handlers.favicon_handler())
coro.spawn (server.start, ('0.0.0.0', 9001))
coro.spawn (coro.backdoor.serve, unix_path='/tmp/httpd.bd')
coro.event_loop (30.0)
