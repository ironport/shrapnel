# -*- Mode: Python -*-

# SMR: I believe this was written by Larry Rosenstein circa 2003?

# Note: this code could use some modernization.
# * latency will be high because of the query/response model

import exceptions
import re
import socket
import string
import struct
import sys
import time
import types

import coro

W = coro.write_stderr
P = coro.print_stderr

MAX_RECONNECT_RETRY   = 10.0
RECONNECT_RETRY_GRAIN = 0.1
DEFAULT_RECV_SIZE     = 0x8000
POSTGRES_HEADER_SIZE     = 0x5  # 1-byte message type; 4-byte length

# large object mode constants

INV_WRITE = 0x00020000
INV_READ = 0x00040000

SEEK_SET = 0
SEEK_CUR = 1
SEEK_END = 2

# ===========================================================================
# Protocol logging; saves data in memory to avoid changing thread
# scheduling behavior, etc.
# ===========================================================================
DATA = None
DATAP = 0
DATAX = 0

def LOG(data, seq=None):
    global DATA, DATAP, DATAX

    if DATA is None:
        DATA = [''] * 5000
    DATAX += 1
    if not seq:
        seq = DATAX

    # coro.print_stderr("%d: DATA[%d] = %s\n" % (DATAX, DATAP, data[:30]))
    DATA[DATAP] = '%d: %s' % (seq, data)
    DATAP += 1
    if DATAP >= len(DATA):
        DATAP = 0

    return seq

def DUMPLOG(n):
    import pprint
    global DATA, DATAP

    f = open(n, 'w')
    reordered = DATA[DATAP:] + DATA[:DATAP]
    pprint.pprint((DATAP, DATAX), f)
    pprint.pprint(reordered, f)
    f.close()

# ===========================================================================
# Exceptions
# ===========================================================================

class PostgresError(exceptions.Exception):
    """Base class of all exceptions raised here."""
    pass

class BackendError(PostgresError):
    """Exception sent by backend; includes error_field dictionary
    that contains details."""

    def __init__(self, msg, error_data=None):
        PostgresError.__init__(self, msg)

        if isinstance(error_data, types.DictType):
            self.error_fields = error_data.copy()
        elif error_data:
            self.error_fields = unpack_error_data(error_data)
        else:
            self.error_fields = {}

    def error_code(self):
        return self.error_fields.get(PG_SQLSTATE_FIELD)

    def __str__(self):
        return "%s (%s %s: %s)" % (
            self.args[0],
            self.error_fields.get(PG_SEVERITY_FIELD, 'UNKNOWN'),
            self.error_fields.get(PG_SQLSTATE_FIELD, '?????'),
            self.error_fields.get(PG_MESSAGE_FIELD, '-----'))

class ConnectError(BackendError):
    pass

class QueryError(BackendError):
    pass

class FunctionError(BackendError):
    pass


class ConnectionClosedError(PostgresError):
    pass

class InternalError(PostgresError):
    """Unexpected condition inside the library."""
    pass


# ===========================================================================
# String Quoting
# ===========================================================================

_std_split_re = re.compile('''([\x00-\x1f\\\\'\x7f-\xff]+)''')
_std_char_quote = {
    '\000': '',
    '\\': '\\\\',
    "'": "\\'",
    '\r': '\\r',
    '\n': '\\n',
    '\b': '\\b',
    '\f': '\\f',
    '\t': '\\t',
}

_array_split_re = re.compile('''([\x00-\x1f\\\\'"\x7f-\xff]+)''')  # add double quote
_array_char_quote = _std_char_quote.copy()
_array_char_quote['\\'] = '\\\\\\\\'
_array_char_quote['"'] = '\\\\"'

_copy_split_re = re.compile('''([\x00-\x1f\\\\\x7f-\xff]+)''')
_copy_char_quote = _std_char_quote.copy()
del _copy_char_quote["'"]

def _std_quote_char(c):
    quoted = _std_char_quote.get(c)
    if quoted is not None:
        return quoted
    elif ord(c) < ord(' '):
        return '\\%03o' % ord(c)
    else:
        return c

def _array_quote_char(c):
    quoted = _array_char_quote.get(c)
    if quoted is not None:
        return quoted
    elif ord(c) < ord(' '):
        return '\\\\\\\\%03o' % ord(c)
    else:
        return c

_copy_quote_char = _std_quote_char

def quote_string(s):
    return _quote_string(s, "'", _std_split_re, _std_quote_char)

def quote_string_array(s):
    return _quote_string(s, '"', _array_split_re, _array_quote_char)

def quote_string_copy(s):
    return _quote_string(s, "", _copy_split_re, _copy_quote_char)

def _quote_string(s, delim, splitter, quoter):
    parts = splitter.split(s)
    for i in xrange(1, len(parts), 2):
        # even elements are OK; odd elements need conversion
        parts[i] = ''.join(map(quoter, parts[i]))

    # reconstitute string with the proper delimiters
    return "%s%s%s" % (delim, ''.join(parts), delim)

_like_split_re = re.compile('''([%_\\\\]+)''')
def _like_quote_char(c):
    return '\\' + c

def escape_like_string(s):
    """Escape characters in an LIKE/ILIKE match string."""
    return _quote_string(s, "", _like_split_re, _like_quote_char)

