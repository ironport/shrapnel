
Logging Subsystem
=================

Goals:

1. performance (string formatting is avoided)
2. simplicity
3. machine-readable (log processing becomes trivial).

Binary Logging
--------------

I have worked on many projects over the years that involve processing
logs, sometimes *HUGE* amounts of logs.  It's very frustrating parsing
free-formatted, whatever-the-developer-felt-like-writing log files
into useful data.  Binary logging steps around the problem by making
the logs machine readable from the start.

You can also instantiate a ``FileLogger`` that will do plain-text logging,
but using the same API.

If you do nothing
-----------------

By default logs are sent to stderr.


Interface
---------

The log-function interface differs from most in that it accepts a
sequence of data items, not a string.  On a heavily loaded server this saves
CPU by not formatting log lines (especially when they are not going to be
used because of log levels).  When a server is emitting thousands of log lines
per second, the CPU impact can be considerable.

So instead of:

```python
LOG ("blert: thing1: %d thing2: %d" % (v0, v1))
```

You do:

```python
LOG ('blert', v0, v1)
```

Reading the Logs
----------------

In the ``scripts`` directory you will find ``catlog``, which will process
either stdin, or a path arg.  It can synchronize with the output of
``tail``, or ``tail -f``.

Log Levels
----------

I intend to add a layer that supports log levels, backward compatible
with this code, in that the first item of '*data' will be an integer
log level.

Module-Level Logging
--------------------

To use module-level logging:

Setup:

```python
    if args.logfile:
        logger = coro.log.asn1.Logger (open (args.logfile, 'wb'))
    else:
        logger = coro.log.StderrLogger()
    coro.log.set_logger (logger)
    coro.log.redirect_stderr()
```


Usage within a module:

```python

from coro.log import Facility
LOG = Facility ('db')

[...]

    def query (self, q):
        LOG ('query', q)
        [...]
	
```

Single-module scripts:

```python
from coro.log import NoFacility
LOG = NoFacility()
```

Logging exceptions:

```python
def test():
    try:
        1/0
    except ZeroDivisionError:
        LOG.exc()
```
