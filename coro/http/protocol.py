# -*- Mode: Python -*-

import coro
from coro import read_stream

W = coro.write_stderr

class HTTP_Protocol_Error (Exception):
    pass

class HTTP_Upgrade (Exception):
    "indicates a connection has left the HTTP universe"
    pass

# candidate for sync.pyx?
class latch:

    "Like a CV, except without the race - if the event has already fired then wait() will return immediately."

    def __init__ (self):
        self.cv = coro.condition_variable()
        self.done = False

    def wake_all (self, args=()):
        self.done = True
        self.args = args
        return self.cv.wake_all (args)

    def wait (self):
        if not self.done:
            return self.cv.wait()
        else:
            return self.args

class http_file:

    "HTTP message content, as a file-like object."

    buffer_size = 8000

    def __init__ (self, headers, stream):
        self.streami = stream
        self.done_cv = latch()
        if headers.get_one ('transfer-encoding') == 'chunked':
            self.streamo = read_stream.buffered_stream (self._gen_read_chunked().next)
        else:
            content_length = headers.get_one ('content-length')
            if content_length:
                self.content_length = int (content_length)
                self.streamo = read_stream.buffered_stream (self._gen_read_fixed().next)
            elif headers.test ('connection', 'close'):
                self.streamo = read_stream.buffered_stream (self._gen_read_all().next)
            else:
                raise HTTP_Protocol_Error ("no way to determine length of HTTP data")

    def _gen_read_chunked (self):
        "generator: decodes chunked transfer-encoding."
        s = self.streami
        while 1:
            chunk_size = int (s.read_line()[:-2], 16)
            if chunk_size == 0:
                assert (s.read_exact (2) == '\r\n')
                self.done_cv.wake_all()
                return
            else:
                remain = chunk_size
                while remain:
                    ask = min (remain, self.buffer_size)
                    yield s.read_exact (ask)
                    remain -= ask
                assert (s.read_exact (2) == '\r\n')

    def _gen_read_fixed (self):
        "generate fixed-size blocks of content."
        s = self.streami
        remain = self.content_length
        while remain:
            ask = min (remain, self.buffer_size)
            block = s.read_exact (ask)
            remain -= ask
            yield block
        self.done_cv.wake_all()
        return

    def _gen_read_all (self):
        "generate content from all remaining data from socket"
        s = self.streami
        while 1:
            block = s.read_exact (self.buffer_size)
            if not block:
                self.done_cv.wake_all()
                return
            else:
                yield block

    def read (self, size=0, join=True):
        "read from the file.  join=False returns a generator, join=True returns a string."
        if size == 0:
            r = (x for x in self.streamo.read_all())
            if join:
                return ''.join (r)
            else:
                return r
        else:
            # ignore join argument
            return self.streamo.read_exact (size)

    def readline (self):
        "read a newline-delimited line."
        if self.done_cv.done:
            return ''
        else:
            return self.streamo.read_until ('\n')

    def wait (self):
        "wait until all the content has been read."
        self.done_cv.wait()

    def abort (self, info='aborted'):
        self.done_cv.wake_all (info)

class header_set:

    def __init__ (self, headers=()):
        self.headers = {}
        for h in headers:
            self.crack (h)

    def from_keywords (self, kwds):
        """Populate this header set from a dictionary of keyword arguments
           (e.g., 'content_length' becomes 'content-length')"""
        r = []
        for k, v in kwds.items():
            k = k.replace ('_', '-')
            self[k] = v
        return self

    def crack (self, h):
        "Crack one header line."
        # deliberately ignoring 822 crap like continuation lines.
        try:
            i = h.index (': ')
            name, value = h[:i], h[i + 2:]
            self[name] = value
        except ValueError:
            coro.write_stderr ('dropping bogus header %r\n' % (h,))
            pass

    def get_one (self, key):
        """Get the value of a header expected to have at most one value.
           If not present, return None.  If more than one, raise ValueError."""
        r = self.headers.get (key, None)
        if r is None:
            return r
        elif isinstance (r, list) and len (r) > 1:
            raise ValueError ("expected only one %s header, got %r" % (key, r))
        else:
            return r[0]

    def has_key (self, key):
        "Is this header present?"
        return self.headers.has_key (key.lower())

    def test (self, key, value):
        "Is this header present with this value?"
        for x in self.headers.get (key.lower(), []):
            if x == value:
                return True
        else:
            return False

    def __getitem__ (self, key):
        "Returns the list of values for this header, or None."
        return self.headers.get (key, None)

    def __setitem__ (self, name, value):
        "Add a value to the header <name>."
        name = name.lower()
        probe = self.headers.get (name)
        if probe is None:
            self.headers[name] = [value]
        else:
            probe.append (value)

    def __delitem__ (self, name):
        "Remove a header."
        del self.headers[name]

    def remove (self, name):
        "remove a header [if present]"
        if self.headers.has_key (name):
            del self.headers[name]

    def __str__ (self):
        "Render the set of headers."
        r = []
        for k, vl in self.headers.iteritems():
            for v in vl:
                r.append ('%s: %s\r\n' % (k, v))
        return ''.join (r)

    def copy (self):
        "Return a copy of this header set"
        h = header_set()
        h.headers = self.headers.copy()
        return h
