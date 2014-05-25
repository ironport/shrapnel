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

# pull in visible bits of the low-level pyrex module
import coro
from coro.asn1.ber import *
from coro.ldap.query import *
import re

W = coro.write_stderr

re_dn = re.compile(r'\s*([,=])\s*')
re_dn_attr = re.compile(r'^([^,]+)(=[^,]+)(,.*)?$')

class ProtocolError (Exception):
    """An LDAP Protocol Error occurred"""
    pass

class Exit_Recv_Thread (Exception):
    "oob signal the ldap client recv thread to exit"
    pass

class LDAP:
    BindRequest                 = 0
    BindResponse                = 1
    UnbindRequest               = 2
    SearchRequest               = 3
    SearchResultEntry           = 4
    SearchResultDone            = 5
    SearchResultReference       = 19  # <--- NOT IN SEQUENCE
    ModifyRequest               = 6
    ModifyResponse              = 7
    AddRequest                  = 8
    AddResponse                 = 9
    DelRequest                  = 10
    DelResponse                 = 11
    ModifyDNRequest             = 12
    ModifyDNResponse            = 13
    CompareRequest              = 14
    CompareResponse             = 15
    AbandonRequest              = 16
    ExtendedRequest             = 23  # <--- NOT IN SEQUENCE
    ExtendedResponse            = 24

class SCOPE:
    BASE      = 0
    ONELEVEL  = 1
    SUBTREE   = 2

class DEREF:
    NEVER     = 0
    SEARCHING = 1
    FINDING   = 2
    ALWAYS    = 3

def encode_search_request (
    base_object,
    scope,
    deref_aliases,
    size_limit,
    time_limit,
    types_only,
    filter,
    which_attrs=None,
    compatibility={}
):
    if scope is None:
        scope = compatibility.get('scope', SCOPE.SUBTREE)
    if which_attrs is None:
        which_attrs = SEQUENCE()
    elif len(which_attrs) == 0:
        # Per section 4.5.1 of rfc 2251, if you really mean the empty
        # list, you can't pass the empty list because the empty list means
        # something else. You need to pass a list consisting of the OID 1.1,
        # which really (see sections 4.1.2, 4.1.4, and 4.1.5) isn't an OID
        # at all. Except some servers (Exchange 5.5) require something
        # different here, hence the lookup in the compatibility dict.
        which_attrs = SEQUENCE (
            OCTET_STRING (compatibility.get ('no_attr_attr', '1.1'))
        )
    else:
        which_attrs = SEQUENCE (*[OCTET_STRING (x) for x in which_attrs])
    return TLV (
        APPLICATION (LDAP.SearchRequest),
        OCTET_STRING (base_object),
        ENUMERATED (scope),
        ENUMERATED (deref_aliases),
        INTEGER (size_limit),
        INTEGER (time_limit),
        BOOLEAN (types_only),
        parse_query (filter),
        which_attrs,
    )

class AUTH:
    # 1 and 2 are reserved
    simple      = 0x00
    sasl        = 0x03

class RESULT:
    success                      = 0
    operationsError              = 1
    protocolError                = 2
    timeLimitExceeded            = 3
    sizeLimitExceeded            = 4
    compareFalse                 = 5
    compareTrue                  = 6
    authMethodNotSupported       = 7
    strongAuthRequired           = 8
    referral                     = 10
    adminLimitExceeded           = 11
    unavailableCriticalExtension = 12
    confidentialityRequired      = 13
    saslBindInProgress           = 14
    noSuchAttribute              = 16
    undefinedAttributeType       = 17
    inappropriateMatching        = 18
    constraintViolation          = 19
    attributeOrValueExists       = 20
    invalidAttributeSyntax       = 21
    noSuchObject                 = 32
    aliasProblem                 = 33
    invalidDNSyntax              = 34
    aliasDereferencingProblem    = 36
    inappropriateAuthentication  = 48
    invalidCredentials           = 49
    insufficientAccessRights     = 50
    busy                         = 51
    unavailable                  = 52
    unwillingToPerform           = 53
    loopDetect                   = 54
    namingViolation              = 64
    objectClassViolation         = 65
    notAllowedOnNonLeaf          = 66
    notAllowedOnRDN              = 67
    entryAlreadyExists           = 68
    objectClassModsProhibited    = 69
    affectsMultipleDSAs          = 71
    other                        = 80

class Error (Exception):

    def __init__ (self, answer):
        Exception.__init__ (self)
        self.code = answer[0]
        self.answer = answer
        self.error_string = result_string (answer[0])

    def __str__ (self):
        if len(self.answer) == 3:
            # We know how to parse it if it's length 3. Second element is
            # the "got DN", and third element is the error message. See
            # section 4 of RFC 1777.

            if self.answer[2]:
                parenthesize_got_dn = 1
                err_msg = " %r" % (self.answer[2],)
            else:
                parenthesize_got_dn = 0
                err_msg = ""

            if self.answer[1]:
                err_msg += " "
                if parenthesize_got_dn:
                    err_msg += "("
                err_msg += "Failed after successfully matching partial DN: %r" \
                           % (self.answer[1],)
                if parenthesize_got_dn:
                    err_msg += ")"
        else:
            err_msg = " %r" % (self.answer,)

        return '<LDAP Error "%s" [0x%x]%s>' % (self.error_string, self.code,
                                               err_msg)
    __repr__ = __str__

RESULT._reverse_map = r = {}
for attr in dir(RESULT):
    value = getattr (RESULT, attr)
    if isinstance(value, type(0)):
        r[value] = attr

def result_string (result):
    try:
        return RESULT._reverse_map[result]
    except KeyError:
        return "unknown error %r" % (result,)

