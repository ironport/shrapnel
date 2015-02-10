# -*- Mode: Python; indent-tabs-mode: nil -*-

__all__ = ['asn1']

import asn1
import coro
import time

def is_binary (ob):
    if type(ob) is not bytes:
        return False
    else:
        return '\x00' in ob

def frob(ob):
    if type(ob) is bytes:
        if is_binary (ob):
            if len(ob) < 500 or args.big:
                return ob.encode ('hex')
            else:
                return '<large>'
        return ob
    else:
        return ob

class StderrLogger:

    # ISO 8601
    time_format = '%Y-%m-%dT%H:%M:%S'    

    def log (self, *data):
        data = [frob(x) for x in data]
        coro.write_stderr ("%s %r\n" % (time.strftime (self.time_format), data))

class ComboLogger:

    def __init__ (self, *loggers):
        self.loggers = loggers

    def log (self, *data):
        for logger in self.loggers:
            logger.log (*data)

