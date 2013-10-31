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
# ssh.keys.openssh_key_formats
#
# This module contains expressions for parsing and matching keys.
#

import re
from rebuild import *

SPACE = '[ \t]'
NUMBER = '\d'
LIST_OF_HOSTS = NAME('list_of_hosts', PLUS('[^ \t]'))
COMMENT = OPTIONAL(
                   PLUS(SPACE),
                   NAME('comment', PLUS('.'))
                  )

ssh1_key = re.compile(
                CONCAT('^',
                       LIST_OF_HOSTS,
                       PLUS(SPACE),
                       NAME('number_of_bits', PLUS(NUMBER)),
                       PLUS(SPACE),
                       NAME('exponent', PLUS(NUMBER)),
                       PLUS(SPACE),
                       NAME('modulus', PLUS(NUMBER)),
                       COMMENT
                      )
                     )

# The man page for OpenSSH specifies that "ssh-dss" and "ssh-rsa" are the only
# valid types, but the code actually checks for this list of types.  Let's
# try to be as flexible as possible.
KEYTYPE = NAME('keytype', OR('ssh-dss', 'ssh-rsa', 'rsa1', 'rsa', 'dsa'))
# Not a very exact base64 regex, but should be good enough.
# OpenSSH seems to ignore spaces anywhere.  Also, this doesn't check for
# a "partial" or truncated base64 string.
BASE64_KEY = NAME('base64_key', PLUS('[a-zA-Z0-9+/=]'))

ssh2_key = re.compile(
                    CONCAT('^',
                           KEYTYPE,
                           PLUS(SPACE),
                           BASE64_KEY,
                           COMMENT
                          )
                     )

ssh2_known_hosts_entry = re.compile(
                CONCAT('^',
                       LIST_OF_HOSTS,
                       PLUS(SPACE),
                       KEYTYPE,
                       PLUS(SPACE),
                       BASE64_KEY,
                       COMMENT
                      )
                     )
