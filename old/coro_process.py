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

"""Process management for a coroutine environment.

This module provides methods for dealing with processes that will use the
kqueue facility from coro to cooperate with other coro threads.

All functions that may raise OSError will raise an errno-specific instance from
the `oserrors` module.
"""

import errno
import os
import signal

import _process
import coro
import process
from _process import DEV_NULL, PIPE, STDOUT
from process import AbnormalExit

class ProcessTimeout(Exception):

    """Process did not finish in time.

    :IVariables:
        - `stdout_output`: The output received so far.
        - `stderr_output`: The output received so far.  (None for `capture`.)
    """

    def __init__(self, stdout_output, stderr_output):
        self.stdout_output = stdout_output
        self.stderr_output = stderr_output
        Exception.__init__(self)


def capture(command, tie_out_err=True, cwd=None, env=None, timeout=0, pgrp=0):
    """Run a program in the background and capture its output.

    :Parameters:
        - `command`: The command to execute.  If it is a string, it will be
          parsed for command-line arguments.  Otherwise it assumes it is a
          sequence of arguments, with the first element being the command to
          execute.

          If the command does not contain a slash (/) it will search the PATH
          environment for the executable.
        - `tie_out_err`: If true, it will also capture output to stderr. If
          False, stderr output will go to ``/dev/null``.
        - `cwd`: Change the working directory to this path if specified before
          executing the program.
        - `env`: The environment to use.  If None, the environment is not
          changed.  May be a dictionary or a list of 'NAME=VALUE' strings.
        - `timeout`: If specified, will use a coro timeout to ensure that the
          process returns within the specified length of time.  If it does not,
          it is forcefully killed (with SIGKILL) and `ProcessTimeout` is
          raised.
        - `pgrp`: Set to -1 to keep process group unchanged, 0 to create a new
          job (default) and >0 to set process group to pgrp

    :Return:
        Returns a tuple ``(status, output)``.  Status is a
        `process.ExitStatus` instance.  Output is a string.

    :Exceptions:
        - `OSError`: Generic system error.
        - `ValueError`: The command value is invalid.
        - `ProcessTimeout`: The process did not return within `timeout`
          seconds.
    """
    if tie_out_err:
        stderr = STDOUT
    else:
        stderr = DEV_NULL
    p = spawn_job_bg(command, stdin=DEV_NULL, stdout=PIPE, stderr=stderr, cwd=cwd, env=env, pgrp=pgrp)
    status = None
    result = []

    def do_read():
        while 1:
            block = p.stdout.read(1024)
            if block:
                result.append(block)
            else:
                break
        return p.wait()

    try:
        if timeout:
            status = coro.with_timeout(timeout, do_read)
        else:
            status = do_read()
    except BaseException, e:
        try:
            p.killpg(signal.SIGKILL)
        except OSError, kill_exc:
            if kill_exc.errno != errno.ESRCH:
                raise
        # Make sure we clean up the zombie.
        coro.spawn(p.wait)
        if isinstance(e, coro.TimeoutError):
            raise ProcessTimeout(''.join(result), None)
        else:
            raise

    return status, ''.join(result)

