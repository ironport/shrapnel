# -*- Mode: Python -*-

import coro
from coro import read_stream

W = coro.write_stderr

# candidate for sync.pyx?
class latch:

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

    buffer_size = 8000

    def __init__ (self, headers, stream):
        self.streami = stream
        self.done_cv = latch()
        # XXX idiotic 'params' might be present
        if headers.get_one ('transfer-encoding') == 'chunked':
            self.streamo = read_stream.buffered_stream (self._gen_read_chunked().next)
        else:
            content_length = headers.get_one ('content-length')
            if content_length:
                self.content_length = int (content_length)
                self.streamo = read_stream.buffered_stream (self._gen_read_fixed().next)
            else:
                raise HTTP_Protocol_Error ("no way to determine length of HTTP data")
            
    def _gen_read_chunked (self):
        s = self.streami
        while 1:
            # XXX more idiotic params here
            chunk_size = int (s.read_line()[:-2], 16)
            if chunk_size == 0:
                self.done_cv.wake_all()
                return
            else:
                remain = chunk_size
                while remain:
                    ask = min (remain, self.buffer_size)
                    block = s.read_exact (ask)
                    assert (s.read_exact (2) == '\r\n')
                    remain -= ask
                    yield block

    def _gen_read_fixed (self):
        s = self.streami
        remain = self.content_length
        while remain:
            ask = min (remain, self.buffer_size)
            block = s.read_exact (ask)
            remain -= ask
            yield block
        self.done_cv.wake_all()
        return

    # XXX implement <size> argument
    def read (self, join=True):
        r = (x for x in self.streamo.read_all())
        if join:
            return ''.join (r)
        else:
            return r
        
    def readline (self):
        if self.done_cv.done:
            return ''
        else:
            return self.streamo.read_until ('\n')

    def wait (self):
        self.done_cv.wait()

class header_set:

    def __init__ (self, headers=()):
        self.headers = {}
        for h in headers:
            self.crack (h)

    def from_keywords (self, kwds):
        r = []
        for k, v in kwds.items():
            k = k.replace ('_', '-')
            self[k] = v
        return self

    def crack (self, h):
        try:
            i = h.index (': ')
            name, value = h[:i], h[i+2:]
            self[name] = value
        except ValueError:
            coro.write_stderr ('dropping bogus header %r\n' % (h,))
            # bogus header, drop it
            # XXX can't remember, does HTTP allow continuation lines in headers?
            pass

    def get_one (self, key):
        r = self.headers.get (key, None)
        if r is None:
            return r
        elif isinstance (r, list) and len (r) > 1:
            raise ValueError ("expected only one %s header, got %r" % (key, r))
        else:
            return r[0]

    def has_key (self, key):
        return self.headers.has_key (key.lower())

    def __getitem__ (self, key):
        return self.headers.get (key, None)

    def __setitem__ (self, name, value):
        name = name.lower()
        probe = self.headers.get (name)
        if probe is None:
            self.headers[name] = [value]
        else:
            probe.append (value)

    def __str__ (self):
        r = []
        for k, vl in self.headers.iteritems():
            for v in vl:
                r.append ('%s: %s\r\n' % (k, v))
        return ''.join (r)
