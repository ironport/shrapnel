# -*- Mode: Python; tab-width: 4 -*-

import coro
import string
import re
import time

h_re = re.compile (r'([^: ]+): (.*)')

def get_header (header, headers):
        for h in headers:
                m = h_re.match (h)
                if m:
                        name, value = m.groups()
                        if string.lower (name) == header:
                                return value
        return None

def extract_session (cookie):
        parts = string.split (cookie, ';')
        for part in parts:
                pair = string.split (part, '=')
                if len(pair) == 2:
                        if pair[0] == 'session':
                                return pair[1]
        return None

class session_handler:

        def __init__ (self, name, function):
                self.name = name
                self.function = function
                self.sessions = {}

        def match (self, request):
                path = string.split (request._path, '/')
                if (len(path) > 1) and (path[1] == self.name):
                        return 1
                else:
                        return 0

        def get_next_request (self):
                return coro._yield()

        def find_session (self, request):
                cookie = get_header ('cookie', request._request_headers)
                if cookie:
                        sid = extract_session (cookie)
                        return sid, self.sessions.get (sid, None)
                else:
                        return None, None

        def gen_session_id (self):
                import random
                import sys
                sid = None
                while self.sessions.has_key (sid):
                        n = random.randint (0,sys.maxint-1)
                        sid = hex(n)[2:]
                return sid

        expires_delta = 100 * 86400

        def handle_request (self, request):
                sid, c = self.find_session (request)
                # The sid=='None' test is temporary hack, can probably remove it
                if (not sid) or (sid=='None'):
                        sid = self.gen_session_id()
                if c and c.isAlive():
                        # is c already running?
                        # hack, must grok this
                        coro.schedule (c, request)
                        request._done = 1
                else:
                        # login
                        c = coro.new (self.function, self, request, sid)
                        # Wdy, DD-Mon-YYYY HH:MM:SS GMT
                        expires = time.strftime ('%a, %d-%b-%Y 00:00:00 GMT', time.gmtime (int (time.time()) + self.expires_delta))
                        request['Set-Cookie'] = 'session=%s; path=/; expires=%s' % (sid, expires)
                        # hack, must grok this
                        request._done = 1
                        c.start()
