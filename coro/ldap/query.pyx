# -*- Mode: Cython -*-

from cpython cimport PyBytes_FromStringAndSize
from coro.asn1.ber cimport *

# ================================================================================
#    ldap search filter language parser
# ================================================================================

# this is not yet complete. see rfc2254

class QuerySyntaxError (Exception):
    """Error parsing rfc2254 query filter"""
    def __str__(self):
        if (len(self.args) == 2) \
           and isinstance(self.args[0], str) \
           and isinstance(self.args[1], int) \
           and (self.args[1] >= 0) \
           and (self.args[1] < len(self.args[0])):
            return 'LDAP Query Syntax Error: Invalid character \'%c\' at ' \
                   'position %d of query "%s"' \
                   % (self.args[0][self.args[1]], self.args[1], self.args[0])
        else:
            return 'LDAP Query Syntax Error: %s' % Exception.__str__(self)

cdef enum:
    SCOPE_BASE      = 0
    SCOPE_ONELEVEL  = 1
    SCOPE_SUBTREE   = 2

cdef enum:
    DEREF_NEVER     = 0
    DEREF_SEARCHING = 1
    DEREF_FINDING   = 2
    DEREF_ALWAYS    = 3

cdef enum:
    FILTER_AND                = 0
    FILTER_OR                 = 1
    FILTER_NOT                = 2
    FILTER_EQUALITY_MATCH     = 3
    FILTER_SUBSTRINGS         = 4
    FILTER_GREATER_OR_EQUAL   = 5
    FILTER_LESS_OR_EQUAL      = 6
    FILTER_PRESENT            = 7
    FILTER_APPROX_MATCH       = 8
    FILTER_EXTENSIBLE_MATCH   = 9

cdef enum:
    SUBSTRING_INITIAL = 0
    SUBSTRING_ANY     = 1
    SUBSTRING_FINAL   = 2

def parse_query (s, pos=0):
    expression, pos = parse_expression (s, pos, 0)
    return expression

cdef parse_expression (bytes x, int pos, int depth):
    cdef char * s = x
    cdef char kind
    cdef list expressions
    cdef bytes value
    cdef bint is_substring
    if s[pos] != c'(':
        raise QuerySyntaxError, (x, pos)
    elif depth > 50:
        raise QuerySyntaxError, "expression too complex"
    else:
        # skip the open-paren
        pos = pos + 1
        # is this a logical expression or a comparison?
        if s[pos] == c'|' or s[pos] == c'&' or s[pos] == c'!':
            # logical
            kind = s[pos]
            expressions = []
            pos = pos + 1
            while s[pos] != c')':
                expression, pos = parse_expression (x, pos, depth+1)
                expressions.append (expression)
            if kind == c'|':
                return _TLV (FILTER_OR, FLAGS_CONTEXT | FLAGS_STRUCTURED, expressions), pos + 1
            elif kind == c'&':
                return _TLV (FILTER_AND, FLAGS_CONTEXT | FLAGS_STRUCTURED, expressions), pos + 1
            elif kind == c'!':
                return _TLV (FILTER_NOT, FLAGS_CONTEXT | FLAGS_STRUCTURED, expressions[:1]), pos + 1
        else:
            # comparison
            attr, is_substring, pos = parse_name (x, pos)
            operator, pos = parse_operator (x, pos)
            value, is_substring, pos = parse_value (x, pos)
            attr = unescape (attr)
            # we don't unescape <value> yet, because we might need
            # some escaped splat chars to make it through parse_substring()
            # [where the pieces will be unescaped individually]
            if is_substring:
                if value == '*' and operator == FILTER_EQUALITY_MATCH:
                    # (tag=*)
                    return _TLV (FILTER_PRESENT, FLAGS_CONTEXT, (attr,)), pos + 1
                elif operator == FILTER_EQUALITY_MATCH:
                    # (tag=sub*strin*g*)
                    return _TLV (
                        FILTER_SUBSTRINGS,
                        FLAGS_CONTEXT | FLAGS_STRUCTURED, (
                            _OCTET_STRING (attr),
                            _SEQUENCE (parse_substring (value, 0, len (value)))
                        )
                    ), pos + 1
                else:
                    raise QuerySyntaxError, "invalid wildcard syntax"
            else:
                return _TLV (
                    operator,
                    FLAGS_CONTEXT | FLAGS_STRUCTURED, (
                        _OCTET_STRING (attr),
                        _OCTET_STRING (unescape (value)),
                    )
                ), pos + 1

cdef parse_operator (bytes x, int pos):
    cdef char * s = x
    cdef int slen = len (x)
    if (pos + 2) >= slen:
        raise QuerySyntaxError, (s, pos)
    elif s[pos] == c'=':
        return FILTER_EQUALITY_MATCH, pos + 1
    elif s[pos] == c'~' and s[pos+1] == c'=':
        return FILTER_APPROX_MATCH, pos + 2
    elif s[pos] == c'<' and s[pos+1] == c'=':
        return FILTER_LESS_OR_EQUAL, pos + 2
    elif s[pos] == c'>' and s[pos+1] == c'=':
        return FILTER_GREATER_OR_EQUAL, pos + 2
    else:
        raise QuerySyntaxError, (x, pos)

# [initial]*any*any*any*[final]

