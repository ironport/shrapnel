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

"""CLI interface.

This is the interface for running SCP and a command-line process.
"""

import optparse
import sys

from coro.ssh.scp import client, core

usage = """\
scp [options] file1 file2
scp [options] file1 ... directory

Each file or directory argument is either:

    - A remote filename or directory in the format of
      ``username@hostname:pathname`` or ``hostname:pathname``.
    - A local filename or directory.  A local filename can not have any colons
      before a slash.

If more than one source file is specified, the destination must be a directory
that exists.

The following options are available:

-p      Preserve modification time, access time, and mode of the original file.
-r      If any source filename is a directory, then transfer the directory and
        all subfiles and directories to the remote host.  The destination must
        be a directory.
-v      Produce verbose output.  Up to 3 -v commands for more verbosity.

Note on file ownership and mode:  If the destination is a file, and that file
already exists, then the mode and owner for the destination file is preserved.
If the destination is a directory or a filename that does not exist, then the
file will be created with the ownership of the remote user and the mode of the
original file modified by the umask of the remote user.
"""

class CLI:

    def main(self, args=None):
        """The main entry point for the SCP cli program.

        Calls sys.exit when finished.

        :Parameters:
            - `args`: The command line arguments as a list of strings.  If
              None, will use sys.argv.
        """
        parser = optparse.OptionParser(usage=usage, add_help_option=False)
        parser.add_option('-p', dest='preserve', action='store_true')
        parser.add_option('-r', dest='recursive', action='store_true')
        parser.add_option('-v', dest='verbosity', action='count')
        parser.add_option('-t', dest='action_to', action='store_true')
        parser.add_option('-f', dest='action_from', action='store_true')
        parser.add_option('-d', dest='target_should_be_dir', action='store_true')
        parser.add_option('--help', dest='help', action='store_true')
        if args is None:
            args = sys.argv[1:]
        options, arguments = parser.parse_args(args)
        if options.help:
            print usage
            sys.exit(0)


        if options.action_from:
            scp = self._get_scp()
            scp.verbosity = options.verbosity
            scp.debug(core.DEBUG_EXTRA, 'options: %r', args)
            scp.read_response()
            scp.send(options.preserve,
                     options.recursive,
                     arguments
                    )
            sys.exit(int(scp.had_errors))

        elif options.action_to:
            scp = self._get_scp()
            scp.verbosity = options.verbosity
            scp.debug(core.DEBUG_EXTRA, 'options: %r', args)
            if len(arguments) != 1:
                scp.hard_error('Must specify 1 target.')
            scp.receive(options.preserve,
                        options.recursive,
                        options.target_should_be_dir,
                        arguments[0]
                       )
            sys.exit(int(scp.had_errors))
        else:
            print 'Function unavailable.'
            sys.exit(1)
            client = self._get_client()
            client.main(options.preserve,
                        options.recursive,
                        options.verbosity,
                        arguments
                       )

    def _get_scp(self):
        return core.SCP()

    def _get_client(self):
        return client.Client()

if __name__ == '__main__':
    cli = CLI()
    cli.main()
