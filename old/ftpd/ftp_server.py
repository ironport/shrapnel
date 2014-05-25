# -*- Mode: Python; tab-width: 4 -*-

#   Author: Sam Rushing <rushing@nightmare.com>
#   Copyright 1996-2000 by Sam Rushing
#                        All Rights Reserved.
#

RCS_ID = '$Id$

# An extensible, configurable, asynchronous FTP server.
#
# All socket I/O is non-blocking, however file I/O is currently
# blocking.  Eventually file I/O may be made non-blocking, too, if it
# seems necessary.  Currently the only CPU-intensive operation is
# getting and formatting a directory listing.  [this could be moved
# into another process/directory server, or another thread?]
#
# Only a subset of RFC 959 is implemented, but much of that RFC is
# vestigial anyway.  I've attempted to include the most commonly-used
# commands, using the feature set of wu-ftpd as a guide.

import coro
import crypt
import errno
import pwd
import qlog
import re
import socket
import stat
import string
import sys
import tags
import tb
import time
import read_stream

from counter import counter

# TODO: implement a directory listing cache.  On very-high-load
# servers this could save a lot of disk abuse, and possibly the
# work of computing emulated unix ls output.

# Potential security problem with the FTP protocol?  I don't think
# there's any verification of the origin of a data connection.  Not
# really a problem for the server (since it doesn't send the port
# command, except when in PASV mode) But I think a data connection
# could be spoofed by a program with access to a sniffer - it could
# watch for a PORT command to go over a command channel, and then
# connect to that port before the server does.

# Unix user id's:
# In order to support assuming the id of a particular user,
# it seems there are two options:
# 1) fork, and seteuid in the child
# 2) carefully control the effective uid around filesystem accessing
#    methods, using try/finally. [this seems to work]

