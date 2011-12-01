import os
import resource

def verify_limit(name, minval):
    current_soft_value, current_hard_value = resource.getrlimit(name)
    if current_soft_value < minval:
        if current_hard_value >= minval:
            # reset it
            resource.setrlimit(name, (minval, current_hard_value))
        else:
            # root can raise the hard limit...let's try
            try:
                resource.setrlimit(name, (minval, minval))
            except ValueError:
                raise SystemError, "The ulimit '%i' has value '%d', which is less than the required minimum value of '%d'...tried to raise but failed." % (name, current_soft_value, minval)
        # check again, just to make sure changes took
        current_soft_value, current_hard_value = resource.getrlimit(name)
        if current_soft_value < minval:
            raise SystemError, "The ulimit '%i' has value '%d', which is less than the required minimum value of '%d'" % (name, current_soft_value, minval)


# The (soft limit) values that we expect
resource_minimums = {
    resource.RLIMIT_CPU:    resource.RLIM_INFINITY,
    resource.RLIMIT_FSIZE:  resource.RLIM_INFINITY,
    resource.RLIMIT_DATA:   2093056,                    # 2 gigs of memory
    resource.RLIMIT_STACK:  65536,
    # we can run just fine with a corelimit...but we may want to enable this
    # or we may not, if in the future we want to set the value to 0
#    resource.RLIMIT_CORE:   resource.RLIM_INFINITY,
    # this may not be necessary because we (AFAIK) never lock any memory
    resource.RLIMIT_MEMLOCK:    resource.RLIM_INFINITY,
    resource.RLIMIT_NOFILE:     16000,
    # this may not be necessary because we do not fork very many processes
    resource.RLIMIT_NPROC:      500,
    resource.RLIMIT_RSS:        resource.RLIM_INFINITY,
    resource.RLIMIT_SBSIZE:     resource.RLIM_INFINITY,
}

def verify():
    if not os.environ.get("BUILDING"):
        for name, minval in resource_minimums.items():
            verify_limit (name, minval)

if __name__=='__main__':
    verify()
