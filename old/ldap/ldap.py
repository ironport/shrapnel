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
from _ldap import *
import re

re_dn = re.compile(r'\s*([,=])\s*')
re_dn_attr = re.compile(r'^([^,]+)(=[^,]+)(,.*)?$')

class ProtocolError (Exception):
    """An LDAP Protocol Error occurred"""
    pass

class LDAP:
    BindRequest                 = 0
    BindResponse                = 1
    UnbindRequest               = 2
    SearchRequest               = 3
    SearchResultEntry           = 4
    SearchResultDone            = 5
    SearchResultReference       = 19 # <--- NOT IN SEQUENCE
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
    ExtendedRequest             = 23 # <--- NOT IN SEQUENCE
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
    if (type(value) == type(0)):
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

    # SEQUENCE(OCTET_STRING('1.3.6.1.4.1.1466.20037'), )
    # SEQUENCE('1.3.6.1.4.1.1466.20037')
    return TLV (
        APPLICATION(LDAP.ExtendedRequest),
        TLV (CHOICE (0, 0), '1.3.6.1.4.1.1466.20037')
        )

def encode_abandon(message_id):
    return TLV(APPLICATION(LDAP.AbandonRequest),
               INTEGER(message_id))

def encode_message (message_id, data):
    "encode/wrap an LDAP protocol message"
    #controls = SEQUENCE() # controls NYI, optional
    #return SEQUENCE (INTEGER (message_id), data, controls)
    return SEQUENCE (INTEGER (message_id), data)

def match_leaf(path, scope, leaf, base):
    """Match a  combination of leaf and base against a path
    based on scope.  path is the full DN returned by LDAP server.
    leaf and base form the match pattern.

    :Parameters:
        - `path`: Value of DN returned by the server(For example,
          the 'memberOf' attribute returned by AD server)
        - 'scope': Depth from the base DN to which search is performed.
          Can be one of SCOPE.* values
        - 'leaf': Leftmost part of the match pattern.  Usually it is
           CN=<groupname> for AD group matching.
        - 'base':  Rightmost part of the match pattern.  It is the base DN
          of LDAP server configured for external authentication with unnecessary
          spaces stripped.

          It is assumed that all DNs returnd by AD server does not have any
          spaces between values and attributes.  However, admin can configure
          baseDN with spaces between values and attributes. Before matching,
          such spaces are removed.
          For Ex: cn     =    admin_group,   cn  =   Users
                  is stripped to
                  cn=admin_group,cn=Users

    :Return:
        True if the leaf and base match the path in the given scope.
        Else False.
    """
    base = re_dn.sub(r'\1', base).strip()
    if scope == SCOPE.ONELEVEL:
        if path == ('%s,%s' % (leaf, base)):
            return True
    if scope == SCOPE.SUBTREE:
        if path.startswith(leaf) and path.endswith(base):
            return True
    return False

def normalize_dn(dn):
    """The first "cn" is assumed to be the Group Name and is case-sensitive.
    While the rest of the string is the base dn, which is supposed to be
    case-insensitive. Normalization is done accordingly.
    Ex: cn=admin_group,cn=Users,dc=ad1,dc=ibqa normalizes to
        CN=admin_group,CN=USERS,DC=AD1,DC=IBQA
    """
    dn = re_dn_attr.match(dn)
    return dn.group(1).upper() + dn.group(2) + dn.group(3).upper()

if __name__ == '__main__':
    sample = encode_message (
        3141,
        encode_search_request (
            'dc=ironport,dc=com',
            SCOPE.SUBTREE,
            DEREF.NEVER,
            0,
            0,
            0,
            '(&(objectclass=inetorgperson)(userid=srushing))',
            #'(&(objectclass=inetorgperson)(userid=newton))',
            # ask for these specific attributes only
            ['mailAlternateAddress', 'rfc822ForwardingMailbox']
            )
        )

    import pprint
    import socket
    s = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
    s.connect (('printers.ironport.com', 389))
    s.send (sample)
    pprint.pprint (decode (s.recv (8192)))