cdef object parse_substring (char * s, int pos, int slen):
    # assumes the presence of at least one splat
    cdef int i, start
    cdef list result = []
    start = 0
    i = 0
    while 1:
        if i == slen:
            if start != i:
                # final
                result.append (
                    _TLV (SUBSTRING_FINAL, FLAGS_CONTEXT, (unescape (s[start:]),))
                    )
            return result
        elif s[i] == c'*':
            if start == 0:
                if i > 0:
                    # initial
                    result.append (
                        _TLV (SUBSTRING_INITIAL, FLAGS_CONTEXT, (unescape (s[0:i]),))
                    )
            else:
                # any
                result.append (
                    _TLV (SUBSTRING_ANY, FLAGS_CONTEXT, (unescape (s[start:i]),))
                )
            # next bit will start *after* the splat
            start = i + 1
            i = i + 1
        else:
            i = i + 1

def ue (s):
    return unescape (s)

# # another possibility would be to access the 'characters'
# # array in stringobject.c directly.  [it's static, though]
# cdef bytes char (int ch):
#     if (ch < 0) or (ch >= 256):
#         raise ValueError, "chr() arg not in range (256)"
#     else:
#         return <char>ch

cdef int name_punc_table[256]
cdef int i

for i from 0 <= i < 256:
    if chr (i) in '()=<>~':
        name_punc_table[i] = 1
    else:
        name_punc_table[i] = 0

cdef object parse_name (bytes x, int pos):
    cdef int slen, is_substring, rpos, start
    cdef unsigned char * s
    s = <unsigned char *>x
    slen = len (x)
    rpos = 0
    start = pos
    if name_punc_table[s[pos]]:
        raise QuerySyntaxError, (x, pos)
    else:
        is_substring = 0
        # we expect names to be delimited by an operator or a close-paren
        while pos < slen:
            if not name_punc_table[s[pos]]:
                if s[pos] == c'*':
                    is_substring = 1
                rpos = rpos + 1
                if rpos == 4096:
                    raise QuerySyntaxError, (x, pos)
                pos = pos + 1
            else:
                return PyBytes_FromStringAndSize (<char *>(s + start), rpos), is_substring, pos
        else:
            raise QuerySyntaxError, (x, pos)

cdef object parse_value (bytes x, int pos):
    cdef int slen, is_substring, rpos, start
    cdef unsigned char * s
    s = <unsigned char *>x
    slen = len (x)
    rpos = 0
    start = pos
    is_substring = 0
    # we expect values to be delimited by a close-paren
    while pos < slen:
        if s[pos] != c')':
            if s[pos] == c'*':
                is_substring = 1
            rpos = rpos + 1
            if rpos == 4096:
                raise QuerySyntaxError, (x, pos)
            pos = pos + 1
        else:
            return PyBytes_FromStringAndSize (<char *>(s + start), rpos), is_substring, pos
    else:
        raise QuerySyntaxError, (x, pos)

cdef object unescape (bytes x):
    cdef int rpos, flag, pos
    cdef char * s = x
    cdef int slen = len (x)
    cdef char buffer[4096]
    cdef char ch
    pos = 0
    rpos = 0
    flag = 0
    while pos < slen:
        if s[pos] == c'\\':
            flag = 1
            pos = pos + 1
            ch, pos = parse_hex_escape (s, pos, slen)
        else:
            ch = s[pos]
            pos = pos + 1
        buffer[rpos] = ch
        rpos = rpos + 1
        if rpos == 4096:
            raise QuerySyntaxError, (x, pos)
    if flag:
        # return a new, unescaped string
        return PyBytes_FromStringAndSize (buffer, rpos)
    else:
        # return the original string
        return x

cdef int parse_hex_digit (int ch):
    if (ch >= 48 and ch <= 57):
        return (ch - 48)
    elif (ch >= 97 and ch <= 102):
        return (ch - 97) + 10
    elif (ch >= 65 and ch <= 70):
        return (ch - 65) + 10
    else:
        return -1

cdef object parse_hex_escape (char * s, int pos, int len):
    cdef char ch, result
    if pos + 2 > len:
        raise QuerySyntaxError, (s, pos)
    else:
        ch = parse_hex_digit (s[pos])
        if ch == -1:
            raise QuerySyntaxError, (s, pos)
        else:
            result = ch << 4
        pos = pos + 1
        ch = parse_hex_digit (s[pos])
        if ch == -1:
            raise QuerySyntaxError, (s, pos)
        else:
            result = result | ch
        pos = pos + 1
    return result, pos

cdef int escape_table[256]
for i from 0 <= i < 256:
    if chr (i) in '\\()=<>~*':
        escape_table[i] = 1
    else:
        escape_table[i] = 0

cdef bytes hex_digits = b"0123456789abcdef"

# 525486/sec
def query_escape (bytes s):
    cdef int slen, rlen, i, j
    cdef unsigned char ch
    cdef char * sbuf, * rbuf
    sbuf = s
    slen = len (s)
    rlen = slen
    # compute length of result
    for i from 0 <= i < slen:
        if escape_table[<unsigned char>sbuf[i]]:
            rlen = rlen + 2
    # create result string
    r = PyBytes_FromStringAndSize (NULL, rlen)
    rbuf = r
    # fill result string
    j = 0
    for i from 0 <= i < slen:
        ch = sbuf[i]
        if escape_table[ch]:
            rbuf[j+0] = <char> 92
            rbuf[j+1] = <char> hex_digits[ch >> 4]
            rbuf[j+2] = <char> hex_digits[ch & 0xf]
            j = j + 3
        else:
            rbuf[j] = ch
            j = j + 1
    return r
