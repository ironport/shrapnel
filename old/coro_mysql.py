# -*- Mode: Python -*-

# Copyright 1999 by eGroups, Inc.
#
#                         All Rights Reserved
#
# Permission to use, copy, modify, and distribute this software and
# its documentation for any purpose and without fee is hereby
# granted, provided that the above copyright notice appear in all
# copies and that both that copyright notice and this permission
# notice appear in supporting documentation, and that the name of
# eGroups not be used in advertising or publicity pertaining to
# distribution of the software without specific, written prior
# permission.
#
# EGROUPS DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE,
# INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS, IN
# NO EVENT SHALL EGROUPS BE LIABLE FOR ANY SPECIAL, INDIRECT OR
# CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
# OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
# NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
# CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

VERSION_STRING = '$Id'

import exceptions
import math
import socket
import string
import sys

import coro

W = sys.stderr.write

MAX_RECONNECT_RETRY   = 10.0
RECONNECT_RETRY_GRAIN = 0.1
DEFAULT_RECV_SIZE     = 0x8000
MYSQL_HEADER_SIZE     = 0x4
MYSQL_END = chr(0xfe)

class InternalError (exceptions.Exception):
    pass

class error (exceptions.Exception):
    pass

# ===========================================================================
#                            Authentication
# ===========================================================================

# Note: I have ignored the stuff to support an older version of the protocol.
#
# The code is based on the file mysql-3.21.33/client/password.c
#
# The auth scheme is challenge/response.  Upon connection the server
# sends an 8-byte challenge message.  This is hashed with the password
# to produce an 8-byte response.  The server side performs an identical
# hash to verify the password is correct.

class random_state:

    def __init__ (self, seed, seed2):
        self.max_value = 0x3FFFFFFF
        self.seed = seed % self.max_value
        self.seed2 = seed2 % self.max_value
        return None

    def rnd (self):
        self.seed = (self.seed * 3 + self.seed2) % self.max_value
        self.seed2 = (self.seed + self.seed2 + 33) % self.max_value
        return float(self.seed) / float(self.max_value)

def hash_password (password):
    nr = 1345345333
    nr2 = 0x12345671
    add = 7

    for ch in password:
        if (ch == ' ') or (ch == '\t'):
            continue
        tmp = ord(ch)
        nr = nr ^ (((nr & 63) + add) * tmp) + (nr << 8)
        nr2 = nr2 + ((nr2 << 8) ^ nr)
        add = add + tmp

    return (nr & ((1 << 31) - 1), nr2 & ((1 << 31) - 1))

def scramble (message, password):
    hash_pass = hash_password (password)
    hash_mess = hash_password (message)

    r = random_state (
        hash_pass[0] ^ hash_mess[0],
        hash_pass[1] ^ hash_mess[1]
    )
    to = []

    for ch in message:
        to.append (int (math.floor ((r.rnd() * 31) + 64)))

    extra = int (math.floor (r.rnd() * 31))
    for i in range(len(to)):
        to[i] = to[i] ^ extra

    return to

# ===========================================================================
#                           Packet Protocol
# ===========================================================================

def unpacket (p):
    # 3-byte length, one-byte packet number, followed by packet data
    a, b, c, s = map (ord, p[:4])
    l = a | (b << 8) | (c << 16)

    # s is a sequence number
    return l, s

def packet (data, s=0):
    l = len(data)
    a, b, c = l & 0xff, (l >> 8) & 0xff, (l >> 16) & 0xff
    h = map (chr, [a, b, c, s])

    return string.join (h, '') + data

def n_byte_num (data, n, pos=0):
    result = 0
    for i in range(n):
        result = result | (ord(data[pos + i]) << (8 * i))

    return result

def decode_length (data, pos=0):
    n = ord(data[pos])

    if n < 251:
        return n, 1
    elif n == 251:
        return 0, 1
    elif n == 252:
        return n_byte_num (data, 2, pos + 1), 3
    elif n == 253:
        return n_byte_num (data, 3, pos + 1), 4
    else:
        # libmysql adds 6, why?
        return n_byte_num (data, 4, pos + 1), 5

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
# generic utils
# ===========================================================================

