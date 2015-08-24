# -*- Mode: Python -*-

import coro
from coro.ssl import openssl
import coro.ssl
import coro.backdoor
import os
import random

from coro.log import NoFacility
from hashlib import sha512

LOG = NoFacility()

# use sha512 as a random-data generator.
# pre-generate 10MB of random data to iterate through

def gen_random_data (seed='fnord'):
    LOG ('generate data', 'start')
    blocks = []
    h = sha512()
    data = seed
    nblocks = (1024 * 1024 * 10) / 64
    for i in range (nblocks):
        h.update (data)
        data = h.digest()
        blocks.append (data)
    LOG ('generate data', 'stop')
    return blocks

random_blocks = gen_random_data()

class random_char_gen:

    def __init__ (self):
        self.index = 0
        self.blocks = random_blocks

    def next (self):
        result = self.blocks[self.index]
        self.index += 1
        if self.index == len(self.blocks):
            self.index = 0
        return result

class random_block:

    def __init__ (self, gen):
        self.gen = gen
        self.buffer = self.gen.next()
        self.random = random.Random (3141)

    def next (self, size):
        while 1:
            if size <= len(self.buffer):
                result, self.buffer = self.buffer[:size], self.buffer[size:]
                return result
            else:
                self.buffer += self.gen.next()

    def random_size (self):
        size = self.random.randrange (10, 500)
        return self.next (size)

def feed (s):
    global wbytes
    blockgen = random_block (random_char_gen())
    while 1:
        block = blockgen.random_size()
        #LOG ('=>', block.encode ('hex'))
        s.send (block)
        wbytes += len (block)
        #coro.sleep_relative (3)

def session (addr):
    LOG ('pid', os.getpid())
    global rbytes
    ctx = openssl.ssl_ctx()
    s = coro.ssl.sock (ctx)
    s.connect (addr)
    assert (s.recv (1024) == 'Howdy!\r\n')
    coro.spawn (feed, s)
    # generates the same stream of characters we sent
    blockgen = random_block (random_char_gen())
    while 1:
        data = s.recv (50)
        #LOG ('<=', data.encode ('hex'))
        rbytes += len (data)
        assert (data == blockgen.next (len (data)))

rbytes = 0
wbytes = 0

def monitor (interval=10):
    global rbytes, wbytes
    while 1:
        r0, w0 = rbytes, wbytes
        coro.sleep_relative (interval)
        r = rbytes - r0
        w = wbytes - w0
        LOG ('throughput', r / interval, w / interval)

if __name__ == '__main__':
    coro.spawn (session, ('127.0.0.1', 7777))
    coro.spawn (coro.backdoor.serve, unix_path='/tmp/openssl_client.bd', global_dict=globals())
    coro.spawn (monitor)
    try:
        coro.event_loop()
    finally:
        LOG ('done')
