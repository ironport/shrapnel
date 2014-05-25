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
# ssh.util
#
# Utility functions for the SSH code.
#

import string

def pick_from_list(name, algorithms):
    """pick_from_list(name, algorithms) -> algorithm
    Picks the algorithm from the list based on the name.

    <name> - The name (a string) to find.
    <algorithms> - List of algorithm classes that have a "name" attribute.

    Returns None if no match found.

    If <name> is None, then it will pick the first item in the list.
    """
    if name is None:
        try:
            return algorithms[0]
        except IndexError:
            return None
    for algorithm in algorithms:
        if algorithm.name == name:
            return algorithm
    return None

nonprintable = ''.join ([x for x in map (chr, range(256)) if x not in string.printable])
nonprintable_replacement = '$' * len(nonprintable)
nonprintable_table = string.maketrans(nonprintable, nonprintable_replacement)

def safe_string(s):
    """safe_string(s) -> new_s
    Escapes control characters in s such that it is suitably
    safe for printing to a terminal.
    """
    return string.translate(s, nonprintable_table)

def str_xor(a, b):
    """str_xor(a, b) -> str
    Returns a^b for every character in <a> and <b>.
    <a> and <b> must be strings of equal length.
    """
    return ''.join(map(lambda x, y: chr(ord(x) ^ ord(y)), a, b))