def _bytea_quote_char(c):
    return r'\\%03o' % ord(c)

def quote_bytea(s):
    return _quote_string(s, "'", _std_split_re, _bytea_quote_char)


# Regex that finds all utf-8 sequences representing characters
# >= U+10000.  (Technically, this finds all 4-byte utf-8 sequences,
# which is more than is actually allowed in utf-8.  Normally, 4-byte
# sequences must start with 0xf0-0xf4.)
#
_4_byte_utf8_re = re.compile(r'[\xf0-\xf7]...')

# Unicode replacement char in utf-8
_replacement_char_utf8 = u'\ufffd'.encode('utf-8')

def scrub_utf8(s):
    """Replace characters >= U+10000 with U+FFFD.

    Related to bug 35006 (and others).  Postgres can't handle Unicode
    characters outside the Basic Multilingual Plane (>= U+10000).
    Replace them # with REPLACEMENT CHARACTER U+FFFD.

    This doesn't do a lot of checks on the original string; it is
    assumed to be valid utf-8.
    """

    return _4_byte_utf8_re.sub(_replacement_char_utf8, s)


# ===========================================================================
# Client class
# ===========================================================================

class postgres_client:
    # connection states
    DISCONNECTED = 'disconnected'
    CONNECTED = 'connected'
    COPYIN = 'copyin'

    DEFAULT_ADDRESS = '/tmp/.s.PGSQL.5432'
    DEFAULT_USER = 'pgsql'

    def __init__ (self, database, username='', password='', address=None, ssl_context=None):

        self._backend_pid = 0
        self._secret_key = 0  # used for cancellations

        if username:
            self.username = username
        else:
            self.username = self.DEFAULT_USER
        self.password = password
        if address:
            self.address = address
        else:
            self.address = self.DEFAULT_ADDRESS

        self.ssl_context = ssl_context
        self.database  = database
        self.backend_parameters = {}

        self._state = self.DISCONNECTED
        self._socket = None
        self._debug = 0

    def connect(self):
        try:
            if self._state == self.DISCONNECTED:
                try:
                    self._socket = self.connect_socket()
                except (socket.error, OSError, IOError), e:
                    # problem connecting; Postgres probably isn't running
                    # convert this to a common PostgresError exception
                    raise ConnectError((str(e), sys.exc_info()[2]))

                self._startup()
                self._wait_for_backend()

                self._state = self.CONNECTED
        finally:
            # If the state is still DISCONNECTED, then there was problem.
            if self._state == self.DISCONNECTED:
                self._dump_connection()

    def is_connected(self):
        try:
            return (self._socket is not None and
                    self._state != self.DISCONNECTED and
                    self._socket.getpeername() and
                    1)
        except:
            return 0

    def cancel(self):
        """Cancel current operation on this connection.

        This sends a Postgres cancel request packet on a newly-opened
        db connection.  It should not be called directly because
        without external synchronization there's no way to tell what
        operation (if any) is going to be cancelled.

        If the cancel request does something, the thread that
        made the query will get a PostgresError exception with
        code PG_ERROR_QUERY_CANCELLED."""

        if self._state != self.DISCONNECTED:
            socket = self.connect_socket()
            try:
                data = build_message(PG_CANCELREQUEST_MSG,
                                     80877102,
                                     self._backend_pid,
                                     self._secret_key,
                                     )
                socket.send (data)
            finally:
                socket.close()

    def get_pid(self):
        """Return pid of the backend process for this connection.

        Does a database query the first time, and so the caller is
        responsible for ensuring that the connection is not in use."""

        if not self.is_connected():
            self._backend_pid = 0  # throw away cached value
            return 0
        elif not self._backend_pid:
            res = self.query('SELECT pg_backend_pid()')
            if res.ntuples > 0:
                self._backend_pid = res.getvalue(0, 0)

        return self._backend_pid

    def query(self, query):
        return self._simple_query(query)

    def Q (self, query):
        "perform a simple query, return all the results"
        return self._simple_query (query).getallrows()

    def query_timeout(self, query, timeout):
        """Run query with a timeout.

        If the query times out, raise TimeoutError."""

        aq = async_query(self)
        aq.start(query)  # start another thread working

        # Wait for results
        return aq.get_result(timeout)

    def analyze(self, vacuum=True, full=False, table='',
                fake_duplicate_problem=False):
        """Perform an ANALYZE statement.

        This handles the common problem where the pg_statistic table has
        gotten corrupted such that it no longer satisfies the "unique"
        constraint of its index.  This can happen if the database runs
        out of disk space.

        vacuum: whether to turn this into a VACUUM statement
        full: whether to turn this into a VACUUM FULL statement
        table: allows analyzing an individual table
        fake_duplicate_problem: for testing (see below)

        If the SQL statement fails with a violation of a unique
        constraint error, the code removes all the rows from the
        pg_statistic table and tries the command again.

        Since it's not possible to re-create the problem through any
        normal sequence, the caller can simulate the problem by passing
        fake_duplicate_problem=True.
        """

        if full:
            cmd = "VACUUM FULL"
        elif vacuum:
            cmd = "VACUUM"
        else:
            cmd = "ANALYZE"

        # Create the desired command
        sql = """%s %s""" % (cmd, table)
        try:
            if fake_duplicate_problem:
                # Do a simple analyze to ensure there's stat data
                self.query('ANALYZE')

                # Try to insert a duplicate row, which generates the
                # kind of error we're looking for.
                self.query('INSERT INTO pg_statistic SELECT * from pg_statistic LIMIT 1')
                # TODO: raise an exception in case we succeeded?

            self.query(sql)
            return
        except QueryError, e:
            if e.error_code() == PG_ERROR_UNIQUE_VIOLATION:  # Duplicate key
                # This usually means a problem with the pg_statistic table
                # Will retry below...
                P("analyze error (%r)" % (fake_duplicate_problem,))
                pass
            else:
                raise

        # Could find only duplicates, but this table usually is small,
        # and it doesn't look like ANALYZE is any faster if there is
        # existing data.
        try:
            self.query("""DELETE FROM pg_statistic""")
        except PostgresError:
            pass  # don't barf trying to fix pg_statistic

        # Retry.  May still raise an exception, but at this point,
        # there's nothing more to be done about it.
        self.query(sql)

    def putline(self, ln):
        if self._state == self.COPYIN:
            self.send_packet (PG_COPY_DATA_MSG, _ByteN_arg(ln))
        else:
            raise InternalError('Current state (%s) is not %s' % (self._state, self.COPYIN))

    def endcopy(self):
        if self._state == self.COPYIN:
            self.send_packet(PG_COPY_DONE_MSG)

            # now go back to processing backend messages
            self._state = self.CONNECTED
            return self._simple_query(None)
        else:
            pass  # we'll let this slide

    def lo_creat(self, mode):
        fn_oid = self._get_lo_function('lo_creat')
        return self._function_call(fn_oid, mode)

    def lo_open(self, loid, mode):
        fn_oid = self._get_lo_function('lo_open')
        return self._function_call(fn_oid, loid, mode)

    def lo_write(self, fd, data):
        fn_oid = self._get_lo_function('lowrite')
        return self._function_call(fn_oid, fd,
                                   _ByteN_arg(data))

    def lo_read(self, fd, numbytes=0):
        fn_oid = self._get_lo_function('loread')
        if numbytes <= 0:
            # read to end of file
            current_pos = self.lo_tell(fd)
            lo_end = self.lo_lseek(fd, 0, SEEK_END)
            numbytes = lo_end - current_pos

            self.lo_lseek(fd, current_pos, SEEK_SET)

        return self._function_call(fn_oid, fd, numbytes)

    def lo_lseek(self, fd, offset, whence):
        fn_oid = self._get_lo_function('lo_lseek')
        return self._function_call(fn_oid, fd, offset, whence)

    def lo_tell(self, fd):
        fn_oid = self._get_lo_function('lo_tell')
        return self._function_call(fn_oid, fd)

    def lo_close(self, fd):
        fn_oid = self._get_lo_function('lo_close')
        return self._function_call(fn_oid, fd)

    def lo_unlink(self, loid):
        fn_oid = self._get_lo_function('lo_unlink')
        return self._function_call(fn_oid, loid)

    def close(self):
        if self._state != self.DISCONNECTED:
            try:  # best effort at cleanly shutting down
                self.send_packet(PG_TERMINATE_MSG)

                # Make sure the db disconnects, so that if the caller
                # tries to (say) delete the database the system won't
                # report it in use.  (Mostly seen during testing.)
                for unused in xrange(10):
                    if self.is_connected():
                        sleep(0.1)
                    else:
                        break
            except (socket.error, OSError, IOError):
                pass

            self._dump_connection()

    def _dump_connection(self):
        """Throw away the socket, to get to a known state."""

        try:
            if self._socket:
                self._socket.close()
        except (socket.error, OSError, IOError):
            pass

        self._socket = None
        self._backend_pid = 0
        self._state = self.DISCONNECTED

    finish = close  # compatibility with libpq

    def notice_received(self, where, message_fields):
        # print where, message_fields
        pass