class ftp_channel:

    # defaults for a reliable __repr__
    addr = ('unknown', '0')

    # unset this in a derived class in order
    # to enable the commands in 'self.write_commands'
    read_only = 1
    write_commands = ['appe', 'dele', 'mkd', 'rmd', 'rnfr', 'rnto', 'stor', 'stou']

    restart_position = 0

    # comply with (possibly troublesome) RFC959 requirements
    # This is necessary to correctly run an active data connection
    # through a firewall that triggers on the source port (expected
    # to be 'L-1', or 20 in the normal case).
    bind_local_minus_one = 0

    shutdown_flag = 0

    recv_timeout = 900
    send_timeout = 900

    # Function that can filter files from the ls commands
    # Given 1 parameter that is the name of the file
    ls_filter = None

    def __init__ (self, server, conn, addr, session_id):
        self.server = server
        self.current_mode = 'a'
        self.addr = addr
        self.conn = conn
        self.session_id = session_id
        self.thread_id = None
        # client data port.  Defaults to 'the same as the control connection'.
        self.client_addr = (addr[0], 21)
        self.in_buffer = ''
        self.closing = 0
        self.passive_acceptor = None
        self.filesystem = None
        self.authorized = 0
        self.stream = read_stream.stream_reader (self.read)
        self.user = None

    # __repr__ for app-failure logging
    def __repr__ (self):
        return (" server: %r current_mode: %s addr: %r conn: %r "
                "session_id: %r thread_id: %r closing: %r authorized: %r "
                "user: %r" % (self.server, self.current_mode, self.addr,
                              self.conn, self.session_id, self.thread_id, self.closing,
                              self.authorized, self.user))

    def read (self, size):
        return self.conn.recv (size)

    def send_file (self, s, f):
        while 1:
            # use a big block size, since this is likely to be on a fast network
            block = f.read (32768)
            if block:
                coro.with_timeout(self.send_timeout, s.send, block)
            else:
                break

    def send_with_producer (self, s, p):
        while 1:
            block = p.more()
            if block:
                coro.with_timeout (self.send_timeout, s.send, block)
            else:
                break

    def read_line_timeout (self):
        return coro.with_timeout (self.recv_timeout, self.stream.read_line)

    def send (self, data):
        return coro.with_timeout (self.send_timeout, self.conn.send, data)

    def writev (self, data):
        return coro.with_timeout (self.send_timeout, self.conn.writev, data)

    # --------------------------------------------------

    def shutdown(self, rudely=0):
        """shutdown(rudely=0) -> None
        Shuts down this session.
        Set rudely to immediately shut it down.
        """
        # TODO: Hmm...the user will just spontaneously be disconnected
        # Can we give them a disconnected error?
        self.shutdown_flag = 1
        if rudely:
            try:
                my_thread = coro.get_thread_by_id (self.thread_id)
            except KeyError:
                # thread already exited
                return
            my_thread.shutdown()

    def run (self):
        try:
            try:
                self._run()
            except coro.Shutdown:
                # We've been asked to shutdown
                return
            except:
                qlog.write('COMMON.APP_FAILURE', tb.traceback_string() + repr(self))
        finally:
            if self.user:
                qlog.write('FTPD.LOGOUT', self.session_id, self.user)
            self.close()
            self.server.session_done(self)
            # remove cycle
            del self.stream

    def get_version(self):
        return tags.version()

    def send_greeting(self):
        self.respond (
            '220 %s IronPort FTP server (V%s) ready.' % (
                self.server.hostname,
                self.get_version()
            )
        )

    def _run (self):
        self.thread_id = coro.current().thread_id()
        try:
            # send the greeting
            self.send_greeting()

            while not self.shutdown_flag:
                line, eof = self.read_line_timeout()
                if eof:
                    break
                line = orig_line = line.lstrip()

                parts = line.split()
                if len (parts) < 1:
                    self.command_not_understood ('')
                    continue
                command = parts[0].lower()
                if len(parts) > 1:
                    args = ' '.join (parts[1:])
                    # If command arguments include null character, python path parsing
                    # function will complain. Remove the null characters.
                    line = [command, args.replace('\0', '')]
                else:
                    line = [command]

                # watch especially for 'urgent' abort commands.
                if command.find ('abor') != -1:
                    # strip off telnet sync chars and the like...
                    while command and command[0] not in string.letters:
                        command = command[1:]
                fun_name = 'cmd_%s' % command
                if command != 'pass':
                    qlog.write('FTPD.RECV', self.session_id, repr(orig_line)[1:-1])
                else:
                    qlog.write('FTPD.RECV', self.session_id, line[0] + ' <password>')
                self.in_buffer = ''
                if not hasattr (self, fun_name):
                    self.command_not_understood (line[0])
                    continue
                fun = getattr (self, fun_name)
                if (not self.authorized) and (command not in ('user', 'pass', 'help', 'quit')):
                    self.respond ('530 Please log in with USER and PASS')
                elif (not self.check_command_authorization (self.user, command)):
                    self.command_not_authorized (command)
                else:
                    if hasattr (self, '_syntax_%s' % command):
                        r = getattr (self, '_syntax_%s' % command)
                        m = re.match (r, orig_line, re.IGNORECASE)
                        if m is None:
                            self.respond ('501 Syntax error in parameters or arguments')
                            continue
                    try:
                        result = apply (fun, (line,))
                    except OSError, why:
                        if why[0] in self.disconnect_errors:
                            # log it & ignore
                            qlog.write ('FTPD.DISCONNECT', self.session_id, why.strerror)
                            break
                        else:
                            raise
                    except coro.TimeoutError:
                        qlog.write('FTPD.DISCONNECT', self.session_id, 'Remote side timed out')
                        break
                    except coro.Interrupted:
                        raise
                    except:
                        self.server.total_exceptions.increment()
                        qlog.write('COMMON.APP_FAILURE', tb.traceback_string() +
                                   ' fun: ' + repr(fun) + ' line: ' + repr(line))
                        self.respond ('451 Server Error')
                        self.close_passive_acceptor()
                    else:
                        if result == 'quit':
                            break
        except read_stream.BufferOverflow:
            try:
                self.respond ('500 line too long.  good-bye')
            except coro.TimeoutError:
                pass
            except OSError:
                pass
        except coro.TimeoutError:
            try:
                self.respond ('421 timeout.  good-bye')
            except coro.TimeoutError:
                pass
            except OSError:
                pass
        except OSError, why:
            if why[0] in self.disconnect_errors:
                # log it & ignore
                qlog.write('FTPD.DISCONNECT', self.session_id, why.strerror)
            else:
                # Unknown error.  If it's something like EBADF, then there is
                # something seriously wrong.
                raise

    # the set of errors that indicate a connection problem
    disconnect_errors = (
        errno.ECONNRESET,
        errno.EHOSTUNREACH,
        errno.ECONNREFUSED,
        errno.EHOSTDOWN,
        errno.EPIPE,
        errno.ETIMEDOUT
    )

    def close_passive_acceptor (self):
        if self.passive_acceptor:
            self.passive_acceptor.close()
            self.passive_acceptor = None

    def close (self):
        self.close_passive_acceptor()
        if self.conn:
            self.conn.close()
            self.conn = None
            self.server.closed_sessions.increment()

    # --------------------------------------------------
    # filesystem interface functions.
    # override these to provide access control or perform
    # other functions.
    # --------------------------------------------------

    def cwd (self, line):
        return self.filesystem.cwd (line[1])

    def cdup (self, line):
        return self.filesystem.cdup()

    def open (self, path, mode):
        return self.filesystem.open (path, mode)

    def tmp_create(self, path, mode):
        return self.filesystem.tmp_create(path, mode)

    # returns a producer
    def listdir (self, path, long=0, ls_filter=None):
        return self.filesystem.listdir (path, long, ls_filter)

    def get_dir_list (self, line, long=0):
        # we need to scan the command line for arguments to '/bin/ls'...
        args = line[1:]
        path_args = []
        for arg in args:
            if arg[0] != '-':
                path_args.append (arg)
            else:
                # ignore arguments
                pass
        if len(path_args) < 1:
            dir = '.'
        else:
            dir = path_args[0]
        return self.listdir (dir, long, self.ls_filter)

    # --------------------------------------------------
    # authorization methods
    # --------------------------------------------------

    def check_command_authorization (self, username, command):
        try:
            return self.server.authorizer.check_command_authorization(username, command)
        except AttributeError:
            if command in self.write_commands and self.read_only:
                return 0
            else:
                return 1

    # --------------------------------------------------
    # utility methods
    # --------------------------------------------------

    def respond (self, resp):
        qlog.write('FTPD.SEND', self.session_id, resp)
        self.send (resp + '\r\n')

    def command_not_understood (self, command):
        self.respond ("500 '%s': command not understood." % command)

    def command_not_authorized (self, command):
        self.respond (
            "530 You are not authorized to perform the '%s' command" % (
                command
            )
        )

    def make_data_channel (self):
        # In PASV mode, the connection may or may _not_ have been made
        # yet.  [although in most cases it is... FTP Explorer being
        # the only exception I've yet seen].  This gets somewhat confusing
        # because things may happen in any order...
        pa = self.passive_acceptor
        if pa:
            conn, addr = pa.accept()
            self.close_passive_acceptor()
            return conn, addr
        else:
            # not in PASV mode.
            ip, port = self.client_addr
            cdc = coro.make_socket (socket.AF_INET, socket.SOCK_STREAM)
            if self.bind_local_minus_one:
                cdc.bind ((self.server.ip, self.server.port - 1))
            else:
                # using random port number
                cdc.bind ((self.server.ip, 0))
            try:
                cdc.connect (self.client_addr)
            except OSError, why:
                cdc.close()
                cdc = None
                self.respond ("425 Can't build data connection: %s" % why.strerror)
            return cdc, self.client_addr

    type_map = {
        'a': 'ASCII',
        'i': 'Binary',
        'e': 'EBCDIC',
        'l': 'Binary'
    }

    type_mode_map = {
        'a': 't',
        'i': 'b',
        'e': 'b',
        'l': 'b'
    }

    # --------------------------------------------------
    # command methods
    # --------------------------------------------------

    _help_type = 'specify data transfer type'
    _syntax_type = 'type (a|i|l)$'

    def cmd_type (self, line):
        # ascii, ebcdic, image, local <byte size>
        t = string.lower (line[1])
        # no support for EBCDIC
        # if t not in ['a','e','i','l']:
        if t not in ['a', 'i', 'l']:
            self.command_not_understood (string.join (line))
        elif t == 'l' and (len(line) > 2 and line[2] != '8'):
            self.respond ('504 Byte size must be 8')
        else:
            self.current_mode = t
            self.respond ('200 Type set to %s.' % self.type_map[t])

    _help_quit = 'terminate session'
    _syntax_quit = 'quit$'

    def cmd_quit (self, line):
        self.respond ('221 Goodbye.')
        return 'quit'

    _help_port = 'specify data connection port'
    _syntax_port = 'port ([0-9]{1,3},){5}[0-9]{1,3}$'

    def cmd_port (self, line):
        info = line[1].split (',')
        ip = '.'.join (info[:4])
        port = (int (info[4]) * 256) + int (info[5])
        # TODO: we should (optionally) verify that the
        # ip number belongs to the client.  [wu-ftpd does this?]
        self.client_addr = (ip, port)
        self.respond ('200 PORT command successful.')

    _help_pasv = 'prepare for server-to-server transfer'
    _syntax_pasv = 'pasv$'

    def cmd_pasv (self, line):
        # careful to close one that might already be there...
        self.close_passive_acceptor()
        ps = coro.make_socket (socket.AF_INET, socket.SOCK_STREAM)
        self.passive_acceptor = ps
        ps.bind ((self.conn.getsockname()[0], 0))
        ps.listen (1)
        (ip, port) = ps.getsockname()
        self.respond (
            '227 Entering Passive Mode (%s,%d,%d)' % (
                ','.join (ip.split ('.')),
                port / 256,
                port % 256
            )
        )

    _help_nlst = 'give name list of files in directory'
    _syntax_nlst = 'nlst( \S+)?'

    def cmd_nlst (self, line):
        # ncftp adds the -FC argument for the user-visible 'nlist'
        # command.  We could try to emulate ls flags, but not just yet.
        if '-FC' in line:
            line.remove ('-FC')
        try:
            dir_list_producer = self.get_dir_list (line, 0)
        except OSError, why:
            self.respond ('550 Could not list directory: %r' % why[0])
            return
        self.respond (
            '150 Opening %s mode data connection for file list' % (
                self.type_map[self.current_mode]
            )
        )
        conn, addr = self.make_data_channel()
        if conn:
            try:
                self.send_with_producer (conn, dir_list_producer)
                self.respond ('226 Transfer Complete')
            finally:
                conn.close()

    _help_list = 'give list files in a directory'
    _syntax_list = 'list( \S+)?'

    def cmd_list (self, line):
        try:
            dir_list_producer = self.get_dir_list (line, 1)
        except OSError, why:
            self.respond ('550 Could not list directory: %r' % why[0])
            return
        self.respond (
            '150 Opening %s mode data connection for file list' % (
                self.type_map[self.current_mode]
            )
        )
        conn, addr = self.make_data_channel()
        if conn:
            try:
                self.send_with_producer (conn, dir_list_producer)
                self.respond ('226 Transfer Complete')
            finally:
                conn.close()

    _help_cwd = 'change working directory'
    _syntax_cwd = 'cwd \S.*$'

    def cmd_cwd (self, line):
        if self.cwd (line):
            self.respond ('250 CWD command successful.')
        else:
            self.respond ('550 No such directory.')

    _help_cdup = 'change to parent of current working directory'
    _syntax_cdup = 'cdup$'

    def cmd_cdup (self, line):
        if self.cdup(line):
            self.respond ('250 CDUP command successful.')
        else:
            self.respond ('550 No such directory.')

    _help_pwd = 'print the current working directory'
    _syntax_pwd = 'pwd$'

    def cmd_pwd (self, line):
        self.respond (
            '257 "%s" is the current directory.' % (
                self.filesystem.current_directory()
            )
        )

    # modification time
    # example output:
    # 213 19960301204320
    _help_mdtm = 'show last modification time of file'
    _syntax_mdtm = 'mdtm \S+'

    def cmd_mdtm (self, line):
        filename = line[1]
        if not self.filesystem.isfile (filename):
            self.respond ('550 "%s" is not a file' % filename)
        else:
            mtime = time.gmtime(self.filesystem.stat(filename)[stat.ST_MTIME])
            self.respond (
                '213 %4d%02d%02d%02d%02d%02d' % (
                    mtime[0],
                    mtime[1],
                    mtime[2],
                    mtime[3],
                    mtime[4],
                    mtime[5]
                )
            )

    _help_noop = 'do nothing'
    _syntax_noop = 'noop$'

    def cmd_noop (self, line):
        self.respond ('200 NOOP command successful.')

    _help_size = 'return size of file'
    _syntax_size = 'size \S+'

    def cmd_size (self, line):
        filename = line[1]
        if not self.filesystem.isfile (filename):
            self.respond ('550 "%s" is not a file' % filename)
        else:
            self.respond (
                '213 %d' % (self.filesystem.stat(filename)[stat.ST_SIZE])
            )

    _help_retr = 'retrieve a file'
    _syntax_retr = 'retr \S+'

    def cmd_retr (self, line):
        if len(line) < 2:
            self.command_not_understood (string.join (line))
        else:
            file = line[1]
            if not self.filesystem.isfile (file):
                self.respond ('550 No such file')
            else:
                try:
                    # FIXME: for some reason, 'rt' isn't working on win95
                    mode = 'r' + self.type_mode_map[self.current_mode]
                    fd = self.open (file, mode)
                except (OSError, IOError), why:
                    self.respond ('553 could not open file for reading: %r' % why[0])
                    return
                try:
                    self.respond (
                        "150 Opening %s mode data connection for file '%s'" % (
                            self.type_map[self.current_mode],
                            file
                        )
                    )
                    conn, addr = self.make_data_channel()
                    if conn:
                        try:
                            fd.seek(0, 2)
                            filesize = fd.tell()
                            fd.seek(0, 0)
                            qlog.write('FTPD.DOWNLOAD', self.session_id, file, filesize)
                            if self.restart_position:
                                # try to position the file as requested, but
                                # give up silently on failure (the 'file object'
                                # may not support seek())
                                try:
                                    fd.seek (self.restart_position)
                                except:
                                    pass
                                self.restart_position = 0
                            try:
                                self.send_file (conn, fd)
                            except OSError, why:
                                self.respond ('451 Transfer aborted. %s' % (str(why)))
                            except coro.TimeoutError:
                                self.respond ('421 Transfer timed out.')
                            except coro.Shutdown:
                                self.respond ('451 Transfer aborted.  FTP service shutting down.')
                            else:
                                self.respond ('226 Transfer Complete')
                        finally:
                            conn.close()
                finally:
                    fd.close()

    # Whether or not to use a temporary file to make atomic updates
    # when writing over a file that already exists.
    use_atomic_store = 1

    _help_stor = 'store a file'
    _syntax_stor = 'stor \S+'

    def cmd_stor (self, line, mode='wb'):
        # don't use 'atomic store' when in 'append' mode (see cmd_appe())
        atomic_flag = self.use_atomic_store and ('a' not in mode)
        if len (line) < 2:
            self.command_not_understood (string.join (line))
            return
        if self.restart_position:
            self.restart_position = 0
            self.respond ('553 restart on STOR not yet supported')
            return
        file = line[1]
        # todo: handle that type flag
        try:
            if atomic_flag:
                tmp_filename, fd = self.tmp_create(file, mode)
            else:
                fd = self.open (file, mode)
        except (OSError, IOError), why:
            self.respond ('553 could not open file for writing: %r' % why[0])
            return
        except filesys.TempFileCreateError:
            self.respond ('553 could not open temporary file. Target may be a directory.')
            return
        try:
            self.respond (
                '150 Opening %s connection for %s' % (
                    self.type_map[self.current_mode],
                    file
                )
            )
            conn, addr = self.make_data_channel ()
            if conn:
                xfer_success = 1
                try:
                    bytes = 0
                    while 1:
                        block = coro.with_timeout (self.recv_timeout, conn.recv, 8192)
                        if block:
                            bytes += len(block)
                            try:
                                fd.write (block)
                            except (OSError, IOError), e:
                                xfer_success = 0
                                qlog.write('FTPD.UPLOAD_FAILURE',
                                           self.session_id, file, e.strerror)
                                self.respond ("452 Store failed: " + e.strerror)
                        else:
                            break
                    fd.close()
                    fd = None
                    if atomic_flag:
                        # atomic rename
                        try:
                            self.filesystem.rename (tmp_filename, file)
                        except OSError, e:
                            xfer_success = 0
                            qlog.write('FTPD.UPLOAD_FAILURE',
                                       self.session_id, file, e.strerror)
                            self.respond ("553 Store failed: " + e.strerror)
                finally:
                    conn.close()
                if xfer_success:
                    qlog.write('FTPD.UPLOAD', self.session_id, file, bytes)
                    self.respond ('226 Transfer Complete')
        finally:
            if fd:
                fd.close()
            if atomic_flag:
                try:
                    self.filesystem.unlink(tmp_filename)
                except OSError:
                    # normally ENOENT
                    pass

    _help_abor = 'abort operation'
    _syntax_abor = 'abor$'

    def cmd_abor (self, line):
        self.respond ('226 ABOR command successful.')

    _help_appe = 'append to a file'
    _syntax_appe = 'appe \S+'

    def cmd_appe (self, line):
        return self.cmd_stor (line, 'ab')

    _help_dele = 'delete file'
    _syntax_dele = 'dele \S+'

    def cmd_dele (self, line):
        if len (line) != 2:
            self.command_not_understood (string.join (line))
        else:
            file = line[1]
            if self.filesystem.isfile (file):
                try:
                    self.filesystem.unlink (file)
                    self.respond ('250 DELE command successful.')
                except OSError:
                    self.respond ('550 error deleting file.')
            else:
                self.respond ('550 %s: No such file.' % file)

    _help_mkd = 'make a directory'
    _syntax_mkd = 'mkd \S+'

    def cmd_mkd (self, line):
        if len (line) != 2:
            self.command_not_understood (string.join (line))
        else:
            path = line[1]
            try:
                self.filesystem.mkdir (path)
                self.respond ('257 MKD command successful.')
            except OSError:
                self.respond ('550 error creating directory.')

    _help_rmd = 'remove a directory'
    _syntax_rmd = 'rmd \S+'

    def cmd_rmd (self, line):
        if len (line) != 2:
            self.command_not_understood (string.join (line))
        else:
            path = line[1]
            try:
                self.filesystem.rmdir (path)
                self.respond ('250 RMD command successful.')
            except OSError:
                self.respond ('550 error removing directory.')

    _help_user = 'specify user name'
    _syntax_user = 'user \S+'

    def cmd_user (self, line):
        if len(line) > 1:
            self.user = line[1]
            self.respond ('331 Password required.')
        else:
            self.command_not_understood (string.join (line))

    _help_pass = 'specify password'
    _syntax_pass = 'pass \S+'

    def cmd_pass (self, line):
        if len(line) < 2:
            pw = ''
        else:
            pw = line[1]
        try:
            result, message, fs = self.server.authorizer.authorize (self, self.user, pw)
        except SystemError:
            result = None
            message = 'User %s access denied' % self.user

        if result:
            self.respond ('230 %s' % message)
            self.filesystem = fs
            self.authorized = 1
            qlog.write('FTPD.LOGIN', self.session_id, self.user)
        else:
            qlog.write('FTPD.LOGIN_FAILED', self.session_id, self.user)
            self.respond ('530 %s' % message)

    _help_rest = 'restart incomplete transfer'
    _syntax_rest = 'rest [0-9]+$'

    def cmd_rest (self, line):
        try:
            pos = string.atoi (line[1])
        except ValueError:
            self.command_not_understood (string.join (line))
        self.restart_position = pos
        self.respond (
            '350 Restarting at %d. Send STORE or RETRIEVE to initiate transfer.' % pos
        )

    _help_stru = 'obsolete - set file transfer structure'
    _syntax_stru = 'stru (f|r|p)$'

    def cmd_stru (self, line):
        if line[1] in ('f', 'F'):
            # f == 'file'
            self.respond ('200 STRU F Ok')
        else:
            self.respond ('504 Unimplemented STRU type')

    _help_mode = 'obsolete - set file transfer mode'
    _syntax_mode = 'mode (s|b|c)$'

    def cmd_mode (self, line):
        if line[1] in ('s', 'S'):
            # f == 'file'
            self.respond ('200 MODE S Ok')
        else:
            self.respond ('502 Unimplemented MODE type')

