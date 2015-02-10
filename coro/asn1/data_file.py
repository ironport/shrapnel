# -*- Mode: Python; indent-tabs-mode: nil -*-

from .python import encode, decode
from .ber import InsufficientData

class DataFileReader:

    def __init__ (self, f, buffer_size=1024 * 1024):
        self.f = f
        self.buffer_size = buffer_size
        self.buffer = self.f.read (self.buffer_size)
        self.pos = 0

    def read_object (self):
        while 1:
            try:
                ob, pos1 = decode (self.buffer, self.pos)
                self.pos = pos1
                return ob
            except InsufficientData:
                chunk = self.f.read (self.buffer_size)
                if len(chunk) == 0:
                    raise EOFError
                else:
                    self.buffer = self.buffer[self.pos:] + chunk
                    self.pos = 0

class DataFileWriter:

    def __init__ (self, f):
        self.f = f

    def write_object (self, data):
        self.f.write (encode (data))
