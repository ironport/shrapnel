
from coro.asn1.python import encode, decode
import coro
import struct

# four bytes from os.urandom().
MAGIC = '%\xf1\xbfB'

class Logger:

    magic = MAGIC

    def __init__ (self, file):
        self.encode = encode
        self.file = file

    def log (self, *data):
        data = self.encode ((coro.now_usec, data))
        self.file.write (
            '%s%s%s' % (
                self.magic,
                struct.pack ('>I', len(data)),
                data
            )
        )
        self.file.flush()


class Sync:

    magic = MAGIC

    def __init__ (self):
        self.state = 0
        self.last = None

    def feed (self, ch):
        if ch == self.magic[self.state]:
            self.state += 1
            if self.state == 4:
                return True
            else:
                return False
        else:
            self.state = 0
            self.last = ch
            return False

    def resync (self, fdin, limit=10000):
        self.state = 0
        i = 0
        while limit == 0 or i < limit:
            ch = fdin.read (1)
            i += 1
            if ch == '':
                raise EOFError
            else:
                if self.feed (ch):
                    return i
        raise ValueError ("unable to sync: is this an asn1 log file?")

def await (f):
    magic = f.read (4)
    if not magic:
        pos0 = f.tell()
        while 1:
            coro.sleep_relative (1)
            f.seek (0, 2)
            pos1 = f.tell()
            if pos1 > pos0:
                f.seek (pos0)
                magic = f.read (4)
                if len (magic) == 4:
                    return magic
    else:
        return magic

def gen_log (f, limit=10000, follow=False):
    s = Sync()
    s.resync (f, limit)
    while 1:
        size, = struct.unpack ('>I', f.read (4))
        block = f.read (size)
        if len(block) != size:
            break
        try:
            (timestamp, info), size = decode (block)
        except Exception:
            s.resync (f, limit)
            continue
        yield size, timestamp / 1000000.0, info
        if follow:
            magic = await (f)
        else:
            magic = f.read (4)
        if not magic:
            break
        elif magic != Sync.magic:
            s.resync (f, limit)