def encode_bind_request (version, name, auth_data):
    assert (1 <= version <= 127)
    return TLV (
        APPLICATION (LDAP.BindRequest),
        INTEGER (version),
        OCTET_STRING (name),
        auth_data
    )

def encode_simple_bind (version, name, login):
    return encode_bind_request (
        version,
        name,
        TLV (
            CHOICE (AUTH.simple, 0),
            login
        )
    )

def encode_sasl_bind (version, name, mechanism, credentials=''):
    if credentials:
        cred = OCTET_STRING (credentials)
    else:
        cred = ''
    return encode_bind_request (
        version,
        name,
        TLV (
            CHOICE (AUTH.sasl),
            OCTET_STRING (mechanism),
            cred
        )
    )

def encode_starttls ():
    # encode STARTTLS request: RFC 2830, 2.1
    return TLV (
        APPLICATION (LDAP.ExtendedRequest),
        TLV (CHOICE (0, 0), '1.3.6.1.4.1.1466.20037')
    )

class client:

    # Note: default port is 389
    def __init__ (self, addr):
        self.msgid = 1
        self.addr = addr
        if isinstance (addr, tuple):
            self.sock = coro.tcp_sock()
        else:
            self.sock = coro.unix_sock()
        self.sock.connect (addr)
        self.pending = {}
        self.recv_thread_ob = coro.spawn (self.recv_thread)

    def recv_exact (self, size):
        try:
            return self.sock.recv_exact (size)
        except AttributeError:
            # tlslite has no recv_exact
            left = size
            r = []
            while left:
                block = self.sock.recv (left)
                if not block:
                    break
                else:
                    r.append (block)
                    left -= len (block)
            return ''.join (r)

    # XXX the ironport code had a simple buffering layer here, might want
    #  to reinstate that...
    def _recv_packet (self):
        # All received packets must be BER SEQUENCE. We can tell from
        # the header how much data we need to complete the packet.
        # ensure we have the sequence header - I'm inlining the (type,
        # length) detection here to get good buffering behavior
        tl = self.recv_exact (2)
        if not tl:
            return [None, None]
        tag = tl[0]
        if tag != '0':  # SEQUENCE | STRUCTURED
            raise ProtocolError ('bad tag byte: %r' % (tag,))
        l = ord (tl[1])
        p = [tl]
        if l & 0x80:
            # <l> tells us how many bytes of actual length
            ll = l & 0x7f
            len_bytes = self.recv_exact (ll)
            p.append (len_bytes)
            # fetch length
            n = 0
            for i in xrange (ll):
                n = (n << 8) | ord(len_bytes[i])
            if (n < 0) or (n > 1000000):
                # let's be reasonable, folks
                raise ProtocolError ('invalid packet length: %d' % (n,))
            need = n
        else:
            # <l> is the length of the sequence
            need = l
        # fetch the rest of the packet...
        p.append (self.recv_exact (need))
        packet = ''.join (p)
        reply, plen = decode (packet)
        return reply

    def recv_thread (self):
        while not self.exit_recv_thread:
            [msgid, reply] = self._recv_packet()
            if msgid is None:
                break
            else:
                probe = self.pending.get (msgid, None)
                if probe is None:
                    raise ProtocolError ('unknown message id in reply: %d' % (msgid,))
                else:
                    probe.schedule (reply)

    default_timeout = 10

    def send_message (self, msg):
        msgid = self.msgid
        self.msgid += 1
        self.sock.send (SEQUENCE (INTEGER (msgid), msg))
        try:
            self.pending[msgid] = me = coro.current()
            reply = coro.with_timeout (self.default_timeout, me._yield)
            return reply
        finally:
            del self.pending[msgid]

    # server replies NO:
    # starttls decoded=[1, ('application', 24, [2, '', 'unsupported extended operation'])]
    # server replies YES:
    # starttls decoded=[1, ('application', 24, [0, '', ''])]

    exit_recv_thread = False

    def starttls (self, *future_cert_params):
        import tlslite
        self.exit_recv_thread = True
        reply = self.send_message (encode_starttls())
        if reply[2] == 0:
            conn = tlslite.TLSConnection (self.sock)
            # does ldap allow client-cert authentication?
            conn.handshakeClientCert()
            self.osock = self.sock
            self.sock = conn
        # restart recv thread (maybe) with TLS socket wrapper
        self.exit_recv_thread = False
        self.recv_thread_ob = coro.spawn (self.recv_thread)
        return reply

    ldap_protocol_version = 3

    def simple_bind (self, name, login):
        return self.send_message (encode_simple_bind (self.ldap_protocol_version, name, login))

    def sasl_bind (self, name, mechanism, credentials):
        return self.send_message (encode_sasl_bind (self.ldap_protocol_version, name, mechanism, credentials))

def t0():
    sample = encode_message (
        3141,
        encode_search_request (
            'dc=nightmare,dc=com',
            SCOPE.SUBTREE,
            DEREF.NEVER,
            0,
            0,
            0,
            '(&(objectclass=inetorgperson)(userid=srushing))',
            # '(&(objectclass=inetorgperson)(userid=newton))',
            # ask for these specific attributes only
            ['mailAlternateAddress', 'rfc822ForwardingMailbox']
        )
    )

    import pprint
    import socket
    s = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
    s.connect (('127.0.0.1', 389))
    s.send (sample)
    pprint.pprint (decode (s.recv (8192)))

def t1():
    c = client (('127.0.0.1', 389))
    c.bind_simple (3, 'cn=manager,dc=nightmare,dc=com', 'fnord')
    return c

if __name__ == '__main__':
    import coro.backdoor
    coro.spawn (coro.backdoor.serve, unix_path='/tmp/ldap.bd')
    coro.event_loop()
