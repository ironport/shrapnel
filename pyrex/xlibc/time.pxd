# -*- Mode: Cython -*- 

cdef extern from "time.h":
    ctypedef long time_t
    ctypedef long suseconds_t

    cdef struct tm:
        int tm_sec
        int tm_min
        int tm_hour
        int tm_mday
        int tm_mon
        int tm_year
        int tm_wday
        int tm_yday
        int tm_isdst
        char *tm_zone
        long tm_gmtoff

    char * ctime(time_t *clock)
    tm * localtime(time_t *clock)
    tm * gmtime(time_t *clock)
    size_t strftime(char * buf, size_t maxsize, char * format, tm * timeptr)
    time_t mktime(tm *)


cdef extern from "sys/time.h":
    cdef struct timeval:
        time_t      tv_sec
        suseconds_t tv_usec

    cdef struct timezone:
        int tz_minuteswest
        int dsttime

    int gettimeofday(timeval *tp, timezone *tzp)
