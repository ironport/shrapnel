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

import sysctl
import struct

# see /usr/include/sys/devicestat.h

devstat_format = (
    # struct devstat {
    'II'  # STAILQ_ENTRY(devstat)   dev_links;
    'I'   # u_int32_t               device_number;       // Devstat device number.
    '16s'  # char                    device_name[DEVSTAT_NAME_LEN];
    'i'   # int                     unit_number;
    'q'   # u_int64_t               bytes_read;          //  Total bytes read from a device.
    'q'   # u_int64_t               bytes_written;       //  Total bytes written to a device.
    'q'   # u_int64_t               bytes_freed;         //  Total bytes freed from a device.
    'q'   # u_int64_t               num_reads;           //  Total number of read requests to the device.
    'q'   # u_int64_t               num_writes;          //  Total number of write requests to the device.
    'q'   # u_int64_t               num_frees;           //  Total number of free requests to the device.
    'q'   # u_int64_t               num_other;           //  Total number of transactions that don't read or write data.
    'i'   # int32_t                 busy_count;          //  Total number of transactions outstanding for the device.
    'I'   # u_int32_t               block_size;          //  Block size, bytes
    # u_int64_t               tag_types[3];        //  The number of simple, ordered, and head of queue tags sent.
    'qqq'
    'II'  # struct timeval          dev_creation_time;   //  Time the device was created.
    'II'  # struct timeval          busy_time;           //  Total amount of time drive has spent processing requests.
    # struct timeval          start_time;          //  The time when
    # busy_count was last == 0.  Or, the start of the latest busy period.
    'II'
    'II'  # struct timeval          last_comp_time;      //  Last time a transaction was completed.
    '8s'
    #       devstat_support_flags   flags;               //  Which statistics are supported by a given device.
    #       devstat_type_flags      device_type;         //  Device type
    #       devstat_priority        priority;            //  Controls list pos.
    # };
)

def fix_zt_string (s):
    return s[:s.index('\000')]

devstat_size = struct.calcsize (devstat_format)

class devstat_struct:

    def cleanup (self):
        self.device_name = fix_zt_string (self.device_name)

    def pprint (self):
        import pprint
        pprint.pprint (self.__dict__)

def devstat():
    if sysctl.sysctl ('kern.devstat.version', 1) != 4:
        raise SystemError("devstat(9) version has changed")
    data = sysctl.sysctl ('kern.devstat.all', 0)
    devices = {}
    for i in range (0, len(data), devstat_size):
        sub = data[i:i + devstat_size]
        if len(sub) != devstat_size:
            # there are an extra four bytes tacked on to the end.
            # don't know what they're about.  padding?  They always
            # seem to be ' \000\000\000'
            break
        else:
            info = struct.unpack (devstat_format, sub)
            ds = devstat_struct()
            (ds.dev_links0, ds.dev_links1,
             device_number, ds.device_name, ds.unit_number,
             ds.bytes_read, ds.bytes_written, ds.bytes_freed,
             ds.num_reads, ds.num_writes, ds.num_frees, ds.num_other,
             ds.busy_count, ds.block_size,
             ds.tag_types0, ds.tag_types1, ds.tag_types2,
             ds.dev_creation_time0, ds.dev_creation_time1,
             ds.busy_time0, ds.busy_time1,
             ds.start_time0, ds.start_time1,
             ds.last_comp_time0, ds.last_comp_time1,
             enums
             ) = info
            ds.cleanup()
            devices[ds.device_name] = ds
    return devices

def devstat_print_all():
    d = sorted(devstat().items())
    for k, v in d:
        print '---', k, '---'
        v.pprint()

if __name__ == '__main__':
    devstat_print_all()