class mysql_client:

    def __init__ (self, username, password, address=('127.0.0.1', 3306),
                  debug=0, timeout=None, connect_timeout=None):

        # remember this for reconnect
        self.username = username
        self.password = password
        self.address = address

        self._database  = None

        self._connected = 0

        self._recv_buffer = ''
        self._recv_length = 0

        self._lock = 0
        self._debug = debug
        self._timeout = timeout
        self._connect_timeout = connect_timeout

    def make_socket(self, *args, **kwargs):
        if self._debug:
            return socket.socket (*args, **kwargs)
        else:
            return coro.make_socket (*args, **kwargs)

    def connect (self):
        if (isinstance(self.address, type(''))):
            self.socket = self.make_socket(socket.AF_UNIX, socket.SOCK_STREAM)
        else:
            self.socket = self.make_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect (self.address)
        self._recv_buffer = ''
        self._recv_length = 0
        return None

    def recv(self):
        data = self.socket.recv (DEFAULT_RECV_SIZE)
        if not data:
            raise InternalError("Lost connection to MySQL server during query")
        else:
            self._recv_buffer = self._recv_buffer + data
            self._recv_length = self._recv_length + len(data)
        return None

    def write (self, data):
        ln = len(data)
        while data:
            n = self.socket.send (data)
            if not n:
                raise InternalError("Lost connection to MySQL server during query")
            else:
                data = data[n:]
        return ln

    debug = 0

    def send_packet (self, data, sequence=0):

        if self.debug:
            print '--> %03d' % sequence
            a, b = dump_hex (data)
            print a
            print b

        self.write (packet (data, sequence))

        return None

    def get_header(self):

        if self._recv_length < MYSQL_HEADER_SIZE:
            return None, None
        else:
            # 3-byte length, one-byte packet number, followed by packet data
            a, b, c, seq = map (ord, self._recv_buffer[:MYSQL_HEADER_SIZE])
            length = a | (b << 8) | (c << 16)

        return length, seq

    def read_packet (self):

        packet_len, seq = self.get_header()

        while (MYSQL_HEADER_SIZE > self._recv_length
               or packet_len + MYSQL_HEADER_SIZE > self._recv_length):

            self.recv()

            if packet_len is None:
                packet_len, seq = self.get_header()
        #
        # now we have at least one packet
        #
        data = self._recv_buffer[MYSQL_HEADER_SIZE:MYSQL_HEADER_SIZE + packet_len]
        self._recv_buffer = self._recv_buffer[MYSQL_HEADER_SIZE + packet_len:]
        self._recv_length = self._recv_length - (MYSQL_HEADER_SIZE + packet_len)

        return seq, data

    def login (self):

        seq, data = self.read_packet()
        # unpack the greeting
        protocol_version = ord(data[0])
        eos = string.find (data, '\000')
        mysql_version = data[1:eos]
        # thread_id = n_byte_num (data[eos+1:eos+5], 4, eos)
        thread_id = n_byte_num (data, 4, eos + 1)
        challenge = data[eos + 5:eos + 13]

        auth = (protocol_version, mysql_version, thread_id, challenge)

        lp = self.build_login_packet (challenge)
        # seems to require a sequence number of one
        self.send_packet (lp, 1)
        #
        # read the response, which will check for errors
        #
        response_tuple = self.read_reply_header()

        if response_tuple != (0, 0, 0):
            raise InternalError('unknown header response: <%r>' % (response_tuple,))

        #
        # mark that we are now connected
        #
        return None

    def check_connection(self):

        if not self._connected:

            self.connect()
            self.login()

            if self._database is not None:

                self.cmd_use(self._database)

            self._connected = 1

        return None

    def build_login_packet (self, challenge):
        auth = string.join (map (chr, scramble (challenge, self.password)), '')
        # 2 bytes of client_capability
        # 3 bytes of max_allowed_packet
        # the '5' == (LONG_PASSWORD | LONG_FLAG)
        return '\005\000\000\000\020' + self.username + '\000' + auth

    def command (self, command_type, command):
        q = chr(decode_db_cmds[command_type]) + command
        self.send_packet (q, 0)
        return None

    def unpack_data (self, d):
        r = []
        i = 0
        while i < len(d):
            fl = ord(d[i])
            if fl > 250:
                fl, scoot = decode_length (d, i)
                i = i + scoot
            else:
                i = i + 1
            r.append (d[i:i + fl])
            i = i + fl
        return r

    def unpack_int(self, data_str):
        if len(data_str) > 4:
            raise TypeError('data too long to be an int32: <%d>' % len(data_str))
        value = 0
        while len(data_str):
            i = ord(data_str[len(data_str) - 1])
            data_str = data_str[:len(data_str) - 1]
            value = value + (i << (8 * len(data_str)))
        return value

    def read_reply_header(self):
        #
        # read in the reply header and return the results.
        #
        seq, data = self.read_packet()

        rows_in_set = 0
        affected_rows = 0
        insert_id = 0

        if data[0] == chr(0xff):
            error_num = ord(data[1]) + (ord(data[2]) << 8)
            error_msg = data[3:]

            raise InternalError('ERROR %d: %s' % (error_num, error_msg))

        elif data[0] == MYSQL_END:
            raise InternalError('unknown header <%s>' % (repr(data)))
        else:

            rows_in_set, move     = decode_length(data, 0)
            data = data[move:]

            if len(data):

                affected_rows, move = decode_length(data, 0)
                data = data[move:]
                insert_id, move     = decode_length(data, 0)
                data = data[move:]

            msg = data

        return rows_in_set, affected_rows, insert_id
    #
    # Internal mysql client requests to get raw data from db (cmd_*)
    #

    def cmd_use (self, database):
        self.command ('init_db', database)

        rows, affected, insert_id = self.read_reply_header()

        if rows != 0 or affected != 0 or insert_id != 0:
            msg = 'unexpected header: <%d> <%d> <%d>' % (rows, affected, insert_id)
            raise InternalError(msg)

        self._database = database

        return None

    def cmd_query (self, query, callback=None):
        # print 'coro mysql query: "%s"' % (repr(query))
        self.command ('query', query)
        #
        # read in the header
        #
        nfields, affected, insert_id = self.read_reply_header()

        if not nfields:
            return statement([], [], affected, insert_id)

        decoders = range(nfields)
        fields = []
        i = 0

        while True:
            seq, data = self.read_packet()

            if data == MYSQL_END:
                break
            else:
                field = self.unpack_data (data)
                decoders[i] = decode_type_map[ord(field[3])]
                fields.append (field)

            i = i + 1

        if len(fields) != nfields:
            raise InternalError("number of fields did not match")

        # read rows
        rows = []
        field_range = range(nfields)

        while True:
            seq, data = self.read_packet()

            if data == MYSQL_END:
                break
            else:
                row = self.unpack_data (data)
                # apply decoders
                for i in field_range:
                    try:
                        row[i] = decoders[i](row[i])
                    except exceptions.ValueError:
                        # bob HACK.  string reps of large unsigned values
                        #     will throw a valueerror exception.
                        try:
                            row[i] = long(row[i])
                        except ValueError:
                            row[i] = None

                if callback is None:
                    rows.append(row)
                else:
                    callback(row)

        return statement(fields, rows)

    def cmd_quit (self):
        self.command ('quit', '')
        #
        # no reply!
        #
        return None

    def cmd_shutdown (self):
        self.command ('shutdown', '')
        seq, data = self.read_packet()
        return None

    def cmd_drop (self, db_name):
        self.command ('drop_db', db_name)
        nfields, affected, insert_id = self.read_reply_header()
        return None

    def cmd_listfields(self, cmd):
        self.command ('field_list', cmd)

        rows = []
        #
        # read data line until we get 255 which is error or 254 which is
        # end of data ( I think :-)
        #
        while True:

            seq, data = self.read_packet()
            #
            # terminal cases.
            #
            if data[0] == chr(0xff):
                raise InternalError(data[3:])

            elif data[0] == MYSQL_END:

                return rows
            else:

                row = self.unpack_data(data)

                table_name = row[0]
                field_name = row[1]
                field_size = self.unpack_int(row[2])
                field_type = decode_type_names[ord(row[3])]
                field_flag = self.unpack_int(row[4])
                field_val  = row[5]

                flag_value = ''

                if field_flag & decode_flag_value['pri_key']:
                    flag_value = flag_value + decode_flag_name['pri_key']

                if field_flag & decode_flag_value['not_null']:
                    flag_value = flag_value + ' ' + decode_flag_name['not_null']

                if field_flag & decode_flag_value['unique_key']:
                    flag_value = flag_value + ' ' + decode_flag_name['unique_key']

                if field_flag & decode_flag_value['multiple_key']:
                    flag_value = flag_value + ' ' + decode_flag_name['multiple_key']

                if field_flag & decode_flag_value['auto']:
                    flag_value = flag_value + ' ' + decode_flag_name['auto']
                #
                # for some reason we do not pass back the default value (row[5])
                #
                rows.append(
                    [field_name, table_name, field_type, field_size, flag_value]
                )

        return None

    def cmd_create(self, name):
        self.command ('create_db', name)
        nfields, affected, insert_id = self.read_reply_header()
        return None

    #
    # MySQL module compatibility, properly wraps raw client requests,
    # to format the return types.
    #
    def selectdb(self, database):
        return self.cmd_use (database,)

    def query (self, q):
        return self.cmd_query(q)

    def listtables (self, wildcard=None):
        if wildcard is None:
            cmd = "show tables"
        else:
            cmd = "show tables like '%s'" % (wildcard)
        return self.cmd_query(cmd).fetchrows()

    def listfields (self, table_name, wildcard=None):
        if wildcard is None:
            cmd = "%s\000\000" % (table_name)
        else:
            cmd = "%s\000%s\000" % (table_name, wildcard)
        return self.cmd_listfields (cmd)

    def drop(self, database):
        return self.cmd_drop (database)

    def create(self, db_name):
        return self.cmd_create (db_name)

    def close(self):
        return self.cmd_quit()