# Internal Routines

    def connect_socket(self):
        """Connect to database at self.address.

        Returns socket object and function to send data on the socket.
        Works with TCP and Unix-domain sockets."""

        if isinstance(self.address, type('')):
            sock = coro.unix_sock()
        else:
            sock = coro.tcp_sock()
        sock.connect (self.address)
        return sock

    _debug = 0

    def send_packet (self, message_type, *data_args):
        data = build_message (message_type, *data_args)

        if self._debug:
            print '-->', repr(message_type)
            a, b = dump_hex(data)
            print a
            print b

        self._socket.send (data)

        return None

    def get_header(self):
        header = self._socket.recv_exact (5)
        message_type, length = struct.unpack ('!cL', header)
        return message_type, length - 4  # return length of data only

    def read_packet(self):
        msg, length = self.get_header()
        data = self._socket.recv_exact (length)
        if self._debug:
            print "<--", repr(msg), length, len(data)
            a, b = dump_hex(data)
            print a
            print b
        return msg, data

    def _startup(self):
        """Implement startup phase of Postgres protocol"""

        if self.ssl_context:
            self.send_packet (PG_SSLREQUEST_MSG, 80877103)
            msg = self._socket.recv_exact (1)  # not a normal packet?
            if msg == 'S':
                # willing
                import coro.ssl
                sock = coro.ssl.sock (self.ssl_context, fd=self._socket.fd)
                sock.ssl_connect()
                self._orig_socket = self._socket
                self._socket = sock
            else:
                raise ConnectError ("unable to negotiate TLS")

        # send startup packet
        self.send_packet (
            PG_STARTUP_MSG,
            0x00030000,  # protocol version
            'user', self.username,
            'database', self.database,
            ''  # terminate options
        )

        msg, data = self.read_packet()
        if msg == PG_AUTHENTICATION_OK_MSG:
            tag, = struct.unpack ('!L', data[:4])
            if tag == 0:
                pass  # no password needed
            elif tag == 5:
                salt = data[4:8]
                # SMR: thx to postgres-pr for this!
                m = md5_hex (self.password + self.username)
                m = 'md5' + md5_hex (m + salt)
                self.send_packet (PG_PASSWORD_MESSAGE, m)
            else:
                raise NotImplementedError ("authentication type: %d" % (tag,))
        elif msg == PG_ERROR_MSG:
            raise ConnectError(("_startup", data))
        else:
            raise ConnectError("Authentication required (%d)" % msg)

    def _wait_for_backend(self):
        """Wait for the backend to be ready for a query"""

        while 1:
            msg, data = self.read_packet()

            if msg == PG_READY_FOR_QUERY_MSG:
                return

            elif msg == PG_BACKEND_KEY_DATA_MSG:
                self._backend_pid, self._secret_key = unpack_data (data, 'ii')
                # print "pid=%d, secret=%d" % (self._backend_pid, self._secret_key)

            elif msg == PG_PARAMETER_STATUS_MSG:
                k, v = unpack_data(data, 'ss')
                self._set_parameter(k, v)

            elif msg == PG_ERROR_MSG:
                raise ConnectError(("_wait_for_backend", data))

            elif msg == PG_NOTICE_MSG:
                self._notice(BACKEND_START_NOTICE, data)

            else:
                continue  # ignore packet?

    def _simple_query(self, query):
        """Execute a simple query.

        query can be None, which skips sending the query
        packet, and immediately goes to processing backend
        messages."""

        if query is not None:
            self._exit_copy_mode('New query started')
            self.send_packet(PG_QUERY_MSG, query)

        exception = None
        result = None

        while 1:
            msg, data = self.read_packet()

            if msg == PG_READY_FOR_QUERY_MSG:
                break

            elif msg == PG_COMMAND_COMPLETE_MSG:
                if not result:
                    result = query_results()
                result._command_complete(data)

            elif msg == PG_COPY_IN_RESPONSE_MSG:
                self._state = self.COPYIN
                break  # exit loop so we can accept putline calls

            elif msg == PG_COPY_OUT_RESPONSE_MSG:
                if not exception:
                    exception = InternalError('COPY OUT not supported')
                break

            elif msg == PG_ROW_DESCRIPTION_MSG:
                result = query_results()
                result._row_description(data)

            elif msg == PG_DATA_ROW_MSG:
                if result:
                    result._data_row(data)
                else:
                    if not exception:
                        exception = InternalError(
                            'DataRow message before RowDescription?')

            elif msg == PG_EMPTY_QUERY_RESPONSE_MSG:
                # totally empty query (skip it?)
                continue

            elif msg == PG_PARAMETER_STATUS_MSG:
                k, v = unpack_data(data, 'ss')
                self._set_parameter(k, v)

            elif msg == PG_ERROR_MSG:
                if not exception:
                    exception = QueryError('_simple_query', data)
                    # LOG("QueryError: %r" % exception.error_fields)
                    # coro.print_stderr("QueryError: %r\n" % exception.error_fields)

            elif msg == PG_NOTICE_MSG:
                self._notice(QUERY_NOTICE, data)

            else:
                continue  # ignore packet?

        if exception:
            raise exception

        return result

    def _exit_copy_mode(self, msg='_exit_copy_mode'):
        if self._state == self.COPYIN:
            self.send_packet(PG_COPY_FAIL_MSG, msg)

    def _set_parameter(self, key, value):
        self.backend_parameters[key] = value
