# -*- Mode: Python -*-

"""
Expose a ``pdb`` session via a socket.


Usage:

  1) place a call to ``set_trace`` (from this module) in your code.
  2) spawn this server (i.e., call ``coro.spawn (coro.debug.serve)``)
  3) run your code
  4) when ready to debug, ``telnet /tmp/debug.sock`` (bsd) or ``nc -CU /tmp/debug.sock`` (linux)

Only one session at a time is supported.  The first time set_trace() is called it will associate
with that connection.  When you're done debugging, use the 'quit' command to close the session
and the socket.  You may connect repeatedly to trigger new debugging sessions.

"""

import os
import coro
from coro.log import Facility
LOG = Facility ('debugger')
from coro.read_stream import sock_stream

import pdb
import cmd

def set_trace():
    import sys
    if dbg_conn is not None and not dbg_conn.busy:
        dbg_conn.busy = True
        dbg_conn.pdb.set_trace (sys._getframe().f_back)

# modifies the 'quit' command to do a 'continue', but to close the
#  debugging session.

class PdbWithQuit (pdb.Pdb):

    def __init__ (self, client, *args, **kwargs):
        pdb.Pdb.__init__ (self, *args, **kwargs)
        self.client = client

    def do_cont (self, *args, **kwargs):
        self.client.busy = False
        return pdb.Pdb.do_cont (self, *args, **kwargs)

    def do_quit (self, *args, **kwargs):
        self.set_continue()
        self.client.close()
        return 1

class Client:

    def __init__ (self, conn):
        self.conn = conn
        self.peer = self.conn.getpeername()
        self.stream = sock_stream (conn)
        self.busy = False
        self.write ("waiting for set_trace()...\r\n")
        self.pdb = PdbWithQuit (self, stdin=self, stdout=self)
        LOG ('open', self.peer)

    def flush (self):
        pass

    def write (self, data):
        self.conn.write (data)

    def readline (self):
        return self.stream.read_line()

    def close (self):
        global dbg_conn
        self.conn.close()
        dbg_conn = None
        LOG ('close', self.peer)

dbg_conn = None

def serve (address='/tmp/debug.sock', global_dict=None):
    "serve a debugging console.  address := a string (for a unix socket) or an (ip, port) pair."
    import errno
    global dbg_conn
    if isinstance(address, basestring):
        try:
            os.remove (address)
        except OSError as why:
            if why.errno == errno.ENOENT:
                pass
            else:
                raise
        s = coro.make_socket (coro.PF.LOCAL, coro.SOCK.STREAM)
    else:
        ip, port = address
        s = coro.make_socket (coro.PF.INET, coro.SOCK.STREAM)
        s.set_reuse_addr()

    s.bind (address)
    LOG ('started', address)
    s.listen (10)

    while 1:
        conn, addr = s.accept()
        LOG ('open', conn.getpeername())
        dbg_conn = Client (conn)


if __name__ == '__main__':
    def thingy (i):
        n = 0
        while 1:
            coro.sleep_relative (5)
            LOG ('thingy loop', i, n)
            if i == 1:
                set_trace()
            n += 1
    coro.spawn (serve)
    coro.spawn (thingy, 1)
    coro.spawn (thingy, 2)
    coro.event_loop()
