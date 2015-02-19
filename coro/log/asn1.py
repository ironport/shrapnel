
from coro.asn1.python import encode
import coro
import struct

class Logger:

    magic = '%\xf1\xbfB'

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