def capture_with_stderr(command, cwd=None, env=None, timeout=0, pgrp=0):
    """Run a program in the background and capture its output.

    stdout and stderr are captured independently.

    :Parameters:
        - `command`: The command to execute.  If it is a string, it will be
          parsed for command-line arguments.  Otherwise it assumes it is a
          sequence of arguments, with the first element being the command to
          execute.

          If the command does not contain a slash (/) it will search the PATH
          environment for the executable.
        - `cwd`: Change the working directory to this path if specified before
          executing the program.
        - `env`: The environment to use.  If None, the environment is not
          changed.  May be a dictionary or a list of 'NAME=VALUE' strings.
        - `timeout`: If specified, will use a coro timeout to ensure that the
          process returns within the specified length of time.  If it does not,
          it is forcefully killed (with SIGKILL) and `ProcessTimeout` is
          raised.
        - `pgrp`: Set to -1 to keep process group unchanged, 0 to create a new
          job (default) and >0 to set process group to pgrp

    :Return:
        Returns a tuple ``(status, stdout_output, stderr_output)``.  Status is an
        `ExitStatus` instance.  The outputs are strings.

    :Exceptions:
        - `OSError`: Generic system error.
        - `ValueError`: The command value is invalid.
        - `ProcessTimeout`: The process did not return within `timeout`
          seconds.
    """
    status = None
    stdout_result = []
    stderr_result = []

    finished_sem = coro.inverted_semaphore(2)

    p = spawn_job_bg(command, stdin=DEV_NULL, stdout=PIPE, stderr=PIPE, cwd=cwd, env=env, pgrp=pgrp)

    def do_read(s, result):
        while 1:
            block = s.read(1024)
            if block:
                result.append(block)
            else:
                break
        finished_sem.release()

    def do_work():
        finished_sem.block_till_zero()
        return p.wait()

    try:
        coro.spawn(do_read, p.stdout, stdout_result)
        coro.spawn(do_read, p.stderr, stderr_result)
        if timeout:
            status = coro.with_timeout(timeout, do_work)
        else:
            status = do_work()
    except BaseException, e:
        try:
            p.killpg(signal.SIGKILL)
        except OSError, kill_exc:
            if kill_exc.errno != errno.ESRCH:
                raise
        # Make sure we clean up the zombie.
        coro.spawn(p.wait)
        if isinstance(e, coro.TimeoutError):
            raise ProcessTimeout(''.join(stdout_result), ''.join(stderr_result))
        else:
            raise

    return status, ''.join(stdout_result), ''.join(stderr_result)


def spawn_job_bg(command, stdin=DEV_NULL, stdout=DEV_NULL, stderr=DEV_NULL, fd_except=None, cwd=None, env=None, pgrp=0):
    """Spawn a job into the background.

    :Parameters:
        - `command`: The command to execute.  If it is a string, it will be
          parsed for command-line arguments.  Otherwise it assumes it is a
          sequence of arguments, with the first element being the command to
          execute.

          If the command does not contain a slash (/) it will search the PATH
          environment for the executable.
        - `stdin`: Either `DEV_NULL` or `PIPE`.
        - `stdout`: Either `DEV_NULL` or `PIPE`.
        - `stderr`: Either `DEV_NULL`, `PIPE`, or `STDOUT`.
        - `fd_except`: A list of file descriptors to NOT close.  By default all
          file descriptors (except for stdin/stdout/stderr are closed).
        - `cwd`: The working directory to use for the child process (the
          default is to leave it alone).
        - `env`: The environment to use.  If None, the environment is not
          changed.  May be a dictionary or a list of 'NAME=VALUE' strings.
        - `pgrp`: Set to -1 to keep process group unchanged, 0 to create a new
          job (default) and >0 to set process group to pgrp

    :Return:
        Returns a `CoroProcess` instance.

    :Exceptions:
        - `OSError`: General low-level error.
        - `ValueError`: The command value is invalid.
    """
    pid, in_fd, out_fd, err_fd = _process.spawn_job_bg(command, stdin, stdout, stderr, fd_except, cwd, env, pgrp)
    if in_fd != -1:
        in_file = coro.fd_sock(in_fd)
    else:
        in_file = None
    if out_fd != -1:
        out_file = coro.fd_sock(out_fd)
    else:
        out_file = None
    if err_fd == out_fd:
        err_file = out_file
    elif err_fd != -1:
        err_file = coro.fd_sock(err_fd)
    else:
        err_file = None

    return CoroProcess(command, pid, in_file, out_file, err_file)

class CoroProcess(process.Process):

    def _waitpid(self, options):
        if options and options & ~os.WNOHANG:
            # Currently kqueue does not appear to support job-control notices.
            # Anyone know how to fix that?
            raise AssertionError('No options besides WNOHANG are supported for coro processes.')
        if options & os.WNOHANG:
            return os.waitpid(self.pid, os.WNOHANG)
        else:
            return coro.waitpid(self.pid)
