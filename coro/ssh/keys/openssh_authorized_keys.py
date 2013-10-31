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
# ssh.keys.openssh_authorized_keys
#
# This module handles the authorized_keys file.
#

import os
import re
from rebuild import *

class DuplicateKeyError(Exception):
    pass

# Keys are in two formats:
# SSH1:
#   [options] bits exponent modulus comment
# SSH2:
#   [options] keytype base64_key comment
#
# The options are optional. They never start with a number, nor do they
# contain spaces. It is a comma-separated list of values.
#
# The SSH1 key format is as follows. The bits is a number, typically
# something like 1024. The exponent is also a number, typically something
# like 35. The modulus is a very long string of numbers. The comment can be
# anything, but it is typically username@hostname.
#
# The SSH2 key format is as follows. The keytype is either ssh-dss or ssh-rsa.
# The key is a long string encoded in base-64. The comment can be anything,
# but it is typically username@hostname.

SPACE = '[ \t]'

OPTION_START = '[^ \t0-9]'
ATOM = '[^ \t]'
QUOTED_ATOM = '"[^"]*"'
WORD = OR(ATOM, QUOTED_ATOM)
OPTIONS = NAME('options', OPTION_START + SPLAT(WORD))

BITS = NAME('bits', '\d+')
EXPONENT = NAME('exponent', '\d+')
MODULUS = NAME('modulus', '\d+')
COMMENT = NAME('comment', '.*')

ssh1_key = CONCAT('^',
                  SPLAT(SPACE),
                  BITS, PLUS(SPACE),
                  EXPONENT, PLUS(SPACE),
                  MODULUS, SPLAT(SPACE),
                  COMMENT
                  )

ssh1_key_w_options = CONCAT('^',
                  SPLAT(SPACE),
                  OPTIONS, PLUS(SPACE),
                  BITS, PLUS(SPACE),
                  EXPONENT, PLUS(SPACE),
                  MODULUS, SPLAT(SPACE),
                  COMMENT
                  )


# The man page for OpenSSH specifies that "ssh-dss" and "ssh-rsa" are the only
# valid types, but the code actually checks for this list of types.  Let's
# try to be as flexible as possible.
KEYTYPE = NAME('keytype', OR('ssh-dss', 'ssh-rsa', 'rsa1', 'rsa', 'dsa'))
# Not a very exact base64 regex, but should be good enough.
# OpenSSH seems to ignore spaces anywhere.  Also, this doesn't check for
# a "partial" or truncated base64 string.
BASE64_KEY = NAME('base64_key', PLUS('[a-zA-Z0-9+/=]'))

ssh2_key = CONCAT('^',
                  SPLAT(SPACE),
                  KEYTYPE, PLUS(SPACE),
                  BASE64_KEY, SPLAT(SPACE),
                  COMMENT
                  )

ssh2_key_w_options = CONCAT('^',
                  SPLAT(SPACE),
                  OPTIONS, PLUS(SPACE),
                  KEYTYPE, PLUS(SPACE),
                  BASE64_KEY, SPLAT(SPACE),
                  COMMENT
                  )

ssh1_key_re = re.compile(ssh1_key)
ssh2_key_re = re.compile(ssh2_key)
ssh1_key_w_options_re = re.compile(ssh1_key_w_options)
ssh2_key_w_options_re = re.compile(ssh2_key_w_options)

class OpenSSH_Authorized_Keys:

    """OpenSSH_Authorized_Keys(filename)

    This is a class that will represent an SSH authorized_keys file.
    """

    def __init__(self, filename):
        self.filename = filename
        # This is a list of dictionary objects.
        self.keys = []
        self.read()

    def read(self):
        """read() -> None
        Reads the contents of the keyfile into memory.
        If the file does not exist, then it does nothing.
        """
        if os.path.exists(self.filename):
            lines = open(self.filename).readlines()
        else:
            lines = []
        for line in lines:
            line = line.strip()
            # ignore comment lines
            if line and line[0] != '#':
                try:
                    self.add_key(line)
                except (DuplicateKeyError, ValueError):
                    # Ignore this entry.
                    # Maybe we should print an error or something?
                    pass

    def add_key(self, key):
        """add_key(key) -> None
        Adds the given key to the object.
        <key> is a string.
        Raises DuplicateKeyError if the key already exists.
        Raises ValueError if the key does not appear to be a valid format.
        """
        key = key.strip()
        m = ssh1_key_re.match(key)
        if not m:
            m = ssh2_key_re.match(key)
            if not m:
                m = ssh1_key_w_options_re.match(key)
                if not m:
                    m = ssh2_key_w_options_re.match(key)
                    if not m:
                        raise ValueError, key

        values = m.groupdict()
        if ((values.has_key('keytype') and not values['keytype']) or
            (values.has_key('base64_key') and not values['base64_key']) or
            (values.has_key('bits') and not values['bits']) or
            (values.has_key('exponent') and not values['exponent']) or
            (values.has_key('modulus') and not values['modulus'])
            ):
            raise ValueError, key
        self._value_strip(values)
        if not values.has_key('options') or not values['options']:
            # If it doesn't exist, or it exists as None, set it to the empty string.
            values['options'] = ''
        if not values['comment']:
            values['comment'] = ''
        self._duplicate_check(values)
        self.keys.append(values)

    def _value_strip(self, d):
        """_value_strip(d) -> None
        Takes d, which is a dict, and calls strip() on all its values.
        """
        for key, value in d.items():
            if value:
                d[key] = value.strip()

    def _duplicate_check(self, key):
        """_duplicate_check(key) -> None
        Checks if key (which is dict-format) is a duplicate.
        Raises DuplicateKeyError if it is.
        """
        if key.has_key('bits'):
            # SSH1
            for x in self.keys:
                if (x.has_key('bits') and
                    x['bits'] == key['bits'] and
                    x['exponent'] == key['exponent'] and
                    x['modulus'] == key['modulus']):
                    raise DuplicateKeyError
        else:
            # SSH2
            for x in self.keys:
                if (x.has_key('keytype') and
                    x['keytype'] == key['keytype'] and
                    x['base64_key'] == key['base64_key']):
                    raise DuplicateKeyError

    def write(self):
        """write() -> None
        Writes the keyfile to disk, safely overwriting the keyfile that
        already exists.
        """
        # Avoid concurrent races here?
        tmp_filename = self.filename + '.tmp'
        fd = os.open(tmp_filename, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0644)
        write = lambda x,y=fd: os.write(y, x)
        map(write, map(self.keydict_to_string, self.keys))
        os.close(fd)
        os.rename(tmp_filename, self.filename)

    def keydict_to_string(self, key, short_output=0):
        """keydict_to_string(key, short_output=0) -> string
        Converts an SSH dict-format key into a string.
        <short_output> - Set to true if you want to exclude options and comment.
        """
        if short_output:
            options = ''
            comment = ''
        else:
            options = key['options']
            comment = key['comment']
        if key.has_key('bits'):
            # SSH1
            bits = key['bits']
            exponent = key['exponent']
            modulus = key['modulus']
            result = ' '.join([options, bits, exponent, modulus, comment])
        else:
            # SSH2
            keytype = key['keytype']
            base64_key = key['base64_key']
            result = ' '.join([options, keytype, base64_key, comment])
        return result.strip() + '\n'