# The stat command has two personalities.  Normally it returns status
# information about the current connection.  But if given an argument,
# it is equivalent to the LIST command, with the data sent over the
# control connection.  Strange.  But wuftpd, ftpd, and nt's ftp server
# all support it.
#
#
#  _help_stat = 'return status of server'
# def cmd_stat (self, line):
# pass

    _help_syst = 'show operating system type of server system'
    _syntax_syst = 'syst$'

    def cmd_syst (self, line):
        # Replying to this command is of questionable utility, because
        # this server does not behave in a predictable way w.r.t. the
        # output of the LIST command.  We emulate Unix ls output, but
        # on win32 the pathname can contain drive information at the front
        # Currently, the combination of ensuring that os.sep == '/'
        # and removing the leading slash when necessary seems to work.
        # [cd'ing to another drive also works]
        #
        # This is how wuftpd responds, and is probably
        # the most expected.  The main purpose of this reply is so that
        # the client knows to expect Unix ls-style LIST output.
        self.respond ('215 UNIX Type: L8')
        # one disadvantage to this is that some client programs
        # assume they can pass args to /bin/ls.
        # a few typical responses:
        # 215 UNIX Type: L8 (wuftpd)
        # 215 Windows_NT version 3.51
        # 215 VMS MultiNet V3.3
        # 500 'SYST': command not understood. (SVR4)

    _help_help = 'give help information'
    _syntax_help = 'help( .*)?$'

    def cmd_help (self, line):
        # find all the methods that match 'cmd_xxxx',
        # use their docstrings for the help response.
        attrs = dir(ftp_channel)
        help_lines = []
        for attr in attrs:
            if attr[:6] == '_help_':
                cmd = attr.split ('_')[2]
                help_lines.append ('\t%s\t%s' % (cmd, getattr (self, attr)))
        if help_lines:
            self.writev ([
                '214-The following commands are recognized\r\n214-',
                '\r\n214-'.join (help_lines[:-1]),
                '\r\n214 ',
                help_lines[-1],
                '\r\n'
            ])
        else:
            self.send ('214      Help Unavailable\r\n')

