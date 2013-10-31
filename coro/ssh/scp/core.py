# Copyright (c) 2002-2012 IronPort Systems and Cisco Systems
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Core SCP code.

This implements the core code of the SCP program.
"""

import glob
import os
import stat
import sys
import time

DEBUG_NORMAL = 1
DEBUG_EXTRA  = 2
DEBUG_FULL   = 3

class RootEscapeError(Exception):

    """Raised when a user tries to access files outside of the root directory."""


class SCP:

    """Core SCP implementation.

    This implements the core transfer functions for SCP.  It does not involve
    any of the SSH code, so it is more similar to RCP.

    :IVariables:
        - `output`: A file-like object for sending data.
        - `input`: A file-like object for receiving data.
        - `verbosity`: Level of verbosity.
        - `had_errors`: Flag to keep track if there were any errors.
        - `blocksize`: Size of blocks to read and write.
        - `path_filter`: A function to filter pathnames to determine whether or
          not they are accessible.  It should take one parameter, the full
          pathname, and return True if it is ok, otherwise False. May be None
          to indicate no filter.
        - `filter_recursive_only`: If True, will only apply the filter for
          recursive sends.  The filter is always appled for receiving.
        - `root`: The root of the filesystem.  By setting this, you can
          transparently reset the root (similar to chroot).  Setting this will
          implicitly change the current working directory to this directory.
          May be None to indicate normal operation.
        - `root_slash`: Same as ``root`` with a trailing slash.
        - `shell_globbing`: If true, will do shell-style globbing on the file
          arguments when sending files.
    """

    output = None
    input = None
    had_errors = False
    verbosity = 0
    blocksize = 4096
    max_line_size = 4096
    root = None
    root_slash = None

    def __init__(self, input=None,
                       output=None,
                       path_filter=None,
                       filter_recursive_only=False,
                       root=None,
                       shell_globbing=False
                ):
        if input:
            self.input = input
        else:
            self.input = sys.stdin
        if output:
            self.output = output
        else:
            self.output = sys.stdout
        self.path_filter = path_filter
        # Make sure there are no trailing slashes.
        if root:
            self.root = root.rstrip('/')
            self.root_slash = root + '/'
        self.filter_recursive_only = filter_recursive_only
        self.shell_globbing = shell_globbing

    def _get_relative_root(self, path):
        if self.root:
            if path.startswith('/'):
                path = path.lstrip('/')
            path = os.path.join(self.root, path)

        path = os.path.realpath(path)

        if self.root:
            if not path.startswith(self.root_slash) and path != self.root:
                # A symlink or .. broke us out of the root.
                # Do not allow this.
                raise RootEscapeError

        return path

    def _remove_root(self, path):
        if self.root:
            if path.startswith(self.root):
                path = path[len(self.root):]
        return path

    def _filter(self, path):
        if self.path_filter:
            return not self.path_filter(path)
        else:
            return False

    def receive(self, preserve, recursive, target_should_be_dir, target):
        """Receive file(s).

        This is the -t flag.

        :Parameters:
            - `preserve`: If true, attempts to preserve modification time,
              access time, and mode of the original file.
            - `recursive`: If true, will recursively send files.
            - `target_should_be_dir`: If true, the target should be a directory.
            - `target`: The target for the file(s).
        """
        if preserve:
            # Clear the mask so that the mode can be properly preserved.
            os.umask(0)
        if '\n' in target:
            self.soft_error('target (%r) contains a newline' % (target,))
            return

        try:
            relative_target = self._get_relative_root(target)
        except RootEscapeError:
            self.soft_error('%s: target not available.' % (target,))
            return

        if self._filter(relative_target):
            self.soft_error('%s: target not available.' % (target,))
            return

        target_is_dir = os.path.isdir(relative_target)
        if target_should_be_dir and not target_is_dir:
            self.soft_error('Expected target %s to be a directory.' % (target,))
            return

        self._respond_success()

        got_timestamp = False
        mtime_sec = mtime_usec = atime_sec = atime_usec = 0
        while 1:
            result = []
            if not self._read_line(result):
                return
            result = ''.join(result)
            self.debug(DEBUG_FULL, 'Executing command: %r', result)
            try:
                code = result[0]
            except IndexError:
                self.hard_error('Expected command character.')
            result = result[1:]
            if code == '\01':
                self._report_error(result[1:])
                self.had_errors = True
            elif code == '\02':
                self._report_error(result[1:])
                sys.exit(1)
            elif code == 'E':
                self._respond_success()
                return
            elif code == 'T':
                parts = result.split()
                if len(parts) != 4:
                    self.hard_error('Timestamp command format error (%r)' % (result,))
                try:
                    mtime_sec = int(parts[0])
                    mtime_usec = int(parts[1])
                    atime_sec = int(parts[2])
                    atime_usec = int(parts[3])
                except ValueError:
                    self.hard_error('Invalid timestamp value (%r)' % (result,))
                else:
                    got_timestamp = True
                    self._respond_success()
            elif code == 'C' or code == 'D':
                if len(result) < 8:
                    # Minimum for 4 bytes (mode), space, length (min 1 byte),
                    # space, name (min 1 byte).
                    self.hard_error('Command length too short (%r)' % (result,))
                try:
                    mode = int(result[:4], 8)
                except ValueError:
                    self.hard_error('Invalid file mode (%r)' % (result,))
                if result[4] != ' ':
                    self.hard_error('Command not properly delimited (%r)' % (result,))
                try:
                    end = result.index(' ', 5)
                except ValueError:
                    self.hard_error('Command not properly delimited (%r)' % (result,))
                try:
                    size = int(result[5:end])
                except ValueError:
                    self.hard_error('Invalid size (%r)' % (result,))
                filename = result[end+1:]
                if not filename:
                    self.hard_error('Filename not specified (%r)' % (result,))
                if '/' in filename or filename == '..':
                    self.hard_error('Invalid filename (%r)' % (result,))
                if target_is_dir:
                    # Store the file in the target directory.
                    relative_pathname = os.path.join(target, filename)
                else:
                    # Store the file as the target.
                    relative_pathname = target
                try:
                    absolute_pathname = self._get_relative_root(relative_pathname)
                except RootEscapeError:
                    self.soft_error('%s: target not available.' % (relative_pathname,))
                    return

                if self._filter(absolute_pathname):
                    self.soft_error('%s: target not available.' % (relative_pathname,))
                    return

                self.debug(DEBUG_EXTRA, 'Receiving file %r mode %o size %i in dir %r' % (filename, mode, size, target))
                if code == 'D':
                    # Creating a directory.
                    if not recursive:
                        self.hard_error('received directory without -r')
                    if os.path.exists(absolute_pathname):
                        if not os.path.isdir(absolute_pathname):
                            self.soft_error('Target (%r) exists, but is not a directory.' % (relative_pathname,))
                            continue
                        if preserve:
                            try:
                                os.chmod(absolute_pathname, mode)
                            except OSError, e:
                                self.debug(DEBUG_NORMAL, 'Failed to chmod %r to %o: %s', relative_pathname, mode, e.strerror)
                                # Continue, this is not critical.
                    else:
                        try:
                            os.mkdir(absolute_pathname, mode)
                        except OSError, e:
                            self.soft_error('Unable to make directory (%r): %s' % (relative_pathname, e.strerror))
                            continue
                    self.receive(preserve, recursive, target_should_be_dir, relative_pathname)
                    if got_timestamp:
                        got_timestamp = False
                        timestamp = (mtime_sec, atime_sec)
                        try:
                            os.utime(absolute_pathname, timestamp)
                        except OSError, e:
                            self.soft_error('Failed to set timestamp (%r) on %r: %s' % (timestamp, relative_pathname, e.strerror))
                            continue
                else:
                    # code == 'C'
                    # Creating a file.
                    try:
                        fd = os.open(absolute_pathname, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, mode)
                    except OSError, e:
                        self.soft_error('Failed to create %r: %s' % (relative_pathname, e.strerror))
                        continue
                    try:
                        self.debug(DEBUG_FULL, 'Send response before start.')
                        self._respond_success()
                        bytes_left = size
                        error = None
                        while bytes_left > 0:
                            block = self.input.read(min(bytes_left, self.blocksize))
                            if not block:
                                self.hard_error('End of file, but expected more data while ready %r.' % (relative_pathname,))
                            bytes_left -= len(block)
                            if not error:
                                try:
                                    os.write(fd, block)
                                except OSError, e:
                                    error = e
                    finally:
                        os.close(fd)
                    self.read_response()
                    if got_timestamp:
                        got_timestamp = False
                        timestamp = (atime_sec, mtime_sec)
                        self.debug(DEBUG_EXTRA, 'Setting timestamp of %r to %r.', relative_pathname, timestamp)
                        try:
                            os.utime(absolute_pathname, timestamp)
                        except OSError, e:
                            self.soft_error('Failed to set timestamp (%r) on %r: %s' % (timestamp, relative_pathname, e.strerror))
                            continue
                    if error:
                        self.soft_error('Error while writing %r: %s' % (relative_pathname, error.strerror))
                    else:
                        self._respond_success()

            else:
                # Unknown command.
                self.hard_error('Invalid command: %r' % (result,))

    def send(self, preserve, recursive, pathnames):
        """Send file(s).

        This is the -f flag.  Make sure you call read_response before calling
        this the first time.

        :Parameters:
            - `preserve`: If true, attempts to preserve modification time,
              access time, and mode of the original file.
            - `recursive`: If true, will recursively send files.
            - `pathnames`: List of pathnames to send.
        """
        for relative_pathname in pathnames:
            if '\n' in relative_pathname:
                self.soft_error('skipping, filename (%r) contains a newline' % (relative_pathname,))
                continue
            # Remove any trailing slashes.
            relative_pathname = relative_pathname.rstrip('/')
            try:
                absolute_pathname = self._get_relative_root(relative_pathname)
            except RootEscapeError:
                self.soft_error('%s: Invalid pathname.' % (relative_pathname,))
                return

            # Potentially do shell expansion.
            if self.shell_globbing:
                more_absolute_pathnames = glob.glob(absolute_pathname)
                if not more_absolute_pathnames:
                    self.soft_error('%s: No such file or directory.' % (relative_pathname,))
                    continue
            else:
                more_absolute_pathnames = [absolute_pathname]

            for more_absolute_pathname in more_absolute_pathnames:
                more_relative_pathname = self._remove_root(more_absolute_pathname)
                # If the original pathname provided was relative, leave the
                # globbed versions as relative.
                if not relative_pathname.startswith('/'):
                    more_relative_pathname = more_relative_pathname.lstrip('/')
                self._send(preserve,
                           recursive,
                           more_relative_pathname,
                           more_absolute_pathname
                          )

    def _send(self, preserve, recursive, relative_pathname, absolute_pathname):

        if not self.filter_recursive_only and self._filter(absolute_pathname):
            self.soft_error('%s: No such file or directory' % (relative_pathname,))
            return

        try:
            st = os.stat(absolute_pathname)
        except OSError, e:
            self.soft_error('%s: %s' % (relative_pathname, e.strerror))
            return
        if stat.S_ISDIR(st.st_mode):
            if self.filter_recursive_only and self._filter(absolute_pathname):
                self.soft_error('%s: No such file or directory' % (relative_pathname,))
                return

            if recursive:
                self._send_recursive(preserve, relative_pathname, absolute_pathname, st)
            else:
                self.soft_error('%s: skipping, is a directory and -r not specified' % (relative_pathname,))
        elif stat.S_ISREG(st.st_mode):
            self._send_file(preserve, relative_pathname, absolute_pathname, st)
        else:
            self.soft_error('%s: skipping, not a regular file' % (relative_pathname,))

    def _send_file(self, preserve, relative_pathname, absolute_pathname, st):
        # pathname should already have been filtered.
        if preserve:
            if not self._send_preserve_timestamp(st):
                return
        base = os.path.basename(relative_pathname)
        self.debug(DEBUG_NORMAL, 'Sending file %r', relative_pathname)
        self.output.write('C%04o %i %s\n' % (stat.S_IMODE(st.st_mode),
                                             st.st_size,
                                             base
                                            )
                         )
        self.output.flush()
        if not self.read_response():
            return
        try:
            fd = os.open(absolute_pathname, os.O_RDONLY)
        except OSError, e:
            self.soft_error('%s: %s' % (relative_pathname, e.strerror))
            return
        try:
            bytes_left = st.st_size
            error = None
            while bytes_left > 0:
                if bytes_left < self.blocksize:
                    to_read = bytes_left
                else:
                    to_read = self.blocksize
                block = os.read(fd, to_read)
                if not block:
                    error = '%s: File shrunk while reading.' % (relative_pathname,)
                    # Keep writing to stay in sync.
                    dummy_data = '\0' * self.blocksize
                    while bytes_left > 0:
                        if bytes_left < len(dummy_data):
                            dummy_data = dummy_data[:bytes_left]
                        self.output.write(dummy_data)
                        bytes_left -= len(dummy_data)
                    break
                self.output.write(block)
                bytes_left -= len(block)
        finally:
            os.close(fd)
        self.output.flush()
        if error:
            self.soft_error(error)
        else:
            self.debug(DEBUG_FULL, 'File send complete, sending success, waiting for response.')
            self._respond_success()
        self.read_response()

    def _send_recursive(self, preserve, relative_pathname, absolute_pathname, st):
        self.debug(DEBUG_EXTRA, 'Send recursive %r', relative_pathname)
        try:
            files = os.listdir(absolute_pathname)
        except OSError, e:
            self.soft_error('%s: %s' % (relative_pathname, e.strerror))
            return
        if preserve:
            if not self._send_preserve_timestamp(st):
                return
        base = os.path.basename(relative_pathname)

        self.debug(DEBUG_NORMAL, 'Sending directory %r', relative_pathname)
        self.output.write('D%04o %i %s\n' % (stat.S_IMODE(st.st_mode),
                                             0,
                                             base
                                            )
                         )
        self.output.flush()
        if not self.read_response():
            return
        for filename in files:
            recursive_relative_pathname = os.path.join(relative_pathname, filename)
            try:
                recursive_absolute_pathname = self._get_relative_root(recursive_relative_pathname)
            except RootEscapeError:
                continue

            if self._filter(recursive_absolute_pathname):
                continue
            self.send(preserve, True, [recursive_relative_pathname])

        self.debug(DEBUG_FULL, 'Sending end of transmission.')
        self.output.write('E\n')
        self.output.flush()
        self.read_response()
        self.debug(DEBUG_FULL, 'End of transmission response read.')

    def _send_preserve_timestamp(self, st):
        self.debug(DEBUG_EXTRA, 'Sending preserve timestamp %i %i', st.st_mtime, st.st_atime)
        self.output.write('T%i 0 %i 0\n' % (st.st_mtime, st.st_atime))
        self.output.flush()
        if self.read_response():
            return True
        else:
            return False

    def _respond_success(self):
        self.output.write('\0')
        self.output.flush()

    def soft_error(self, error):
        """Sends a soft-error response.

        :Parameters:
            - `error`: The error string to send.  This should not have any
              newline characters.
        """
        self.debug(DEBUG_NORMAL, 'Soft error: %s' % (error,))
        self.output.write('\01scp: %s\n' % (error,))
        self.output.flush()
        self._report_error(error)
        self.had_errors = True

    def hard_error(self, error):
        """Sends a hard-error response.

        This function calls sys.exit.

        :Parameters:
            - `error`: The error string to send.  This should not have any
              newline characters.
        """
        self.debug(DEBUG_NORMAL, 'Hard error: %s' % (error,))
        self.output.write('\02scp: %s\n' % (error,))
        self.output.flush()
        self._report_error(error)
        sys.exit(1)

    def read_response(self):
        """Read a response.

        This function calls sys.exit on fatal errors.

        :Return:
            Returns True on a successful response, False otherwise.
        """
        code = self.input.read(1)
        self.debug(DEBUG_FULL, 'Got response %r' % (code,))
        if code == '\0':
            return True
        else:
            if code == '\1' or code == '\2':
                result = []
            else:
                result = [code]
            self._read_line(result)
            result = ''.join(result)
            self._report_error(result)
            self.had_errors = True
            if code == '\1':
                return False
            else:
                sys.exit(1)

    def _read_line(self, result):
        for unused in xrange(self.max_line_size):
            char = self.input.read(1)
            if not char:
                if not result:
                    return False
                else:
                    self.hard_error('End of line, expected \\n')
            if char == '\n':
                break
            result.append(char)
        else:
            # Never saw a \n.
            self.hard_error('Command line too long (%i)' % (self.max_line_size,))
        return True


    def _report_error(self, message):
        """Report an error message.

        By default, this does nothing (since the base code is intended for use
        on the server side). The client side should send the message to stderr
        or its equivalent.

        :Parameters:
            - `message`: The message to print (should not have a newline).
        """
        pass

    def debug(self, level, format, *args):
        """Send a debug message.

        :Parameters:
            - `level`: The level of the message.  May be DEBUG_NORMAL,
              DEBUG_EXTRA, or DEBUG_FULL.
            - `format`: The string to write.  Will be applied with the Python
              format operator with the rest of the arguments.
        """
        if level <= self.verbosity:
            msg = format % args
            print >>sys.stderr, '%s %i:%s' % (time.ctime(), level, msg)
