# -*- Mode: Python -*-

"""Verify that system resource values are set appropriately for heavy-duty benchmarking.
   Some of these values can be set (using 'sysctl') on a live system.  Some can be set
   in /boot/loader.conf.  Some (but not all!) can be changed in the kernel config as well.

   Our position is going to be this:
     1) prefer /boot/loader.conf over kernel config
        [this is because at least one value (TCBHASHSIZE) can't be set in the kernel
         config but *can* be set from loader.conf]
     2) prefer /etc/sysctl.conf to changing things manually

"""

import os
import sysctl
import tb

def verify_resource (name, minval):
    try:
        x = sysctl.sysctl (name, 1)
    except:
        raise SystemError("Failed to query sysctl MIB '%s': %s" % (name, tb.traceback_string()))
    else:
        if x < minval:
            raise SystemError(
                "The sysctl MIB '%s' has value '%d', which is less than the required minimum value of '%d'" %
                (name, x, minval))

resource_minimums = {
    "kern.maxfiles": 16384,        # /etc/sysctl.conf
    "kern.maxfilesperproc": 16000,        # /etc/sysctl.conf
    "kern.ipc.somaxconn": 8192,        # /etc/sysctl.conf
    "kern.ipc.nmbufs": 65536,        # /boot/loader.conf
    "kern.ipc.nmbclusters": 16384,        # /boot/loader.conf
    "net.inet.ip.portrange.last": 49151,        # /etc/sysctl.conf
    "net.inet.tcp.tcbhashsize": 16384,        # /boot/loader.conf
    "net.inet.ip.intr_queue_maxlen": 200,        # /etc/sysctl.conf
    # "machdep.tsc_freq"              :     0,        # see kernel config and rdtsc.h
}

def verify():
    if not os.environ.get("BUILDING"):
        for name, minval in resource_minimums.items():
            verify_resource (name, minval)

if __name__ == '__main__':
    verify()
