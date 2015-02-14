# -*- Mode: Python; indent-tabs-mode: nil -*-

__all__ = ['asn1']

import asn1
import coro
import time

class StderrLogger:

    def __init__ (self):
        import sys
        self.saved_stderr = sys.stderr

    # ISO 8601
    time_format = '%Y-%m-%dT%H:%M:%S'    

    def log (self, *data):
        self.saved_stderr.write ("%s %r\n" % (time.strftime (self.time_format), data))

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
    coro.write_stderr = stderr.write
    coro.print_stderr = stderr.write

the_logger = StderrLogger()

def set_logger (logger):
    global the_logger
    the_logger = logger

def log (*data):
    the_logger.log (*data)

