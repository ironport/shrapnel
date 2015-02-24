# -*- Mode: Python -*-

# Copyright 1999, 2000 by eGroups, Inc.
#
#                         All Rights Reserved
#
# Permission to use, copy, modify, and distribute this software and
# its documentation for any purpose and without fee is hereby
# granted, provided that the above copyright notice appear in all
# copies and that both that copyright notice and this permission
# notice appear in supporting documentation, and that the name of
# eGroups not be used in advertising or publicity pertaining to
# distribution of the software without specific, written prior
# permission.
#
# EGROUPS DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE,
# INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS, IN
# NO EVENT SHALL EGROUPS BE LIABLE FOR ANY SPECIAL, INDIRECT OR
# CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
# OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
# NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
# CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

"""Backdoor Python access.

This module implements a server that allows one to telnet to a socket and get a
Python prompt in a process.

Simply spawn a thread running the `serve` function to start a backdoor server.
"""

VERSION_STRING = '$Id: //prod/main/ap/shrapnel/coro/backdoor.py#6 $'

import coro
import cStringIO
import fcntl
import sys
import traceback
import os

from coro.log import Facility
LOG = Facility ('backdoor')

# Originally, this object implemented the file-output api, and set
# sys.stdout and sys.stderr to 'self'.  However, if any other
# coroutine ran, it would see the captured definition of sys.stdout,
# and would send its output here, instead of the expected place.  Now
# the code captures all output using StringIO.  A little less
# flexible, a little less efficient, but much less surprising!
# [Note: this is exactly the same problem addressed by Scheme's
#  dynamic-wind facility]

class backdoor:

    def __init__ (self, sock, line_separator='\r\n', welcome_message=None, global_dict=None):
        self.sock = sock
        self.buffer = ''
        self.lines = []
        self.multilines = []
        self.line_separator = line_separator
        self.welcome_message = welcome_message
        self.global_dict = global_dict

        # allow the user to change the prompts:
        if 'ps1' not in sys.__dict__:
            sys.ps1 = '>>> '
        if 'ps2' not in sys.__dict__:
            sys.ps2 = '... '

    def send (self, data):
        try:
            self.sock.send (data)
        except:
            pass

    def prompt (self):
        if self.multilines:
            self.send (sys.ps2)
        else:
            self.send (sys.ps1)

    def read_line (self):
        if self.lines:
            l = self.lines[0]
            self.lines = self.lines[1:]
            return l
        else:
            while not self.lines:
                block = self.sock.recv (8100)
                if not block:
                    return None
                elif block == '\004':
                    self.sock.close()
                    return None
                else:
                    self.buffer += block
                    lines = self.buffer.split (self.line_separator)
                    for l in lines[:-1]:
                        self.lines.append (l)
                    self.buffer = lines[-1]
            return self.read_line()

    def send_welcome_message(self):
        self.send ('Python ' + sys.version.replace ('\n', '\r\n') + self.line_separator)
        self.send (sys.copyright.replace ('\n', '\r\n') + self.line_separator)
        if self.welcome_message is not None:
            # make '\n' into the right line separator and terminate with
            # a line separator
            lines = self.welcome_message.split ('\n')
            if lines[-1] != '':
                lines.append('')
            self.send (self.line_separator.join (lines))

    def login (self):
        "override to provide authentication"
        pass

    def read_eval_print_loop (self):
        self.login()
        self.send_welcome_message()
        if self.global_dict is None:
            # this does the equivalent of 'from __main__ import *'
            env = sys.modules['__main__'].__dict__.copy()
        else:
            env = self.global_dict.copy()

        while 1:
            self.prompt()
            try:
                line = self.read_line()
            except EOFError:
                break
            if line is None:
                break
            elif self.multilines:
                self.multilines.append(line)
                if line == '':
                    code = '\n'.join (self.multilines)
                    self.parse(code, env)
                    # we do this after the parsing so parse() knows not to do
                    # a second round of multiline input if it really is an
                    # unexpected EOF
                    self.multilines = []
            else:
                self.parse(line, env)

    def print_result (self, result):
        "override to process the result (e.g., pprint)"
        print result

    def parse (self, line, env):
        save = sys.stdout, sys.stderr
        output = cStringIO.StringIO()
        try:
            try:
                sys.stdout = sys.stderr = output
                co = compile (line, repr(self), 'eval')
                result = eval (co, env)
                if result is not None:
                    self.print_result (result)
                    env['_'] = result
            except SyntaxError:
                try:
                    co = compile (line, repr(self), 'exec')
                    exec co in env
                except SyntaxError, msg:
                    # this is a hack, but it is a righteous hack:
                    if not self.multilines and msg[0] == 'unexpected EOF while parsing':
                        self.multilines.append(line)
                    else:
                        traceback.print_exc()
                except:
                    traceback.print_exc()
            except:
                traceback.print_exc()
        finally:
            sys.stdout, sys.stderr = save
            self.send (output.getvalue())
            del output