# compatibility layer, avoid it if you can by using cmd_query directly.
# incomplete and hackish.  perhaps a better solution would be to implement
# the DB API ourselves rather than using Mysqldb.py

class statement:

    def __init__ (self, fields, rows, affected_rows=-1, insert_id=0):
        self._fields = fields
        self._rows = rows

        if affected_rows < 0:
            self._affected_rows = len(rows)
        else:
            self._affected_rows = affected_rows

        self._index = 0
        self._insert_id = insert_id

        return None
    # =======================================================================
    # internal methods
    # =======================================================================

    def _fetchone (self):
        if self._index < len(self._rows):
            result = self._rows[self._index]
            self._index = self._index + 1
        else:
            result = []

        return result

    def _fetchmany (self, size):
        result = self._rows[self._index:self._index + size]
        self._index = self._index + len(result)

        return result

    def _fetchall (self):
        result = self._rows[self._index:]
        self._index = self._index + len(result)

        return result
    # =======================================================================
    # external methods
    # =======================================================================

    def affectedrows (self):
        return self._affected_rows

    def numrows (self):
        return len(self._rows)

    def numfields(self):
        return len(self._fields)

    def fields (self):
        # raw format:
        # table, fieldname, ??? (flags?), datatype
        # ['groupmap', 'gid', '\013\000\000', '\003', '\013B\000']
        # MySQL returns
        # ['gid', 'groupmap', 'long', 11, 'pri notnull auto_inc mkey']
        return map (lambda x: (x[1],
                               x[0],
                               decode_type_names[ord(x[3])],
                               ord(x[4][0])),
                    self._fields)

    def fetchrows(self, size=0):
        if size:
            return self._fetchmany(size)
        else:
            return self._fetchall()

    # [{'groupmap.podid': 2,
    #   'groupmap.listname': 'medusa',
    #   'groupmap.active': 'y',
    #   'groupmap.gid': 116225,
    #   'groupmap.locked': 'n'}]
    def fetchdict (self, size=0, options=0):
        if options & OPTION_SHORT:
            keys = map (lambda x: x[1], self._fields)
        else:
            keys = map (lambda x: "%s.%s" % (x[0], x[1]), self._fields)
        range_len_keys = range(len(keys))
        result = []
        for row in self.fetchrows(size):
            d = {}
            for j in range_len_keys:
                d[keys[j]] = row[j]
            result.append(d)
        return result

    def insert_id (self):
        # i have no idea what this is
        return self._insert_id

