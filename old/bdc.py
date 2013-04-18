#telnet client
#
# Usage : telnetclient.py hostname portnumber
#
# Programmed by Gang Seong Lee
# 2000.3.20

from telnetlib import Telnet
import time, sys
from threading import *
#import readline
import editline; editline.parse_and_bind ('bind -e')
import os

host = ''
port = 23

class ReaderThread(Thread):
        def __init__(self, telnet):
                self.telnet = telnet
                Thread.__init__(self)

        def run(self):
                while 1:
                        str = self.telnet.read_some()
                        if str == '':
                            break
                        sys.stdout.write(str)
                        sys.stdout.flush()

def main(host, port):
        telnet = Telnet()
        telnet.open(host, port)

        reader = ReaderThread(telnet)
        reader.start()

        while 1:
                if not reader.isAlive():
                    print 'giving up'
                    break
                try:
                    line = raw_input()
                except:
                    break
                telnet.write(line+'\r\n')
        print '\n'
        os._exit(0)
#        telnet.close()

if __name__ == '__main__':
        try:
                host = sys.argv[1]
        except: pass
        try:
                port = int(sys.argv[2])
        except: pass
        try:
            main(host, port)
        except: pass
        sys.exit(0)