def client (conn, addr, welcome_message=None, global_dict=None):
    b = backdoor (conn, welcome_message=welcome_message, global_dict=global_dict)
    b.read_eval_print_loop()

def serve (port=None, ip='', unix_path=None, welcome_message=None, global_dict=None, client_class=None):
    """Backdoor server function.

    This function will listen on the backdoor socket and spawn new threads for
    each connection.

    :Parameters:
        - `port`: The IPv4 port to listen on (defaults to automatically choose
          an unused port between 8023->8033).  May also be a list of ports.
        - `ip`: The IP to listen on.  Defaults to all IP's.
        - `unix_path`: The unix path to listen on.  If this is specified, then
          it will use unix-domain sockets, otherwise it will use IPv4 sockets.
        - `welcome_message`: A welcome message to display when a user logs in.
        - `global_dict`: The global dictionary to use for client sessions.
    """
    import errno
    if unix_path:
        try:
            os.remove (unix_path)
        except OSError, why:
            if why[0] == errno.ENOENT:
                pass
            else:
                raise
        s = coro.make_socket (coro.PF.LOCAL, coro.SOCK.STREAM)
        s.bind (unix_path)
        LOG ('started', unix_path)
    else:
        s = coro.make_socket (coro.PF.INET, coro.SOCK.STREAM)
        s.set_reuse_addr()
        if port is None:
            ports = xrange(8023, 8033)
        else:
            if type(port) is int:
                ports = [port]
            else:
                ports = port
        for i in ports:
            try:
                s.bind ((ip, i))
                LOG ('started', (ip, i))
                break
            except OSError, why:
                if why[0] != errno.EADDRINUSE:
                    raise OSError(why)
        else:
            raise Exception("couldn't bind a port (try not specifying a port)")

    if client_class is None:
        client_class = client

    flags = fcntl.fcntl(s.fileno(), fcntl.F_GETFD)
    fcntl.fcntl(s.fileno(), fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)

    s.listen (1024)
    while 1:
        conn, addr = s.accept()
        LOG ('incoming backdoor connection from %r' % (conn.getpeername(),))
        thread = coro.spawn (client_class, conn, addr, welcome_message, global_dict)
        thread.set_name('backdoor session')

import coro.ssh.transport.server
import coro.ssh.connection.connect
import coro.ssh.l4_transport.coro_socket_transport
import coro.ssh.auth.userauth
import coro.ssh.connection.interactive_session

class ssh_repl (coro.ssh.connection.interactive_session.Interactive_Session_Server):

    def __init__ (self, connection_service):
        coro.ssh.connection.interactive_session.Interactive_Session_Server.__init__ (self, connection_service)
        coro.spawn (self.go)

    def go (self):
        b = backdoor (self, line_separator='\n')
        # this is to avoid getting the banner/copyright/etc mixed in with ssh client pty/x11 warnings
        coro.sleep_relative (0.1)
        b.read_eval_print_loop()
        self.close()
        LOG ('closed', self.transport.transport.peer)

# see coro/ssh/demo/backdoor.py for instructions on setting up an ssh backdoor server.
class ssh_server:
    def __init__ (self, port, addr, server_key, authenticators):
        self.port = port
        self.addr = addr
        self.server_key = server_key
        self.authenticators = authenticators
        coro.spawn (self.serve)

    def serve (self):
        serve (self.port, self.addr, client_class=self.new_connection)

    def new_connection (self, conn, addr, welcome_message, global_dict):
        # debug = coro.ssh.util.debug.Debug()
        # debug.level = coro.ssh.util.debug.DEBUG_3
        transport = coro.ssh.l4_transport.coro_socket_transport.coro_socket_transport(sock=conn)
        server = coro.ssh.transport.server.SSH_Server_Transport (self.server_key)  # , debug=debug)
        authenticator = coro.ssh.auth.userauth.Authenticator (server, self.authenticators)
        server.connect (transport, authenticator)
        service = coro.ssh.connection.connect.Connection_Service (server, ssh_repl)

if __name__ == '__main__':
    thread = coro.spawn (serve, welcome_message='Testing backdoor.py')
    thread.set_name('backdoor server')
    coro.event_loop (30.0)