# print "Parameter: %s=%s" % (k, v)

    def _notice(self, where, data):
        self.notice_received(where, unpack_notice_data(data))

    def _get_lo_function(self, name):
        global _lo_functions

        if not _lo_functions:
            res = self._simple_query(
                """select proname, oid from pg_proc
                   where proname='lo_open' or
                         proname='lo_close' or
                         proname='lo_creat' or
                         proname='lo_unlink' or
                         proname='lo_lseek' or
                         proname='lo_tell' or
                         proname='loread' or
                         proname='lowrite'""")
            fns = {}
            for i in xrange(res.ntuples):
                fns[res.getvalue(i, 0)] = res.getvalue(i, 1)

            _lo_functions = fns

        fn = _lo_functions.get(name)
        if fn:
            return fn
        else:
            raise InternalError('Failed to get %s function oid' % name)

    def _function_call(self, fn_oid, *args):
        """Execute a function call."""

        # Construct the arguments for the function call message

        packet_args = [fn_oid,  # what function
                       _Int16_arg(1),  # only need 1 format type...
                       _Int16_arg(1),  # ...which is binary
                       ]

        # Number of args
        packet_args.append(_Int16_arg(len(args)))

        # Args (length followed by bytes)...
        for a in args:
            if a is None:
                packet_args.append(-1)  # special representation for NULL
            else:
                arg_data = pack_data(a)
                packet_args.extend((len(arg_data), _ByteN_arg(arg_data)))

        # Result type (binary)
        packet_args.append(_Int16_arg(1))

        self.send_packet(PG_FUNCTION_CALL_MSG, *packet_args)

        exception = None
        result = None

        while 1:
            msg, data = self.read_packet()

            if msg == PG_READY_FOR_QUERY_MSG:
                break

            elif msg == PG_FUNCTION_CALL_RESPONSE:
                return_len, data = unpack_data(data, 'i', return_rest=1)

                if return_len == 2:
                    result = struct.unpack('!h', data)[0]
                elif return_len == 4:
                    result = struct.unpack('!i', data)[0]
                else:
                    result = data  # punt on decoding?

            elif msg == PG_ERROR_MSG:
                if not exception:
                    exception = FunctionError('_function_call', data)
                    # LOG("FunctionError: %r" % exception.error_fields)
                    # coro.print_stderr("FunctionError: %r\n" % exception.error_fields)

            elif msg == PG_NOTICE_MSG:
                self._notice(FUNCTION_NOTICE, data)

            else:
                continue  # ignore packet?

        if exception:
            # coro.print_stderr("exception: %r\n" % exception.error_fields)
            raise exception

        return result

