# -*- Mode: Python -*-

import getrusage
import string

def format_rusage (l):
    times = map (lambda x: "%ld %ld" % x, l[:3])
    nums = (
        "maxrss:%d "
        "ixrss:%d "
        "idrss:%d "
        "isrss:%d "
        "minflt:%d "
        "majflt:%d "
        "nswap:%d "
        "inblock:%d "
        "oublock:%d "
        "msgsnd:%d "
        "msgrcv:%d "
        "nsignals:%d "
        "nvcsw:%d "
        "nivcsw:%d" % tuple(l[3:])
    )
    return string.join (times + [nums], '|')

def diff_timeval (a, b):
    r = [0, 0]
    r[0] = b[0] - a[0]
    r[1] = b[1] - a[1]
    if (r[1] < 0):
        r[0] -= 1
        r[1] += 1000000
    return tuple(r)

def diff_rusage (a, b):
    rrt, rut, rst = map (diff_timeval, a[:3], b[:3])
    return (
        rrt,
        rut,
        rst,
        b[3],           # maxrss
        b[4],           # ixrss
        b[5],           # idrss
        b[6],           # isrss
        b[7] - a[7],    # minflt
        b[8] - a[8],    # majflt
        b[9] - a[9],    # nswap
        b[10] - a[10],    # inblock
        b[11] - a[11],  # oublock
        b[12] - a[12],  # msgsnd
        b[13] - a[13],  # msgrcv
        b[14] - a[14],  # nsignals
        b[15] - a[15],  # nvcsw
        b[16] - a[16],  # nivcsw
    )

class real_timer:
    def __init__ (self):
        self.start = getrusage.getrusage()

    def mark (self):
        self.start = getrusage.getrusage()

    def bench (self):
        now = getrusage.getrusage()
        return diff_rusage (self.start, now)

def dump_stats_by_line():
    import sys
    d = sys.statistical_profiling_data.items()
    d.sort (lambda a, b: cmp(b[1], a[1]))
    for (co, line), count in d[:100]:
        print '%6d %s:%s:%s' % (count, co.co_filename, co.co_name, line)

def dump_stats_by_fun():
    import sys
    d = sys.statistical_profiling_data.items()
    d2 = {}
    for (co, line), count in d:
        n = d2.get (co, 0)
        d2[co] = count + n
    d2 = d2.items()
    d2.sort (lambda a, b: cmp(b[1], a[1]))
    for co, count in d2[:100]:
        print '%6d %s:%s' % (count, co.co_filename, co.co_name)
