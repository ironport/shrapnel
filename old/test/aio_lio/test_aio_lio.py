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

"""Test program for AIO.

This exercises AIO functionality in coro.  Run with --help for more detail.
"""

# XXX TODO
# - convert to real unittest?

import backdoor
import bintree
import comm_path
import coro
import optparse
import os
import random
import signal
import sysctl
import t_aio
import tempfile
from comma_group import comma_group

usage = """test_aio.py [options] test_path

The test_path is a path to a file or device where you want to test AIO.
BEWARE!  THIS WILL DESTROY ANYTHING ON THAT DEVICE OR FILE!
"""

USING_LISTIO = 0
MAX_LIO = 0

try:
    import lio_listio
except ImportError:
    if hasattr(coro, 'lio_read'):
        USING_LISTIO = 1
    else:
        USING_LISTIO = 0

if USING_LISTIO:
    MAX_LIO = sysctl.sysctl('p1003_1b.aio_listio_max', 1)
    if MAX_LIO:
        USING_LISTIO = 1
    else:
        USING_LISTIO = 0

# 512 bytes
DISK_BLOCK_SIZE = (1<<9)
DISK_BLOCK_MASK = ((1<<9)-1)

# fall 512 bytes shy of a full 64K, this will avoid wasting an entire
# 32K malloc block to hold the extra 24 bytes of Python object
# overhead.
MAX_LIO_SIZE = ((64 * 1024) - DISK_BLOCK_SIZE)

assert ((MAX_LIO_SIZE % DISK_BLOCK_SIZE) == 0)

def get_random(nbytes):
    return open('/dev/urandom').read(nbytes)

def shutdown(signum):
    # Unfortunately if the code gets in a tight loop, this doesn't run because
    # it is being delievered by kqueue.
    coro.set_exit(1)
    os._exit(1)