_lo_functions = None


# ===========================================================================
# Query Results
# ===========================================================================

# XXX this is where we need some generator goodness.

class query_results:
    def __init__(self):
        self.ntuples = 0
        self.nfields = 0
        self.cmdTuples = 0
        self.oidValue = 0

        self._field_names = []
        self._field_types = []
        self._rows = []

    def fname(self, fidx):
        if fidx >= 0 and fidx < len(self._field_names):
            return self._field_names[fidx]
        else:
            return None

    def fnumber(self, name):
        for i in xrange(len(self._field_names)):
            if self._field_names[i] == name:
                return i

        return -1

    def getvalue(self, row, col):
        r = self.getrow(row)
        if r is not None and col >= 0 and col < len(r):
            return r[col]
        else:
            return None

    def getrow(self, row):
        if row >= 0 and row < len(self._rows):
            return self._rows[row]
        else:
            return None

    def getallrows(self):
        return self._rows

    def getrowdict(self, row):
        """Get a result row as a dictionary {col name: value}"""

        r = self.getrow(row)
        if r is not None and len(r) <= len(self._field_names):
            result = {}
            for i in xrange(len(r)):
                result[self._field_names[i]] = r[i]
            return result
        else:
            return None

    def getallrowdicts(self):
        return map(self.getrowdict, xrange(self.ntuples))

    def getcolumn(self, col):
        """Get a list of all values in a given column."""

        try:
            return map(lambda x: x[col], self._rows)
        except IndexError:
            # col out of range
            return None

    def _row_description(self, data):
        self.nfields, data = unpack_data(data, 'h', return_rest=1)

        for unused in xrange(self.nfields):
            (fname, table_oid,
             colnum, ftype,
             fsize, fmod,
             format, data) = unpack_data(data, 'sihihih', return_rest=1)
            self._field_names.append(fname)
            self._field_types.append(ftype)

    def _data_row(self, data):
        nvalues, data = unpack_data(data, 'h', return_rest=1)

        new_row = [None] * self.nfields
        for i in xrange(min(self.nfields, nvalues)):
            collen, data = unpack_data(data, 'i', return_rest=1)
            if collen >= 0:
                cast = decode_type_map.get(self._field_types[i], str)
                new_row[i] = cast(data[:collen])
                data = data[collen:]

        self._rows.append(new_row)

    def _command_complete(self, data):
        # extract some info from the data
        tag = unpack_data(data, 's')[0]
        parts = tag.split(' ')

        self.oidValue = 0
        self.cmdTuples = 0

        if parts[0] == 'INSERT':
            self.oidValue = int(parts[1])
            self.cmdTuples = int(parts[2])
        elif parts[0] in ('DELETE', 'UPDATE', 'MOVE', 'FETCH'):
            self.cmdTuples = int(parts[1])

        self.ntuples = len(self._rows)


class async_query:
    """Class that encapsulates an asynchronous database query.

    Currently, this is used for implementing a timeout, but in the
    future it could be exposed at the app level, to allow a query
    to be started and the results tested some time later.

    :IVariables:
        - `_client`: instance of postgres_client, representing
          the database connection.
        - `_thread`: the thread running the query
        - `_res`: result of the query; None if not yet completed;
          and exception if the query produced an exception
        - `_cv`: condition_variable to allow a thread waiting for
          the result to be awaken.

    An instance can only run a single query, although the result
    can be read multiple times by multiple threads.
    """

    def __init__(self, client):
        self._client = client

        # It isn't necessary to hang onto the thread, but it might
        # help in debugging.
        self._thread = None

        self._res = None
        self._cv = coro.condition_variable()

    def start(self, sql):
        """Start a thread to run sql as a query."""

        assert self._thread is None
        self._thread = coro.spawn(self._run_query, sql)
        self._thread.set_name('async_query %r' % id(self))

    def _run_query(self, sql):
        """Function run in secondary thread to run db query."""

        try:
            res = self._client.query(sql)
        except PostgresError, e:
            # The query raised an exception, which becomes the "result"
            res = e

        # Set the result attribute & wake threads waiting for the answer.
        self._res = res
        self._cv.wake_all()

    def get_result(self, timeout):
        """Get query result waiting up to timeout seconds.

        If the query completes within the timeout, it will be
        returned.  If the query raises an exception, the same
        exception will be raised by this call.  If the query times
        out, this call will raise coro.TimeoutError.
        """

        # See if the query has completed already; if not
        # wait for a result up to the timeout.
        if self._res is None:
            try:
                coro.with_timeout(timeout, self._cv.wait)
            except coro.TimeoutError:
                # Timeout, cancel the request.
                self._client.cancel()

            # The request may or may not be cancelled.  Either way,
            # wait for the other thread to post a result and finish
            # using the db connection.
            while self._res is None:
                self._cv.wait()

        if isinstance(self._res, Exception):
            if (isinstance(self._res, BackendError) and
                    self._res.error_code() == PG_ERROR_QUERY_CANCELLED):
                raise coro.TimeoutError  # really did time out
            else:
                raise self._res

        # Fall through if we got an actual result
        return self._res


