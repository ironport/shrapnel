
from coro.asn1.python import encode
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

    def resync (self, fdin):
        self.state = 0
        give_up = 10000
        i = 0
        while i < give_up:
            ch = fdin.read (1)
            i += 1
            if ch == '':
                raise EOFError
            else:
                if self.feed (ch):
                    return
        raise ValueError ("unable to sync: is this an asn1 log file?")