class TestAIO:

    def __init__(self):
        self._worker_semaphore = coro.inverted_semaphore()
        self._writes_finished = 0
        self._reads_finished = 0
        self._bytes_written = 0
        self._bytes_read = 0
        self._start_time = 0
        self._fd = -1
        self._written = []
        self._size = 0
        self._num_live_writers = 0

        self._write_cancel_success = 0
        self._write_cancel_fail = 0
        self._read_cancel_success = 0
        self._read_cancel_fail = 0
        self._assertion_errors = 0
        self._write_locks = None
        self._read_locks = None

        self.main_thread_state = 'Not started.'
        self.writer_status = {}
        self.reader_status = {}
        self.lio_status = {}

    def main(self):
        try:
            try:
                self._main()
            except SystemExit, e:
                if e.code is not None:
                    if not isinstance(e.code, int):
                        print e.code
                coro.set_exit()
        finally:
            coro.set_exit()

    def _main(self):
        parser = optparse.OptionParser(usage=usage)
        parser.add_option('-v', '--verbose', action='count',
                          help='Verbose output.  Specify multiple times for more verbosity.'
                         )
        parser.add_option('--blocks', type='int', action='store', default=1048576,
                          metavar=`1048576`,
                          help='The size of the file in blocks.'
                         )
        parser.add_option('--num-writers', type='int', action='store', default=50,
                          metavar=`50`,
                          help='The number of writer threads.'
                         )
        parser.add_option('--num-readers', type='int', action='store', default=50,
                          metavar=`50`,
                          help='The number of reader threads.'
                         )
        parser.add_option('--max-num-blocks', type='int', action='store', default=100*1024,
                          metavar=`100*1024`,
                          help='The maximum number of blocks to write.'
                         )
        parser.add_option('--block-size', type='int', action='store', default=1,
                          metavar=`1`,
                          help='The size of a block.'
                         )
        parser.add_option('--duration', type='int', action='store', default=60,
                          metavar=`60`,
                          help='How long to run the test in seconds.'
                         )
        parser.add_option('--reader-delay', type='int', action='store', default=10000,
                          metavar=`10000`,
                          help='How many writes to wait to finish before starting the readers.'
                         )
        parser.add_option('--greediness', type='int', action='store', default=10,
                          metavar=`10`,
                          help='Number of consecutive reads or writes to perform before yielding.'
                         )
        parser.add_option('--cancel-percent', type='int', action='store', default=10,
                          metavar=`10`,
                          help='The percent of operations to try to cancel.'
                         )
        parser.add_option('--lio', action='store_true',
                          help='Use LIO instead of AIO.'
                         )
        parser.add_option('--min-lio', type='int', action='store', default=1,
                          metavar=`1`,
                          help='The minimum number of events per LIO submit.'
                         )
        parser.add_option('--max-lio', type='int', action='store', default=MAX_LIO,
                          metavar=`MAX_LIO`,
                          help='The maximum number of events per LIO submit.'
                         )
        parser.add_option('--max-lio-size', type='int', action='store', default=MAX_LIO_SIZE,
                          metavar=`MAX_LIO_SIZE`,
                          help='The maximum size of a block of data in a LIO request.  Do not change unless you know what you are doing.  This is used instead of --max-num-blocks when using LIO.'
                         )
        parser.add_option('--num-lio-workers', type='int', action='store', default=50,
                          metavar=`50`,
                          help='The number of workers to use for LIO (used instead of --num-readers and --num-writers).'
                         )
        # blocked
        # interrupt percentage
        self.options, arguments = parser.parse_args()
        if len(arguments) != 1:
            parser.error('Must specify 1 argument.')

        # Check for valid settings.
        if self.options.lio:
            if not USING_LISTIO:
                parser.error('Unable to use LIO.  Either lio_listio is not compiled, or the sysctl p1003_1b.aio_listio_max is not set.')
            if self.options.max_lio > MAX_LIO:
                parser.error('Maximum number of LIO events cannot be set above the p1003_1b.aio_listio_max sysctl value (currently %i).' % (MAX_LIO,))
            if self.options.min_lio > self.options.max_lio:
                parser.error('--min-lio cannot be set above --max-lio')
            if self.options.max_lio_size % self.options.block_size:
                parser.error('--max-lio-size is not a multiple of --block-size')
        else:
            if self.options.max_num_blocks > self.options.blocks/2:
                parser.error('max_num_blocks cannot be greater than the file size divided by 2.')


        self._size = self.options.blocks * self.options.block_size

        self._write_locks = bintree.bintree((0, self._size))
        self._read_locks = bintree.bintree((0, self._size))

        self.path = arguments[0]
        self.main_thread_state = 'Creating file.'
        self.create()
        self.main_thread_state = 'Preparing file.'
        self.prep()
        if self.options.lio:
            self.start_lio()
        else:
            self.start_aio()
        print 'Write cancel success: %i' % (self._write_cancel_success,)
        print 'Write cancel failure: %i' % (self._write_cancel_fail,)
        print 'Read cancel success: %i' % (self._read_cancel_success,)
        print 'Read cancel failure: %i' % (self._read_cancel_fail,)
        print 'Total writes: %s (%s bytes)' % (comma_group(self._writes_finished), comma_group(self._bytes_written))
        print 'Total reads: %s (%s bytes)' % (comma_group(self._reads_finished), comma_group(self._bytes_read))
        print 'Assertion errors: %i' % (self._assertion_errors,)

    def log(self, level, message, *args):
        if level <= self.options.verbose:
            if args:
                message = message % args
            coro.print_stderr(message + '\n')

    def create(self):
        if not os.path.exists(self.path) or os.path.isfile(self.path):
            self.log(0, 'Creating %r', self.path)
            fd = os.open(self.path, os.O_RDWR|os.O_CREAT|os.O_TRUNC)
            try:
                size = self.options.blocks * self.options.block_size
                os.lseek(fd, size-1, 0)
                os.write(fd, '\0')
            finally:
                os.close(fd)
        else:
            self.log(0, '%s is not a regular file, assuming block device', self.path)

    def start_aio(self):
        self._start_time = coro.get_now()
        self.main_thread_state = 'Starting writers.'
        self.log(1, 'Starting %i writers.', self.options.num_writers)
        for x in xrange(self.options.num_writers):
            self._worker_semaphore.acquire()
            coro.spawn(self._writer, x)

        while 1:
            # Spin lock.
            status = 'Waiting for writers to ramp up %i/%i.' % (self._writes_finished, self.options.reader_delay)
            self.main_thread_state = status
            self.log(2, status)
            if int(self._worker_semaphore) == 0:
                self.log(0, 'EEP!  All writers exited too fast.')
                self.main_thread_state = 'Aborted.'
                return
            if self._writes_finished < self.options.reader_delay:
                coro.sleep_relative(0.5)
            else:
                break

        self.main_thread_state = 'Starting readers.'
        self.log(1, 'Starting %i readers.', self.options.num_readers)
        for x in xrange(self.options.num_readers):
            self._worker_semaphore.acquire()
            coro.spawn(self._reader, x)

        self.main_thread_state = 'Waiting for all threads to finish.'
        self.log(1, 'Waiting till all threads finished.')
        self._worker_semaphore.block_till_zero()
        self.main_thread_state = 'Done.'

    def start_lio(self):
        self._start_time = coro.get_now()
        self.main_thread_state = 'Starting LIO workers.'
        self.log(1, 'Starting %i lio workers.', self.options.num_lio_workers)
        for x in xrange(self.options.num_lio_workers):
            self._worker_semaphore.acquire()
            coro.spawn(self._lio, x)

        self.main_thread_state = 'Waiting for all threads to finish.'
        self.log(1, 'Waiting till all threads finished.')
        self._worker_semaphore.block_till_zero()
        self.main_thread_state = 'Done.'

    def _get_to_write(self):
        attempts = 0
        while 1:
            # Pick a random location to read from.
            attempts += 1
            if not attempts % 3:
                self.log(2, 'Failed to pick write location 3 times.')
                coro.sleep_relative(0)
            block_pos = random.randint(1, self.options.blocks)-1
            pos = block_pos * self.options.block_size

            if self.options.lio:
                max_lio_blocks = self.options.max_lio_size / self.options.block_size
                max_num_blocks = min(max_lio_blocks,
                                     self.options.blocks - block_pos)
            else:
                max_num_blocks = min(self.options.max_num_blocks,
                                     self.options.blocks - block_pos)
            num_blocks = random.randint(1, max_num_blocks)
            size = num_blocks * self.options.block_size

            area = (pos, pos+size)

            if (self._write_locks.search(area) or
                self._read_locks.search(area)):
                # Someone is currently writing to this position.
                self.log(2, 'writer skipping lock %r', area)
            else:
                break

        self._write_locks.insert(area)
        return pos, size, area

    def _get_to_read(self):
        attempts = 0
        while 1:
            # Pick a random location that has been written.
            # Don't pick anything that overlaps with stuff being written.
            attempts += 1
            if not attempts % 3:
                self.log(2, 'Failed to pick read location 3 times.')
                coro.sleep_relative(0)
            block_index = random.randint(0, len(self._written)-1)
            pos, size = self._written[block_index]
            area = (pos, pos+size)
            if self._write_locks.search(area):
                self.log(2, 'reader skipping write lock %r', area)
            else:
                self._written.pop(block_index)
                break

        self._read_locks.insert(area)
        return pos, size, area

    def _writer(self, writer_num):
        selfish_acts = 1
        self._num_live_writers += 1
        self.writer_status[writer_num] = 'Starting.'
        try:
            while 1:
                if coro.get_now() > self._start_time + self.options.duration*coro.ticks_per_sec:
                    self.writer_status[writer_num] = 'Finished.'
                    return
                if not selfish_acts % self.options.greediness:
                    self.writer_status[writer_num] = 'Greediness sleep.'
                    coro.sleep_relative(0)
                self.writer_status[writer_num] = 'Getting area to write.'
                pos, size, area = self._get_to_write()

                self.log(3, '%i: write(%i, %i)', writer_num, size, pos)
                data = t_aio.make_data(pos, size)
                try:
                    if random.random() < self.options.cancel_percent/100.0:
                        try:
                            self.writer_status[writer_num] = 'Writing with cancel.'
                            num_written = coro.with_timeout(0, coro.aio_write, self._fd, data, long(pos))
                        except coro.TimeoutError:
                            self._write_cancel_success += 1
                        else:
                            self._written.append((pos, size))
                            self._write_cancel_fail += 1
                    else:
                        self.writer_status[writer_num] = 'Writing.'
                        num_written = coro.aio_write(self._fd, data, long(pos))
                        if num_written != size:
                            self.log(0, 'ERROR: Failed to write %i bytes (%i written).' % (size, num_written))
                            self._assertion_errors += 1
                        else:
                            self._written.append((pos, size))
                finally:
                    self._write_locks.delete(area)
                selfish_acts += 1
                #print len(self._written)
                self._writes_finished += 1
                self._bytes_written += size
        finally:
            self._worker_semaphore.release()
            self._num_live_writers -= 1

    def _have_blocks_to_read(self):
        if len(self._written) == 0:
            self.log(3, 'Reader has nothing to do.')
            return False
        # Because we can read faster than we can write, we do not want
        # the amount of available data to fall too low.
        if len(self._written) < self.options.reader_delay/2 and self._num_live_writers:
            self.log(3, 'Reader is backing off.')
            return False
        return True

    def _reader(self, reader_num):
        selfish_acts = 1
        self.reader_status[reader_num] = 'Starting.'
        try:
            while 1:
                if coro.get_now() > self._start_time + self.options.duration*coro.ticks_per_sec:
                    self.reader_status[reader_num] = 'Finished.'
                    return
                if not selfish_acts % self.options.greediness:
                    self.reader_status[reader_num] = 'Greediness sleep.'
                    coro.sleep_relative(0)
                if not self._have_blocks_to_read():
                    self.reader_status[reader_num] = 'Sleeping, waiting for writers to catch up.'
                    coro.sleep_relative(0.1)
                    continue
                pos, size, area = self._get_to_read()

                self.log(3, '%i: read(%i, %i)', reader_num, size, pos)
                try:
                    if random.random() < self.options.cancel_percent/100.0:
                        try:
                            self.reader_status[reader_num] = 'Reading with cancel.'
                            data = coro.with_timeout(0, coro.aio_read, self._fd, size, long(pos))
                        except coro.TimeoutError:
                            self._read_cancel_success += 1
                        else:
                            self._read_cancel_fail += 1
                    else:
                        self.reader_status[reader_num] = 'Reading.'
                        data = coro.aio_read(self._fd, size, long(pos))
                        expected_data = t_aio.make_data(pos, size)
                        if data != expected_data:
                            self._assertion_errors += 1
                            self.log(0, 'ERROR: data read=%i expected=%i pos=%i', len(data), size, pos)
                            fname = tempfile.mktemp()
                            f = open(fname, 'w')
                            f.write(data)
                            f.close()
                            self.log(0, 'Wrote temp file %s', fname)
                finally:
                    self._read_locks.delete(area)
                selfish_acts += 1
                self._reads_finished += 1
                self._bytes_read += size
        finally:
            self._worker_semaphore.release()

    def _lio(self, worker_num):
        selfish_acts = 1
        self._num_live_writers += 1
        self.lio_status[worker_num] = 'Starting.'
        try:
            while 1:
                if coro.get_now() > self._start_time + self.options.duration*coro.ticks_per_sec:
                    self.lio_status[worker_num] = 'Finished.'
                    return
                if not selfish_acts % self.options.greediness:
                    self.lio_status[worker_num] = 'Greediness sleep.'
                    coro.sleep_relative(0)
                num_events = random.randint(self.options.min_lio, self.options.max_lio)
                requests = []
                reads_to_unlock = []
                writes_to_unlock = []
                self.log(3, '%i: lio(%i)', worker_num, num_events)
                if self._have_blocks_to_read():
                    do_read = random.randint(0, 1)
                else:
                    do_read = False
                if do_read:
                    expected_result = []
                else:
                    expected_result = 0

                for unused in xrange(num_events):
                    if do_read:
                        if not self._have_blocks_to_read():
                            # Skip the rest of the reads.
                            continue
                        self.lio_status[worker_num] = 'Getting area to read.'
                        pos, size, area = self._get_to_read()
                        requests.append((self._fd, pos, size))
                        data = t_aio.make_data(pos, size)
                        expected_result.append(data)
                        self.log(3, '%i: lio_read(%i, %i)', worker_num, size, pos)
                        reads_to_unlock.append(area)
                        lio_op = coro.lio_read
                    else:
                        self.lio_status[worker_num] = 'Getting area to write.'
                        pos, size, area = self._get_to_write()
                        data = t_aio.make_data(pos, size)
                        requests.append((self._fd, pos, data))
                        expected_result += size
                        self.log(3, '%i: lio_write(%i, %i)', worker_num, size, pos)
                        writes_to_unlock.append(area)
                        lio_op = coro.lio_write

                try:
                    if random.random() < self.options.cancel_percent/100.0:
                        try:
                            if do_read:
                                self.lio_status[worker_num] = 'Doing LIO READ with cancel.'
                            else:
                                self.lio_status[worker_num] = 'Doing LIO WRITE with cancel.'
                            result = coro.with_timeout(0, lio_op, requests)
                        except coro.TimeoutError:
                            self._write_cancel_success += 1
                            continue
                        else:
                            self._write_cancel_fail += 1
                    else:
                        if do_read:
                            self.lio_status[worker_num] = 'Doing LIO READ.'
                        else:
                            self.lio_status[worker_num] = 'Doing LIO WRITE.'
                        result = lio_op(requests)
                finally:
                    for area in reads_to_unlock:
                        self._read_locks.delete(area)
                    for area in writes_to_unlock:
                        self._write_locks.delete(area)

                if do_read:
                    if len(result) != len(expected_result):
                        self.log(0, 'ERROR: Length of result (%i) is not expected (%i).', len(result), len(expected_result))
                        continue

                    for result_value, expected_value in zip(result, expected_result):
                        if result_value != expected_value:
                            self.log(0, 'ERROR: Expected read of %i bytes, got %i bytes not equal.', len(expected_value), len(result_value))
                        else:
                            self._reads_finished += 1
                            self._bytes_read += len(expected_value)
                else:
                    # doing a write, return value is just an integer.
                    if result != expected_result:
                        self.log(0, 'ERROR: Result from write (%i) not expected (%i).', result, expected_result)
                        continue
                    else:
                        self._writes_finished += 1
                        self._bytes_written += expected_result
                        self._written.append((pos, size))

        finally:
            self._num_live_writers -= 1
            self._worker_semaphore.release()


    def prep(self):
        size = self.options.blocks*self.options.block_size
        self.log(1, 'Writing out %i bytes.', size)
        # Not sure if we should have a command-line flag to try with or without
        # O_DIRECT.  Not sure if it makes a difference.
        # XXX: Add O_FSYNC for testing.
        self._fd = os.open(self.path, os.O_RDWR|os.O_DIRECT|os.O_FSYNC)
        block = '\0'*1024*1024
        num_blocks = size/len(block)
        for unused in xrange(num_blocks):
            os.write(self._fd, block)
        # Write any partial data.
        partial_size = size % len(block)
        if partial_size:
            os.write(self._fd, block[:partial_size])

    def print_status(self, unused=None):
        print 'Main thread status: %s' % (self.main_thread_state,)
        print 'Current read pool size: %i' % (len(self._written),)
        if self.writer_status:
            print 'Writer status:'
            items = self.writer_status.items()
            items.sort()
            for i, status in items:
                print '%i: %s' % (i, status)
        if self.reader_status:
            print 'Reader status:'
            items = self.reader_status.items()
            items.sort()
            for i, status in items:
                print '%i: %s' % (i, status)
        if self.lio_status:
            print 'LIO status:'
            items = self.lio_status.items()
            items.sort()
            for i, status in items:
                print '%i: %s' % (i, status)

if __name__ == '__main__':
    t = TestAIO()
    coro.set_print_exit_string(False)
    coro.install_signal_handlers = 0
    bd_path = comm_path.mk_backdoor_path('test_aio_lio')
    coro.spawn(backdoor.serve, unix_path = bd_path).set_name('backdoor')
    coro.signal_handler.register_signal_handler (signal.SIGINT, shutdown)
    coro.signal_handler.register_signal_handler (signal.SIGTERM, shutdown)
    coro.signal_handler.register_signal_handler (signal.SIGHUP, t.print_status)
    coro.spawn(t.main)
    coro.event_loop()
