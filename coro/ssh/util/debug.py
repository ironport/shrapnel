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

#
# ssh_debug
#
# This module implements the debugging facilities.
#
# Debug information is represented at different levels:
# ERROR - Fatal error.
# WARNING - Warning about a non-fatal problem.
# INFO - General information.
# DEBUG_1 - Action-level information.
# DEBUG_2 - Packet-level information.
# DEBUG_3 - Low-level function tracing.
#
# Setting the log level includes all levels above it.
# Default level is WARNING.
#

ERROR   = 0
WARNING = 1
INFO    = 2
DEBUG_1 = 3
DEBUG_2 = 4
DEBUG_3 = 5

level_text = {ERROR: 'Error',
              WARNING: 'Warning',
              INFO: 'Info',
              DEBUG_1: 'Debug 1',
              DEBUG_2: 'Debug 2',
              DEBUG_3: 'Debug 3',
              }

import sys

class Debug:

    level = WARNING

    def write(self, level, message, args=None):
        if level <= self.level:
            if args is not None:
                message = message % args
            try:
                sys.stderr.write('[%s] %s\n' % (level_text[level], message))
            except IOError:
                pass