# ======================================================================
# Places in the code that can get notice messages
# ======================================================================

BACKEND_START_NOTICE = "wait for backend"
QUERY_NOTICE = "query"
FUNCTION_NOTICE = "function"


# ======================================================================
# Postgres message types
# ======================================================================

# See http://www.postgresql.org/docs/9.2/static/protocol-message-formats.html

PG_STARTUP_MSG = ''
PG_SSLREQUEST_MSG = ''
PG_CANCELREQUEST_MSG = ''
PG_COMMAND_COMPLETE_MSG = 'C'
PG_COPY_DONE_MSG = 'c'
PG_DATA_ROW_MSG = 'D'
PG_COPY_DATA_MSG = 'd'
PG_ERROR_MSG = 'E'
PG_FUNCTION_CALL_MSG = 'F'
PG_COPY_FAIL_MSG = 'f'
PG_COPY_IN_RESPONSE_MSG = 'G'
PG_COPY_OUT_RESPONSE_MSG = 'H'
PG_EMPTY_QUERY_RESPONSE_MSG = 'I'
PG_BACKEND_KEY_DATA_MSG = 'K'
PG_NOTICE_MSG = 'N'
PG_QUERY_MSG = 'Q'
PG_AUTHENTICATION_OK_MSG = 'R'
PG_PARAMETER_STATUS_MSG = 'S'
PG_SYNC_MSG = 'S'
PG_ROW_DESCRIPTION_MSG = 'T'
PG_FUNCTION_CALL_RESPONSE = 'V'
PG_TERMINATE_MSG = 'X'
PG_READY_FOR_QUERY_MSG = 'Z'

# added by SMR 20130401
PG_PASSWORD_MESSAGE = 'p'

# ======================================================================
# Field types for Notice & Error messages
# ======================================================================

PG_SEVERITY_FIELD = 'S'
PG_SQLSTATE_FIELD = 'C'
PG_MESSAGE_FIELD = 'M'
PG_DEFAULT_FIELD = 'D'
PG_HINT_FIELD = 'H'
PG_POSITION_FIELD = 'P'
PG_WHERE_FIELD = 'W'
PG_FILE_FIELD = 'F'
PG_LINE_FIELD = 'L'
PG_ROUTINE_FIELD = 'R'


# ======================================================================
# Common Error Codes
# ======================================================================

PG_ERROR_UNIQUE_VIOLATION               = '23505'
PG_ERROR_INVALID_CATALOG_NAME           = '3D000'
PG_ERROR_DATABASE_EXISTS                = '42P04'
PG_ERROR_OBJECT_IN_USE                  = '55006'
PG_ERROR_QUERY_CANCELLED                = '57014'


# ======================================================================
# Decoding Postgres data types
# ======================================================================

def _simple_array_decode(x, fn):
    """Decode array string where the elements are guaranteed not to
    have any quoting (and there for we can just split on commas).
    Call fn on each element to convert to actual value"""

    if x[0] != '{' or x[-1] != '}':
        raise ValueError('Array not enclosed in {...}')
    x = x[1:-1]
    return map(lambda s, fn=fn: fn(s.strip()), x.split(','))

_simple_str_elt_re = re.compile(r'''([^"][^,]*),?''')
_quoted_str_elt_re = re.compile(r'''"((?:\\\\|\\"|[^"])*)",?''')
_escape_sub_re = re.compile(r'\\(.)')

def _general_array_decode(x):
    """Decode array string where elements may be quoted."""

    if x[0] != '{' or x[-1] != '}':
        raise ValueError('Array not enclosed in {...}')
    x = x[1:-1]

    result = []
    pos = 0
    while pos < len(x):
        # check for unquoted element
        match = _simple_str_elt_re.match(x, pos)
        if match:
            result.append(match.group(1))
            pos = match.end()
            continue

        # check for quoted element
        match = _quoted_str_elt_re.match(x, pos)
        if match:
            # must undo '\' escaping
            part = _escape_sub_re.sub(r'\1', match.group(1))
            result.append(part)
            pos = match.end()
            continue

        # problem
        raise ValueError('Could not parse array (%s)' % x[pos:])

    return result

def decode_bool(x):
    return x == 't' or x == 'T'

