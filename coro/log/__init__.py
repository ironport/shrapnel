# -*- Mode: Python; indent-tabs-mode: nil -*-

__all__ = ['asn1']

import asn1
import coro
import time

class FileLogger:

    # ISO 8601
    time_format = '%Y-%m-%dT%H:%M:%S'

    def __init__ (self, f):
        self.f = f

    def log (self, *data):
        line = ' '.join ([repr(x) for x in data])
        self.f.write ("%s %s\n" % (time.strftime (self.time_format), line))
        self.f.flush()

class StderrLogger (FileLogger):
    def __init__ (self):
        FileLogger.__init__ (self, coro.saved_stderr)

class SysLogger:

    def __init__ (self, path='/dev/log', facility=16, level=6):
        self.sock = coro.sock (coro.AF.UNIX, coro.SOCK.DGRAM)
        self.sock.connect (path)
        self.encoded = (facility << 3) | level

    def log (self, *data):
        line = ' '.join ([repr(x) for x in data])
        self.sock.send ('<%d>%s\000' % (self.encoded, line))

class ComboLogger:

    def __init__ (self, *loggers):
        self.loggers = loggers

    def log (self, *data):
        for logger in self.loggers:
            logger.log (*data)

class Facility:

    def __init__ (self, name):
        self.name = name

    def __call__ (self, *data):
        log (self.name, *data)

    def exc (self):
        log (self.name, 'exception', coro.traceback_data())

class NoFacility:

    def __call__ (self, *data):
        log (*data)

    def exc (self):
        log ('exception', coro.traceback_data())

class StderrRedirector:

    def __init__ (self):
        self.log = Facility ('stderr')

    def write (self, data):
        self.log (data)

def redirect_stderr():
    global stderr
    stderr = StderrRedirector()
    import sys
    sys.stderr = stderr
    # obviously this needs fixing, we have to stop
    #   squirreling these away everywhere.
    coro.write_stderr = stderr.write
    coro.print_stderr = stderr.write
    coro._coro.write_stderr = stderr.write
    coro._coro.print_stderr = stderr.write

the_logger = StderrLogger()

def set_logger (logger):
    global the_logger
    the_logger = logger

def log (*data):
    the_logger.log (*data)
