# -*- Mode: Python -*-

import coro
import time
import uuid

import sys
W = sys.stderr.write

# See: http://en.wikipedia.org/wiki/HTTP_cookie#Session_cookie

def extract_session (cookie):
    parts = cookie.split (';')
    for part in parts:
        pair = [x.strip() for x in part.split ('=')]
        if len (pair) == 2:
            if pair[0] == 'session':
                return pair[1]
    return None

class session_handler:

    def __init__ (self, name, function):
        self.name = name
        self.function = function
        self.sessions = {}

    def match (self, request):
        path = request.path.split ('/')
        if (len(path) > 1) and (path[1] == self.name):
            return 1
        else:
            return 0

    def find_session (self, request):
        # XXX does http allow more than one cookie header?
        cookie = request['cookie']
        if cookie:
            sid = extract_session (cookie)
            return sid, self.sessions.get (sid, None)
        else:
            return None, None

    def gen_session_id (self):
        return str (uuid.uuid4())

    def handle_request (self, request):
        sid, fifo = self.find_session (request)
        if fifo is None:
            # login
            fifo = coro.fifo()
            fifo.push (request)
            sid = self.gen_session_id()
            request['set-cookie'] = 'session=%s' % (sid,)
            self.sessions[sid] = fifo
            coro.spawn (self.wrap, sid, fifo)
        else:
            fifo.push (request)

    def wrap (self, sid, fifo):
        try:
            self.function (sid, fifo)
        finally:
            del self.sessions[sid]