OPTION_SHORT = 1
# ======================================================================
# decoding MySQL data types
#
# from mysql-3.21.33/include/mysql_com.h.in
#
# by default leave as a string
decode_type_map = [str] * 256
decode_type_names = ['unknown'] * 256

# Many of these are not correct!  Note especially
# the time/date types... If you want to write a real decoder
# for any of these, just replace 'str' with your function.

for code, cast, name in (
    (0, float, 'decimal'),
    (1, int, 'tiny'),
    (2, int, 'short'),
    (3, int, 'long'),
    (4, float, 'float'),
    (5, float, 'double'),
    (6, str, 'null'),
    (7, str, 'timestamp'),
    # (8,                long,   'longlong'),
    (8, str, 'unhandled'),  # Mysqldb expects unhandled.  strange.
    (9, int, 'int24'),
    (10, str, 'date'),  # looks like YYYY-MM-DD ??
    (11, str, 'time'),  # looks like HH:MM:SS
    (12, str, 'datetime'),
    (13, str, 'year'),
    (14, str, 'newdate'),
    (247, str, 'enum'),
    (248, str, 'set'),
    (249, str, 'tiny_blob'),
    (250, str, 'medium_blob'),
    (251, str, 'long_blob'),
    (252, str, 'blob'),
    (253, str, 'varchar'),  # in the C code it is VAR_STRING
    (254, str, 'string')
):
    decode_type_map[code] = cast
    decode_type_names[code] = name
