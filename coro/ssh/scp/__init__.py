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

"""Secure Copy.

Overview
========
This implements the scp "protocol" for transferring files over SSH.

AFAIK, the SCP/RCP "protocol" is not documented anywhere.  This implemented is
inferred from the BSD and OpenSSH source code.

Options
=======
Running the SCP process from the command line has the options defined in the
usage string in `ssh.scp.cli`.

The scp command connects to the remote host and runs the "scp" process
(assuming it is in your PATH somewhere).

If it is sending the file to the remote host, then it has the following
options:

    scp [options] -t pathnames...

If it is getting a file from the remote host, then it has the following
options:

    scp [options] -f target

A special option for running in remote mode is '-d'.  This indicates that the
target should be a directory.  This is only true if more than one source file
is specified.

The only other options supported by this implementation are "-p", "-r" and
"-v" which are user options defined in the usage string.

These options are not very consistent.  For example, rcp in FreeBSD does not
support "-v", but it does support "-x" (which is for encryption and thus not
used in scp).

Messages
========
The SCP protocol involves one side (the client) sending commands to the other
side (the server).  The commands are 1 letter, options for that command,
terminated by a newline character.  The commands are:

    - ``T``: Indicates the timestamp of the next file (only).  The format is::

        mtime_sec SPACE mtime_usec SPACE atime_sec SPACE atime_usec

      The timestamps are POSIX timestamps in ASCII base-10.  Most
      implementations use 0 for the micro-second portions.

      ``mtime`` is the modified time.  ``atime`` is the last access time.

      This is only sent if the -p option is specified.

    - ``C``: A file.  The format is::

        mode SPACE size SPACE filename

      ``mode`` is a 4-digit octal number in ASCII that is the mode of the file.

      ``size`` is a number in ASCII base-10 that indicates the size of the data
      to follow.

      ``filename`` is the name of the file (with no path information).

      The data immediately follows this entry.

    - ``D``: A directory.  The format is the same as a file (C), but the size
      is zero.  All following files will be in this specified directory.

    - ``E``: The end of transmission.  This has no options.

Care should be taken to make sure a filename does not contain a newline
character.

Responses
=========
Every command requires a response.  A response is a message, with the following
codes:

    - ``\0``: A successful response.

    - ``\01``: An soft error occurred.  The error string follows up to the
      newline character.  This does not stop the data stream.

    - ``\02``: A hard error occurred.  The error string follows up to the
      newline character.  This causes the receiving side (the server) to exit.

Any other character in a response is interpreted as a hard error.

Sending and receiving files has the following message/response timeline:

    =================   =================
    Client              Server
    =================   =================
    Send C command
    Wait for response
                        Send response
    Got response
    Send file
                        Receive file
                        Wait for response
    Send response
    Wait for response
                        Got response
                        Send response
    Got response
    =================   =================

Transfer Modes
==============
There are various transfer modes that the scp program can run in.  The
following is a description of those modes from the perspective of the person
initiating the scp command.

1. Local to local.  This doesn't actually use SSH to transfer, and acts very
   similar to cp.
2. Local to remote.  The local side connects to the remote host with the -t
   option and sends the file(s).
3. Remote to local.  The local side connects to the remote host with the -f
   option and requests file(s).
4. Remote to remote.  The local side connects to the source remote host with
   the -f option and connects to the target remote host with the -t option and
   relays the data between the two hosts.

"""