def decode_int_array(x):
    return _simple_array_decode(x, int)

def decode_str_array(x):
    return _general_array_decode(x)

# Matches \xxx and \\ where x is an octal character.
# Note that the regexp syntax requires 2 \ characters in a pattern,
# and the raw string eliminates the need to quote each of those.
_quoted_bytea_re = re.compile(r'(\\[0-7][0-7][0-7]|\\\\)')

def decode_bytea(x):
    parts = _quoted_bytea_re.split(x)
    for i in xrange(1, len(parts), 2):
        # even elements are OK; odd elements need conversion
        if parts[i] == '\\\\':  # 2 slashes...
            parts[i] = '\\'  # ...become 1
        else:
            parts[i] = chr(int(parts[i][1:], 8))

    return ''.join(parts)

#
# from src/include/catalog/pg_type.h
#
# by default leave as a string
decode_type_map = {}
decode_type_names = {}

# NOTE: there is a table built into postgres with these values.
# Try "select typname, typelem from pg_catalog.pg_type"

for oid, cast, name in (
    (16, decode_bool, 'bool'),
    (17, decode_bytea, 'bytea'),
    (18, str, 'char'),
    (19, str, 'name'),
    (20, int, 'int8'),
    (21, int, 'int2'),
    (22, decode_int_array, 'int2vector'),
    (23, int, 'int4'),
    (25, str, 'text'),
    (26, int, 'oid'),
    (27, int, 'tid'),
    (28, int, 'xid'),
    (29, int, 'cid'),
    (30, str, 'oidvector'),
    (700, float, 'float4'),
    (701, float, 'float8'),
    (1007, decode_int_array, 'int4[]'),
    (1009, decode_str_array, 'text[]'),
    (1700, float, 'numeric')
):
    decode_type_map[oid] = cast
    decode_type_names[oid] = name


# ===========================================================================
#                           Packet Protocol
# ===========================================================================

def not_unpack_data(data, formats, return_rest=0):
    """Unpack the data part of a packed according to format:

    i: Int32
    h: Int16
    s: String
    c: Byte1 (returned as 1-character string)

    If return_rest is true, then return the rest of the
    data as the last item in the list.
    """

    pos = 0
    result = []

    for code in formats:
        if code == 'i':
            result.append(struct.unpack('!i', data[pos:pos + 4])[0])
            pos += 4
        elif code == 'h':
            result.append(struct.unpack('!h', data[pos:pos + 2])[0])
            pos += 2
        elif code == 'c':
            result.append(data[pos])
            pos += 1
        elif code == 's':
            i = data.find('\0', pos)
            if i < 0:
                i = len(data)

            result.append(data[pos:pos + i])
            pos += (i + 1)

    if return_rest:
        result.append(data[pos:])

    return result

try:
    # try to pull in cython speedup[s]
    from coro.db.postgres import proto
    unpack_data = proto.unpack_data
except ImportError:
    pass

def unpack_error_data(data):
    """Unpack the dictionary-like structure used in Error and Notice
    responses.  keys are 1 character codes followed by a String.  A
    '\0' key signals the end of the data."""

    pos = 0
    result = {}

    while pos < len(data):
        k = data[pos]
        if k == '\0':
            break
        pos += 1
        if not k:
            break

        i = data.find('\0', pos)
        if i < 0:
            i = len(data)

        result[k] = data[pos:i]
        pos = i + 1

    return result

unpack_notice_data = unpack_error_data

def pack_data(*data_args):
    """Pack data values into an appropriate payload.

    Each element of data_args can be:

    string: encode as String
    int: encode as Int32
    list/tuple: use the first element as a pack string
                applied to rest of the elements
    """

    parts = []
    for d in data_args:
        if isinstance(d, types.StringType):
            parts.extend((d, '\0'))  # null terminated string
        elif isinstance(d, types.IntType):
            parts.append(struct.pack('!i', d))
        elif isinstance(d, types.ListType) or isinstance(d, types.TupleType):
            parts.append(struct.pack(d[0], *d[1:]))

    return ''.join(parts)

def build_message (message_type, *data_args):
    """Build a Postgres message."""

    args = pack_data(*data_args)
    data = ''.join ([message_type, struct.pack('!i', len(args) + 4), args])
    return data

# helpers that can be used for args to pack_data

def _Int16_arg(x):
    if isinstance(x, types.IntType):
        return ('!h', x)
    else:
        return ('!%dh' % len(x),) + tuple(x)

def _Int32_arg(x):
    if isinstance(x, types.IntType):
        return int(x)
    else:
        return ('!%di' % len(x),) + tuple(x)

def _ByteN_arg(x):
    return ('!%ds' % len(x), x)

# used to generate the dumps below
def dump_hex (s):
    r1 = []
    r2 = []

    for ch in s:
        r1.append (' %02x' % ord(ch))
        if (ch in string.letters) or (ch in string.digits):
            r2.append ('  %c' % ch)
        else:
            r2.append ('   ')

    return string.join (r1, ''), string.join (r2, '')


# ===========================================================================
#                           Postgres Utilities
# ===========================================================================