#
# we need flag mappings also
#
decode_flag_value = {}
decode_flag_name  = {}

for value, flag, name in (
    (1, 'not_null', 'notnull'),  # Field can not be NULL
    (2, 'pri_key', 'pri'),      # Field is part of a primary key
    (4, 'unique_key', 'ukey'),     # Field is part of a unique key
    (8, 'multiple_key', 'mkey'),     # Field is part of a key
    (16, 'blob', 'unused'),   # Field is a blob
    (32, 'unsigned', 'unused'),   # Field is unsigned
    (64, 'zerofill', 'unused'),   # Field is zerofill
    (128, 'binary', 'unused'),
    (256, 'enum', 'unused'),   # field is an enum
    (512, 'auto', 'auto_inc'),  # field is a autoincrement field
    (1024, 'timestamp', 'unused'),   # Field is a timestamp
    (2048, 'set', 'unused'),   # field is a set
    (16384, 'part_key', 'unused'),   # Intern; Part of some key
    (32768, 'group', 'unused'),   # Intern: Group field
    (65536, 'unique', 'unused')    # Intern: Used by sql_yacc
):
    decode_flag_value[flag] = value
    decode_flag_name[flag]  = name
#
# database commands
#
decode_db_cmds = {}

for value, name in (
    (0, 'sleep'),
    (1, 'quit'),
    (2, 'init_db'),
    (3, 'query'),
    (4, 'field_list'),
    (5, 'create_db'),
    (6, 'drop_db'),
    (7, 'refresh'),
    (8, 'shutdown'),
    (9, 'statistics'),
    (10, 'process_info'),
    (11, 'connect'),
    (12, 'process_kill'),
    (13, 'debug')
):
    decode_db_cmds[name] = value

# ======================================================================
##
# SMR - borrowed from daGADFLY.py, moved dict 'constant' out of
# function definition.
#
# quote_for_escape = {'\0': '\\0', "'": "''", '"': '""', '\\': '\\\\'}
# martinb - changed to match the behaviour of MySQL:
quote_for_escape = {'\0': '\\0', "'": "\\'", '"': '\\"', '\\': '\\\\'}

import types

def escape(s):
    quote = quote_for_escape
    if isinstance(s, types.IntType):
        return str(s)
    elif s is None:
        return ""
    elif isinstance(s, types.StringType):
        r = range(len(s))
        r.reverse()              # iterate backwards, so as not to destroy indexing

        for i in r:
            if s[i] in quote:
                s = s[:i] + quote[s[i]] + s[i + 1:]

        return s

    else:
        log(s)
        log (type(s))
        raise MySQLError

def test ():
    c = mysql_client ('rushing', 'fnord', ('10.1.1.55', 3306))
    print 'connecting...'
    c.connect()
    print 'logging in...'
    c.login()
    print c
    c.cmd_use ('mysql')
    for row in c.cmd_query ('select * from user').fetchrows():
        print row
    c.cmd_quit()

if __name__ == '__main__':

    import backdoor
    coro.spawn (backdoor.serve)

    for i in range(1):
        coro.spawn (test)

    coro.event_loop (30.0)
#
# - mysql_client is analogous to DBH in MySQLmodule.c, and statment is
#   analogous to STH in MySQLmodule.c
# - DBH is the database handler, and STH is the statment handler,
# - Here are the methods that the MySQLmodule.c implements, and if they
#   are at least attempted here in coromysql
#
# DBH:
#
#    "selectdb"       - yes
#    "do"             - no
#    "query"          - yes
#    "listdbs"        - no
#    "listtables"     - yes
#    "listfields"     - yes
#    "listprocesses"  - no
#    "create"         - yes
#    "stat"           - no
#    "clientinfo"     - no
#    "hostinfo"       - no
#    "serverinfo"     - no
#    "protoinfo"      - no
#    "drop"           - yes
#    "reload"         - no
#    "insert_id"      - no
#    "close"          - yes
#    "shutdown"       - no
#
# STH:
#
#    "fields"         - yes
#    "fetchrows"      - yes
#    "fetchdict"      - yes
#    "seek"           - no
#    "numrows"        - yes
#    "numfields"      - yes
#    "eof"            - no
#    "affectedrows"   - yes
#    "insert_id"      - yes
