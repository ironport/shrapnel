# -*- Mode: Python -*-

import coro
from coro.http.handlers import file_handler

import pygments
import pygments.lexer
import pygments.lexers
import pygments.formatters
import pygments.util

from coro.log import Facility

LOG = Facility ('pygments_handler')

# unfortunately there doesn't seem to be any way to
#  stream data to the lexer, it needs the entire file
#  in a string.

class pygments_request_wrapper:

    def __init__ (self, req, lex):
        self._req = req
        self._lex = lex
        self._data = []

    def __getattr__ (self, name):
        return getattr (self._req, name)

    def push (self, data):
        self._data.append (data)

    def done (self):
        form = pygments.formatters.get_formatter_by_name ('html', full=True)
        self._req.reply_headers.set_one ('content-type', 'text/html', override=True)
        self._req.set_deflate()
        code = b''.join (self._data)
        form.format (pygments.lex (code, self._lex), self)
        self._req.done()

    def write (self, data):
        if type(data) is unicode:
            self._req.push (data.encode ('utf8'))
        else:
            self._req.push (data)

class pygments_handler:

    def __init__ (self, inner_handler):
        self.inner_handler = inner_handler

    def match (self, req):
        return self.inner_handler.match (req)

    def handle_request (self, req):
        try:
            lex = pygments.lexers.get_lexer_for_filename (req.path)
            req = pygments_request_wrapper (req, lex)
        except pygments.util.ClassNotFound:
            pass
        self.inner_handler.handle_request (req)