def connect_to_db(database, username='', address=None, schema=None):
    """Utility to connect to the indicated database.

    Return instance of postgres_client if successful or None if there
    is no such database.  If schema is supplied as a string, and the
    database doesn't exist, create the database."""

    database = database.lower()
    db = postgres_client(database=database,
                         username=username,
                         address=address)
    try:
        db.connect()
        return db
    except ConnectError, e:  # doesn't exist
        if e.error_code() == PG_ERROR_INVALID_CATALOG_NAME:
            if schema is not None:
                dbm = database_manager(username=username,
                                       address=address)
                dbm.create_database(database, schema)

                # try again
                db.connect()
                return db
            else:
                return None
        else:
            raise  # some other Postgres error

class database_manager:
    def __init__(self, username='', password='',
                 address=None,
                 debug=False):
        self._db = postgres_client('template1',
                                   username=username,
                                   password=password,
                                   address=address)
        self._debug = debug

    def has_database(self, database):

        res = self._query(
            '''select datname from pg_database
               where datname=%s''' % quote_string(database))
        return res.ntuples

    def create_database(self, database, schema=None):
        delete_db = False

        try:
            self._query('CREATE DATABASE %s' % database)
            if schema:
                # If we can't install the schema, ensure db is dropped
                delete_db = True

                # connect to new database and load it up
                new_db = postgres_client(database,
                                         username=self._db.username,
                                         password=self._db.password,
                                         address=self._db.address)
                new_db.connect()
                try:
                    new_db.query(schema)
                    delete_db = False  # it's done
                finally:
                    new_db.close()
        finally:
            if delete_db:
                try:
                    self.drop_database(database)
                except coro.Interrupted:
                    raise
                except:
                    pass

    def drop_database(self, database):
        try:
            self._query('DROP DATABASE %s' % database)
        except QueryError, e:
            if e.error_code() == PG_ERROR_INVALID_CATALOG_NAME:
                pass  # this is OK
            else:
                raise

    def _query(self, sql):
        """Perform a query against the template1 database.

        create/drop database cannot be done while there are other
        connections to template1, so only maintain the connection for
        as long as necessary.

        Also, this method handles the error that occurs if >1
        connection tries to manipulate databases while there are other
        connections.  (Because there are multiple processes involved,
        it isn't possible to serialize connections to template1.)
        """

        self._db.connect()
        try:
            while True:
                try:
                    return self._db.query(sql)
                except QueryError, e:
                    if e.error_code() == PG_ERROR_OBJECT_IN_USE:
                        self._backoff()
                    else:
                        raise  # some other exception
        finally:
            self._db.close()  # close the connection

    def _backoff(self):
        """Called after finding that template1 is in use.

        Checks to see if the current connection has the lowest pid.
        If not, then closes the connection to allow the lowest
        to proceed.  This should prevent livelock where 2 threads
        continually interfere with one another."""

        my_pid = self._db.get_pid()

        while True:
            # Get smallest pid connected to template1
            res = self._db.query(
                """SELECT procpid FROM pg_stat_activity
                   WHERE datname='template1' ORDER BY procpid""")

            if res.ntuples == 0:
                # For some reason, occasionally there is nothing in
                # the pg_stat_activity table.  Try again.
                sleep(0.5)
                continue
            elif res.getvalue(0, 0) != my_pid:
                if self._debug:
                    P("%d closing" % (my_pid,))
                self._db.close()  # the other connection takes priority
                break
            else:
                # This connection has smallest pid, so remain connected.
                if self._debug:
                    P("%d continuing" % (my_pid,))
                break

        # Allow some time for other connections to finish.
        sleep(2)

        # Must be connected before returning.
        if not self._db.is_connected():
            self._db.connect()

def md5_hex (s):
    import hashlib
    h = hashlib.new ('md5')
    h.update (s)
    return h.hexdigest()

def sleep(x):
    coro.sleep_relative(x)

# def make_db():
# db = postgres_client('lrosenstein', '', 'system_quarantine',
# ('127.0.0.1', 5432))
# db.connect()
# return db

# def test_open(db):
# db.query("BEGIN")
# return db.lo_open(17219, INV_READ)

# def test_read(db):
# db.query("BEGIN")
#    fd = db.lo_open(17219, INV_READ)
# print db.lo_read(fd, 50)
# print db.lo_read(fd)
# db.lo_close(fd)
# db.query("ROLLBACK")

def test_ssl():
    import coro.ssl.openssl
    ctx = coro.ssl.openssl.ssl_ctx()
    db = postgres_client ('mydb', 'myuser', 'mypass', ('192.168.1.99', 5432), ssl_context=ctx)
    return db

def test_concurrent_dbm(tries):
    dbm = database_manager(debug=True)
    for i in xrange(tries):
        my_tid = coro.current().thread_id()
        db_name = "test_database_%d_%d" % (my_tid, i)
        dbm.create_database(db_name)
        dbm.drop_database(db_name)
        P("done %r" % db_name)

def watcher(thread_ids):
    while True:
        if len(thread_ids) == 0:
            coro.set_exit()
            break
        thread_ids = [x for x in thread_ids if x in coro.all_threads]
        coro.sleep_relative(0.1)

if __name__ == '__main__':

    import coro.backdoor
    coro.spawn (coro.backdoor.serve)

    # thread_ids = []
    #
    # for i in xrange(3):
    #    thread_ids.append(coro.spawn(test_concurrent_dbm, 5).thread_id())
    # coro.spawn(watcher, thread_ids)

    coro.event_loop (30.0)
