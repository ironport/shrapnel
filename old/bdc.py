#!/usr/bin/env python

# originally based on a telnet client by Gang Seong Lee, 2000.3.20.

from telnetlib import Telnet

import socket
import sys
import readline
import os

class UnixTelnet (Telnet):
    def open (self, addr, timeout=socket._GLOBAL_DEFAULT_TIMEOUT):
        self.eof = 0
        if type(addr) is str:
            self.host = 'none'
            self.port = 0
            self.sock = socket.socket (socket.AF_UNIX, socket.SOCK_STREAM)
        else:
            self.host, self.port = addr
            self.sock = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect (addr)


PYTHON_PROMPT = '>>> '
PYTHON_PROMPT_REGEX = '>>> \Z'
PYTHON_CONTINUATION_PROMPT = '... '
PYTHON_CONTINUATION_PROMPT_REGEX = '\\.\\.\\. \Z'
PROMPTS = [PYTHON_PROMPT, PYTHON_CONTINUATION_PROMPT]
PROMPT_REGEXS = [PYTHON_PROMPT_REGEX, PYTHON_CONTINUATION_PROMPT_REGEX]
HOME_DIRECTORY = os.path.expanduser("~")
HISTORY_FILE_NAME = '.bdc_history'

def main (addr):
    history_file = os.path.join(HOME_DIRECTORY, HISTORY_FILE_NAME)
    try:
        readline.read_history_file(history_file)
    except IOError:
        print 'Error reading history file:', history_file
    import atexit
    atexit.register(readline.write_history_file, history_file)

    telnet = UnixTelnet()
    telnet.open (addr)

    # The prompt that shrapnel includes in the output interferes with
    # readline's prompt so strip off the prompt from the output
    # before emitting the banner text from shrapnel
    shrapnel_output = telnet.read_until(PYTHON_PROMPT)
    prompt_index = shrapnel_output.find(PYTHON_PROMPT)
    banner = shrapnel_output[:prompt_index]
    sys.stdout.write(banner)
    sys.stdout.flush()

    prompt = PYTHON_PROMPT
    while True:
        try:
            line = raw_input(prompt)
            telnet.write(line + '\r\n')
            prompt_index, _, response = telnet.expect(PROMPT_REGEXS)
            prompt = PROMPTS[prompt_index]
            sys.stdout.write(response[:-len(prompt)])
            sys.stdout.flush()
        except EOFError:
            break

    sys.stdout.write(os.linesep)

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser (description='shrapnel back door client')
    ap.add_argument ('addr', help='server address', default='127.0.0.1:23', metavar="(HOST:PORT)|PATH")
    args = ap.parse_args()
    if ':' in args.addr:
        host, port = args.addr.split (':')
        port = int (port)
        addr = (host, port)
    else:
        addr = args.addr
    main (addr)