class ftp_server:

    def __init__ (self, authorizer, channel=ftp_channel, hostname=None, ip='0.0.0.0', port=21):
        self.ip = ip
        self.port = port
        self.authorizer = authorizer
        self.channel = channel
        self.thread_id = None
        # Used to signal when all the clients have exited
        self.shutdown_cv = coro.condition_variable()
        # list of ftp_channel instances
        self.clients = []
        self.session_id = 1

        if hostname is None:
            self.hostname = socket.gethostname()
        else:
            self.hostname = hostname

        # statistics
        self.total_sessions = counter()
        self.closed_sessions = counter()
        self.total_files_out = counter()
        self.total_files_in = counter()
        self.total_bytes_out = counter()
        self.total_bytes_in = counter()
        self.total_exceptions = counter()

    def session_done(self, client):
        """session_done(client) -> None
        Indicates that the given session is done.
        Client is a ftp_channel instance.
        """
        self.clients.remove(client)
        if len(self.clients) == 0:
            self.shutdown_cv.wake_one()

    def shutdown(self, timeout):
        """shutdown(timeout) -> None
        Shuts down the server and all the children within timeout seconds.
        Rudely terminates sessions if they don't exit within timeout
        seconds.
        """
        # Shut down the main accept loop
        if self.thread_id:
            try:
                my_thread = coro.get_thread_by_id (self.thread_id)
            except KeyError:
                # thread already exited
                return
            my_thread.shutdown()
        # Shut down all the children
        if self.clients:
            for c in self.clients:
                c.shutdown()
            # wait for all the children to finish
            try:
                coro.with_timeout(timeout, self.shutdown_cv.wait)
            except coro.TimeoutError:
                # kill hard
                for c in self.clients:
                    c.shutdown(rudely=1)

    def run (self):
        try:
            self._run()
        except coro.Shutdown:
            # We've been asked to shutdown
            return

    def _run (self):
        """Listens on the FTP port accepting connections and spawning sessions."""
        self.thread_id = coro.current().thread_id()
        s = coro.make_socket (socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.set_reuse_addr()
            done = 0
            while not done:
                for x in xrange (5):
                    try:
                        was_eaddrinuse = 0
                        s.bind ((self.ip, self.port))
                    except OSError, why:
                        if why[0] == errno.EACCES:
                            coro.print_stderr(
                                'Access denied binding to %s:%i.  Are you running as root?\n' % (self.ip, self.port))
                            return
                        elif why[0] == errno.EADDRINUSE:
                            was_eaddrinuse = 1
                        elif why[0] != errno.EADDRNOTAVAIL:
                            raise
                    else:
                        done = 1
                        break
                    coro.sleep_relative (1)
                else:
                    coro.print_stderr ("cannot bind to %s:%d after 5 attempts\n" % (self.ip, self.port))
                    if was_eaddrinuse:
                        qlog.write('FTPD.PORT_IN_USE',
                                   self.ip, str(self.port))
                    coro.sleep_relative (15)
            s.listen (1024)
            while 1:
                conn_list = s.accept_many()
                for conn, addr in conn_list:
                    qlog.write('FTPD.CONNECTION', self.session_id, addr[0], self.ip)
                    session = self.channel (self, conn, addr, self.session_id)
                    self.session_id += 1
                    thread = coro.spawn (session.run)
                    thread.set_name (
                        "%s_%d" % (
                            session.__class__.__name__,
                            thread.thread_id()
                        )
                    )
                    self.clients.append(session)
        finally:
            s.close()

import filesys

# not much of a doorman! 8^)
class dummy_authorizer:
    def __init__ (self, root='/'):
        self.root = root

    def authorize (self, channel, username, password):
        channel.persona = -1, -1
        channel.read_only = 1
        return 1, 'Ok.', filesys.os_filesystem (self.root)

class anon_authorizer:
    def __init__ (self, root='/'):
        self.root = root

    def authorize (self, channel, username, password):
        if username in ('ftp', 'anonymous'):
            channel.persona = -1, -1
            channel.read_only = 1
            return 1, 'Ok.', filesys.os_filesystem (self.root)
        else:
            return 0, 'Password invalid.', None

class unix_authorizer:

    def __init__(self, root=None, wd=None):
        """unix_authorizer(root=None, wd=None) -> unix_authorizer instance
        Creates a unix authorizer instance.
        root may be a callable function.  It is given one argument, the name of the user.
        It is supposed to return the root directory for this user.  By default this is '/'.
        wd may be a callable function.  It is given one argument, the name of the user.
        It is supposed to return the working directory that the user first starts in.
        By default this is the user's home directory.
        """
        self.root = root
        self.wd = wd

    # return a trio of (success, reply_string, filesystem)
    def authorize (self, channel, username, password):
        try:
            pw_name, pw_passwd, pw_uid, pw_gid, pw_gecos, pw_dir, pw_shell = pwd.getpwnam (username)
        except (KeyError, TypeError):
            return 0, 'No such user.', None
        if pw_passwd == '*':
            raise SystemError("unable to fetch encrypted password. not running as root?")
        else:
            if crypt.crypt (password, pw_passwd) == pw_passwd:
                # XXX think about this
                # channel.read_only = 0
                # channel.read_only = 1
                if self.root:
                    root = self.root(pw_name)
                else:
                    root = '/'
                if self.wd:
                    wd = self.wd(pw_name)
                else:
                    wd = pw_dir
                fs = filesys.schizophrenic_unix_filesystem (
                    root,
                    wd,
                    persona=(pw_name, pw_uid, pw_gid)
                )
                return 1, 'Login successful.', fs
            else:
                return 0, 'Password invalid.', None

    def __repr__ (self):
        return '<standard unix authorizer>'

def test (port='8021'):
    fs = ftp_server (dummy_authorizer(), port=int(port))
    # fs = ftp_server (unix_authorizer(), port=int(port))
    qlog.disable()
    coro.spawn (fs.run)
    coro.event_loop()

if __name__ == '__main__':
    test (sys.argv[1])
