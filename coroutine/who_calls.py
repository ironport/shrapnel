# -*- Mode: Python -*-
# Copyright (c) 2002-2011 IronPort Systems and Cisco Systems
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

import sys

class whoCallsError (Exception):
    pass

import os

def get_module_name (n):
    try:
        return os.path.split (n)[-1].split('.')[0]
    except:
        return '???'

def who_calls_helper():
    tinfo = []
    exc_info = sys.exc_info()

    f = exc_info[2].tb_frame.f_back
    while f:
        tinfo.append ((
            get_module_name (f.f_code.co_filename),
            f.f_code.co_name,
            str (f.f_lineno)
            ))
        f = f.f_back

    del exc_info
    tinfo.reverse()
    return '[' + ('] ['.join (map ('|'.join, tinfo))) + ']'

def who_calls():
    try:
        raise whoCallsError
    except whoCallsError:
        tinfo = who_calls_helper()
    return tinfo
