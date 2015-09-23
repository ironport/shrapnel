# -*- Mode: Python -*-

static_table = [
    (None, None),
    (':authority', None),
    (':method', 'GET'),
    (':method', 'POST'),
    (':path', '/'),
    (':path', '/index.html'),
    (':scheme', 'http'),
    (':scheme', 'https'),
    (':status', '200'),
    (':status', '204'),
    (':status', '206'),
    (':status', '304'),
    (':status', '400'),
    (':status', '404'),
    (':status', '500'),
    ('accept-charset', None),
    ('accept-encoding', 'gzip, deflate'),
    ('accept-language', None),
    ('accept-ranges', None),
    ('accept', None),
    ('access-control-allow-origin', None),
    ('age', None),
    ('allow', None),
    ('authorization', None),
    ('cache-control', None),
    ('content-disposition', None),
    ('content-encoding', None),
    ('content-language', None),
    ('content-length', None),
    ('content-location', None),
    ('content-range', None),
    ('content-type', None),
    ('cookie', None),
    ('date', None),
    ('etag', None),
    ('expect', None),
    ('expires', None),
    ('from', None),
    ('host', None),
    ('if-match', None),
    ('if-modified-since', None),
    ('if-none-match', None),
    ('if-range', None),
    ('if-unmodified-since', None),
    ('last-modified', None),
    ('link', None),
    ('location', None),
    ('max-forwards', None),
    ('proxy-authenticate', None),
    ('proxy-authorization', None),
    ('range', None),
    ('referer', None),
    ('refresh', None),
    ('retry-after', None),
    ('server', None),
    ('set-cookie', None),
    ('strict-transport-security', None),
    ('transfer-encoding', None),
    ('user-agent', None),
    ('vary', None),
    ('via', None),
    ('www-authenticate', None),
]

nstatic = len(static_table)

static_map = {}
for i, key in enumerate (static_table):
    static_map[key] = i

# convert from ascii to a binary tree.
#   each leaf is a character.
def from_ascii (s, pos=0):
    if s[pos] == '.':
        pos += 1
        l, pos = from_ascii (s, pos)
        r, pos = from_ascii (s, pos)
        return [l, r], pos
    elif s[pos] == 'Z':
        return 256, pos + 1
    else:
        return int (s[pos:pos+2], 16), pos + 2

# source: see huffman.py
huffman_table, _ = from_ascii (
    '.....3031.3261..6365.696f...7374..2025.2d2e...2f33.3435..3637.3839.....3d41.5f62'
    '..6466.6768...6c6d.6e70..7275..3a42.4344.....4546.4748..494a.4b4c...4d4e.4f50..'
    '5152.5354....5556.5759..6a6b.7176...7778.797a...262a.2c3b..585a...2122.2829..3f.'
    '272b..7c.233e...0024.405b..5d7e..5e7d..3c60.7b....5cc3.d0.8082...83a2.b8c2..e0e2'
    '..99a1.a7ac.....b0b1.b3d1..d8d9.e3e5...e6.8184..8586.8892...9a9c.a0a3..a4a9.aaad'
    '.....b2b5.b9ba..bbbd.bec4...c6e4.e8e9...0187.898a..8b8c.8d8f.....9395.9697..989b'
    '.9d9e...a5a6.a8ae..afb4.b6b7....bcbf.c5e7..ef.098e..9091.949f....abce.d7e1..eced'
    '..c7cf.eaeb.....c0c1.c8c9..cacd.d2d5...dadb.eef0..f2f3.ff.cbcc.....d3d4.d6dd..de'
    'df.f1f4...f5f6.f7f8..fafb.fcfd....fe.0203..0405.0607...080b.0c0e..0f10.1112....1'
    '314.1517..1819.1a1b...1c1d.1e1f..7fdc.f9..0a0d.16Z'
)

# build a map from byte -> (num, bits)
#  e.g. huffman_map[ord('A')] = (33, 6)
def make_huffman_map (t):
    m = {}
    def loop (t, n, bits):
        if isinstance (t, int):
            m[t] = (n, bits)
        else:
            loop (t[0], n << 1 | 0, bits + 1)
            loop (t[1], n << 1 | 1, bits + 1)
    loop (t, 0, 0)
    return m

huffman_map = make_huffman_map (huffman_table)

masks = {i : (1<<i)-1 for i in (1,2,3,4,5,6,7)}

class HuffmanEncoder:

    def __init__ (self):
        self.data = []
        self.left = 8
        self.byte = 0

    def emit_byte (self):
        self.data.append (chr (self.byte))
        self.left = 8
        self.byte = 0

    def emit (self, n, bits):
        while bits:
            slice = min (self.left, bits)
            shift = bits - slice
            self.byte <<= slice
            self.byte |= n >> shift & masks[slice]
            bits -= slice
            self.left -= slice
            if self.left == 0:
                self.emit_byte()

    def encode (self, s):
        for ch in s:
            code, bits = huffman_map[ord(ch)]
            self.emit (code, bits)

    def done (self):
        if self.left < 8:
            self.emit (0xffffffff, self.left)
        return ''.join (self.data)

def huffman_encode (s):
    h = HuffmanEncoder()
    h.encode (s)
    return h.done()

