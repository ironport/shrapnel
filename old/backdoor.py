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

VERSION_STRING = '$Id$'

import coro

import socket
import string
import cStringIO
import sys
import traceback
import types
import os

# Originally, this object implemented the file-output api, and set
# sys.stdout and sys.stderr to 'self'.  However, if any other
# coroutine ran, it would see the captured definition of sys.stdout,
# and would send its output here, instead of the expected place.  Now
# the code captures all output using StringIO.  A little less
# flexible, a little less efficient, but much less surprising!
# [Note: this is exactly the same problem addressed by Scheme's
#  dynamic-wind facility]

class backdoor:

    def __init__ (self, socket, line_separator='\r\n', welcome_message=None, global_dict=None):
        self.socket = socket
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
            self.socket.send (data)
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
                block = self.socket.recv (8192)
                if not block:
                    return None
                elif block == '\004':
                    self.socket.close()
                    return None
                else:
                    self.buffer = self.buffer + block
                    lines = string.split (self.buffer, self.line_separator)
                    for l in lines[:-1]:
                        self.lines.append (l)
                    self.buffer = lines[-1]
            return self.read_line()

    def send_welcome_message(self):
        self.send ('Python ' + sys.version + self.line_separator)
        self.send (sys.copyright + self.line_separator)
        if self.welcome_message is not None:
            # make '\n' into the right line separator and terminate with
            # a line separator
            lines = string.split(self.welcome_message, '\n')
            if lines[-1] != '':
                lines.append('')
            self.send(string.join(lines, self.line_separator))

    def read_eval_print_loop (self):
        self.send_welcome_message()

        if self.global_dict is None:
            # this does the equivalent of 'from __main__ import *'
            env = sys.modules['__main__'].__dict__.copy()
        else:
            env = self.global_dict.copy()

        # Some of Python's special values (such as __ispkg__)
        # can cause problems when inherited from __main__.
        # To be on the safe side, we'll only include the things that we care
        # about.
        for name, value in env.items():
            if (name.startswith('__') and
                    name.endswith('__') and
                    name not in ('__builtins__',)):
                del env[name]
        env['__name__'] = '__backdoor__'

        while True:
            self.prompt()
            line = self.read_line()
            if line is None:
                break
            elif self.multilines:
                self.multilines.append(line)
                if line == '':
                    code = string.join(self.multilines, '\n')
                    self.parse(code, env)
                    # we do this after the parsing so parse() knows not to do
                    # a second round of multiline input if it really is an
                    # unexpected EOF
                    self.multilines = []
            else:
                self.parse(line, env)

    def parse(self, line, env):
        save = sys.stdout, sys.stderr
        output = cStringIO.StringIO()
        try:
            try:
                sys.stdout = sys.stderr = output
                co = compile (line, repr(self), 'eval')
                result = eval (co, env)
                if result is not None:
                    print repr(result)
                    env['_'] = result
            except SyntaxError:
                try:
                    co = compile (line, repr(self), 'exec')
                    exec co in env
                except SyntaxError as msg:
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

def serve (port=None, ip='127.0.0.1', unix_path=None, welcome_message=None, global_dict=None):
    import errno
    if unix_path:
        try:
            os.remove(unix_path)
        except OSError as why:
            if why[0] == errno.ENOENT:
                pass
            else:
                raise
        try:
            s = coro.make_socket (socket.AF_UNIX, socket.SOCK_STREAM)
            s.bind(unix_path)
        except OSError:
            coro.print_stderr('Error starting up backdoor on unix socket %s\n' % unix_path)
            raise
        coro.print_stderr('Backdoor started on unix socket %s\n' % unix_path)
    else:
        s = coro.make_socket (socket.AF_INET, socket.SOCK_STREAM)
        s.set_reuse_addr()
        if port is None:
            ports = xrange(8023, 8033)
        else:
            if isinstance(port, types.IntType):
                ports = [port]
            else:
                ports = port
        bound = 0
        for i in ports:
            try:
                s.bind ((ip, i))
                bound = 1
                break
            except (OSError, socket.error) as why:
                if why[0] != errno.EADDRINUSE:
                    raise OSError(why)
        if not bound:
            raise Exception("couldn't bind a port (try not specifying a port)")
        coro.print_stderr('Backdoor started on port %d\n' % i)
    s.listen (1024)
    while True:
        conn, addr = s.accept()
        coro.print_stderr ('incoming connection from %r\n' % (conn.getsockname(),))
        thread = coro.spawn (client, conn, addr, welcome_message, global_dict)
        thread.set_name('backdoor session')

if __name__ == '__main__':
    thread = coro.spawn (serve, welcome_message='Testing backdoor.py')
    thread.set_name('backdoor')
    coro.event_loop (30.0)
