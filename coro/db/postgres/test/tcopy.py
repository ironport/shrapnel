# -*- Mode: Python -*-

import coro
import coro.db.postgres as PG
import struct
W = coro.write_stderr

# postgres implements the COPY FROM STDIN command inside the protocol,
#  if you emit a COPY command (via SQL), it will put the connection into
#  copyin mode.  Feed it the exact same data you would have from a file,
#  and you have a much faster way of populating a database.

class writer:
    def __init__ (self, forms, fout, chunk_size=16000):
        self.forms = forms
        self.fout = fout
        self.buffer = []
        self.size = 0
        self.chunk_size = chunk_size
        self.append ('PGCOPY\n\xff\r\n\x00')
        self.append (struct.pack ('>L', 0)) # flags
        self.append (struct.pack ('>L', 0)) # ext len
        self.count = 0

    def append (self, data):
        self.buffer.append (data)
        self.size += len (data)
        if self.size > self.chunk_size:
            self.flush()

    def flush (self):
        block, self.buffer = self.buffer, []
        self.size = 0
        block = ''.join (block)
        self.fout (block)

    def write_row (self, row):
        row_data = [struct.pack ('>h', len(row))]
        for i in range (len (self.forms)):
            if row[i] is None:
                row_data.append (struct.pack ('>l', -1))
            else:
                data = struct.pack ('>%s' % (self.forms[i],), row[i])
                row_data.append (struct.pack ('>l', len(data)))
                row_data.append (data)
        self.count += 1
        self.append (''.join (row_data,))
        
    def done (self):
        self.append (struct.pack ('>h', -1))
        self.flush()

def t0():
    db = PG.postgres_client ('t0', 'foo', 'bar')
    db.connect()
    try:
        db.Q ('drop table squares;')
    except PG.QueryError:
        pass
    db.Q ('create table squares (n int, n2 int);')
    db.query ('copy squares from stdin binary;')
    w = writer (('i', 'i'), db.putline)
    for i in range (1000):
        w.write_row ([i, i*i])
    w.done()
    db.endcopy()

coro.spawn (t0)
coro.event_loop()