class DynamicTable:

    def __init__ (self, max_size=1024):
        self.table = []
        self.size = 0
        self.max_size = max_size

    def __getitem__ (self, index):
        if index < nstatic:
            return static_table[index]
        else:
            return self.table[index-nstatic]

    def entry_size (self, name, val):
        return len(name) + len(val) + 32

    def evict_one (self):
        (k, v) = self.table.pop()
        self.size -= self.entry_size (k, v)
        print 'evicted', k, v, self.size

    def __setitem__ (self, name, val):
        es = self.entry_size (name, val)
        while self.size + es > self.max_size:
            self.evict_one()
        self.table.insert (0, (name, val))
        self.size += es

    def set_size (self, size):
        self.max_size = size
        while self.size > self.max_size:
            self.evict_one()

class Decoder:

    def __init__ (self, table=None):
        self.data = ''
        self.pos = 0
        # used when pulling off huffman-encoded bits.
        self.bpos = 0
        if table is None:
            table = DynamicTable()
        self.dyn = table

    def feed (self, data):
        self.data = data
        self.pos = 0

    @property
    def done (self):
        return self.pos >= len(self.data)

    @property
    def byte (self):
        return ord(self.data[self.pos])

    def next_byte (self):
        self.pos += 1
        self.bpos = 7

    def get_bytes (self, n):
        result = self.data[self.pos:self.pos+n]
        self.pos += n
        assert (len(result) == n)
        return result

    def get_integer (self, nbits):
        # fetch an integer from the lower <nbits> of
        #   the current byte.
        mask = masks[nbits]
        r = self.byte & mask
        if r == mask:
            # more octets
            r = 0
            while 1:
                self.next_byte()
                r <<= 7
                r |= self.byte & 0x7f
                if not self.byte & 0x80:
                    break
            self.next_byte()
            return r + mask
        else:
            self.next_byte()
            return r

    def get_bit (self):
        r = (self.byte & (1 << self.bpos)) != 0
        self.bpos -= 1
        if self.bpos < 0:
            self.next_byte()
        return r

    def get_pair0 (self, index):
        if index == 0:
            name = self.get_literal()
        else:
            name = self.dyn[index][0]
        val  = self.get_literal()
        return name, val

    def get_header (self):
        if self.byte >> 7 == 0x1:
            # index name and value
            index = self.get_integer (7)
            assert index != 0
            return self.dyn[index]
        elif self.byte >> 6 == 0b01:
            # literal with incremental indexing.
            index = self.get_integer (6)
            name, val = self.get_pair0 (index)
            self.dyn[name] = val
            return name, val
        elif self.byte >> 4 in (0b0000, 0b0001):
            never = self.byte >> 4 & 0b0001
            # literal without indexing
            index = self.get_integer (4)
            name, val = self.get_pair0 (index)
            return name, val
        elif self.byte >> 5 == 0b001:
            self.dyn.set_size (self.get_integer (5))

    def get_literal (self):
        is_huffman = self.byte & 0b10000000
        lit_len = self.get_integer (7)
        if is_huffman:
            return self.get_huffman (lit_len)
        else:
            return self.get_bytes (lit_len)

    def get_huffman (self, nbytes):
        r = []
        stop = self.pos + nbytes
        while 1:
            t = huffman_table
            while 1:
                b = self.get_bit()
                t = t[b]
                if isinstance (t, int):
                    r.append (chr (t))
                    break
                if self.pos == stop:
                    return ''.join (r)
        return ''.join (r)

class Encoder:

    def __init__ (self, table=None):
        # not used yet.
        if table is None:
            table = DynamicTable()
        self.table = table
        self.data = []

    def emit (self, b):
        self.data.append (chr(b))

    def emit_integer (self, n0, n1_bits, n1):
        mask = masks[n1_bits]
        if n1 < mask:
            self.emit ((n0 << n1_bits) | n1)
        else:
            self.emit ((n0 << n1_bits) | mask)
            n1 -= mask
            # encode remaining bits 7 at a time...
            while n1 >= 0b10000000:
                self.emit ((n1 & 0b01111111) | 0b10000000)
                n1 >>= 7
            # and any leftover (or 0).
            self.emit (n1)

    def emit_literal (self, s):
        s0 = huffman_encode (s)
        if len(s0) > len(s):
            # oops, not huffman-friendly
            self.emit_integer (0b0, 7, len(s))
            self.data.append (s)
        else:
            self.emit_integer (0b1, 7, len(s0))
            self.data.append (s0)

    def emit_header (self, name, val):
        index = static_map.get ((name, val), None)
        if index is not None:
            # index name and value
            self.emit_integer (1, 7, index)
        else:
            index = static_map.get ((name, None), None)
            # XXX no dyntable yet
            index = None
            if index is not None:
                # index name, literal value
                self.emit_integer (0b0000, 4, index)
                self.emit_literal (val)
            else:
                # literal name, literal value
                self.emit_integer (0b0000, 4, 0)
                self.emit_literal (name)
                self.emit_literal (val)

    def __call__ (self, hset):
        self.data = []
        # rfc7540 8.1.2.1 Pseudo-Header Fields requires that
        #   pseudo-headers precede normal headers.
        pseudo = []
        normal = []
        for name, vals in hset:
            if name.startswith (':'):
                pseudo.append ((name, vals))
            else:
                normal.append ((name, vals))
        items = pseudo + normal
        for name, vals in items:
            for val in vals:
                self.emit_header (name, val)
        return ''.join (self.data)
