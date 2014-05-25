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

"""
ldapurl - handling of LDAP URLs as described in RFC 2255
written by Michael Stroeder <michael@stroeder.com>

See http://python-ldap.sourceforge.net for details.

\$Id: ldapurl.py,v 1.1 2007/04/07 06:30:26 tdraegen Exp $

Python compability note:
This module only works with Python 2.0+ since
1. string methods are used instead of module string and
2. list comprehensions are used.
"""

__version__ = '0.5.2'

__all__ = [
    # constants
    'SEARCH_SCOPE', 'SEARCH_SCOPE_STR',
    'LDAP_SCOPE_BASE', 'LDAP_SCOPE_ONELEVEL', 'LDAP_SCOPE_SUBTREE',
    # functions
    'isLDAPUrl',
    # classes
    'LDAPUrlExtension', 'LDAPUrlExtensions', 'LDAPUrl'
]

import UserDict

from urllib import quote, unquote

LDAP_SCOPE_BASE = 0
LDAP_SCOPE_ONELEVEL = 1
LDAP_SCOPE_SUBTREE = 2

SEARCH_SCOPE_STR = {None: '', 0: 'base', 1: 'one', 2: 'sub'}

SEARCH_SCOPE = {
    '': None,
    # the search scope strings defined in RFC2255
    'base': LDAP_SCOPE_BASE,
    'one': LDAP_SCOPE_ONELEVEL,
    'sub': LDAP_SCOPE_SUBTREE,
}

# Some widely used types
StringType = type('')
TupleType = type(())


def isLDAPUrl(s):
    """
    Returns 1 if s is a LDAP URL, 0 else
    """
    s_lower = s.lower()
    return \
        s_lower.startswith('ldap://') or \
        s_lower.startswith('ldaps://') or \
        s_lower.startswith('ldapi://')


def ldapUrlEscape(s):
    """Returns URL encoding of string s"""
    return quote(s).replace(',', '%2C').replace('/', '%2F')


class LDAPUrlExtension:
    """
    Class for parsing and unparsing LDAP URL extensions
    as described in RFC 2255.

    BNF definition of LDAP URL extensions:

         extensions = extension *("," extension)
         extension  = ["!"] extype ["=" exvalue]
         extype     = token / xtoken
         exvalue    = LDAPString from section 4.1.2 of [2]
         token      = oid from section 4.1 of [3]
         xtoken     = ("X-" / "x-") token

    Usable class attributes:
    critical
          Boolean integer marking the extension as critical
    extype
          Type of extension
    exvalue
          Value of extension
    """

    def __init__(self, extensionStr=None, critical=0, extype=None, exvalue=None):
        self.critical = critical
        self.extype = extype
        self.exvalue = exvalue
        if extensionStr:
            self._parse(extensionStr)

    def _parse(self, extension):
        extension = extension.strip()
        if not extension:
            # Don't parse empty strings
            self.extype, self.exvalue = None, None
            return
        self.critical = extension[0] == '!'
        if extension[0] == '!':
            extension = extension[1:].strip()
        self.extype, self.exvalue = extension.split('=', 1)
        self.extype = self.extype.strip()
        self.exvalue = unquote(self.exvalue.strip())

    def unparse(self):
        return '%s%s=%s' % (
            '!' * (self.critical > 0),
            self.extype, (self.exvalue or '').replace(',', r'%2C')
        )

    def __str__(self):
        return self.unparse()

    def __repr__(self):
        return '<%s.%s instance at %s: %s>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            hex(id(self)),
            self.__dict__
        )

    def __eq__(self, other):
        return \
            (self.critical == other.critical) and \
            (self.extype == other.extype) and \
            (self.exvalue == other.exvalue)

    def __ne__(self, other):
        return not self.__eq__(other)


class LDAPUrlExtensions(UserDict.UserDict):
    """
    Models a collection of LDAP URL extensions as
    dictionary type
    """

    def __init__(self, default=None):
        UserDict.UserDict.__init__(self)
        for k, v in (default or {}).items():
            self[k] = v

    def __setitem__(self, name, value):
        """
        value
            Either LDAPUrlExtension instance, (critical,exvalue)
            or string'ed exvalue
        """
        assert isinstance(value, LDAPUrlExtension)
        assert name == value.extype
        self.data[name] = value

    def values(self):
        return [
            self[k]
            for k in self.keys()
        ]

    def __str__(self):
        return ','.join(map(str, self.values()))

    def __repr__(self):
        return '<%s.%s instance at %s: %s>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            hex(id(self)),
            self.data
        )

    def __eq__(self, other):
        assert isinstance(other, self.__class__), TypeError(
            "other has to be instance of %s" % (self.__class__)
        )
        return self.data == other.data

    def parse(self, extListStr):
        for extension_str in extListStr.strip().split(','):
            e = LDAPUrlExtension(extension_str)
            self[e.extype] = e

    def unparse(self):
        return ','.join([v.unparse() for v in self.values()])


class LDAPUrl:
    """
    Class for parsing and unparsing LDAP URLs
    as described in RFC 2255.

    BNF definition of LDAP URL:

      hostport     host:port
      dn           distinguished name
      attributes   list with attributes
      scope        search scope string
      filter       LDAP search filter
      ldapurl    = scheme "://" [hostport] ["/"
                       [dn ["?" [attrs] ["?" [scope]
                       ["?" [filter] ["?" extensions]]]]]]

    Usable class attributes:
      urlscheme
          URL scheme (either ldap, ldaps or ldapi)
      hostport
          LDAP host (default '')
      dn
          String holding distinguished name (default '')
      attrs
          list of attribute types (default None)
      scope
          integer search scope for ldap-module
      filterstr
          String representation of LDAP Search Filters
          (see RFC 2254)
      extensions
          Dictionary used as extensions store
      who
          Maps automagically to bindname LDAP URL extension
      cred
          Maps automagically to X-BINDPW LDAP URL extension
    """

    attr2extype = {'who': 'bindname', 'cred': 'X-BINDPW'}

    def __init__(
        self,
        ldapUrl=None,
        urlscheme='ldap',
        hostport='', dn='', attrs=None, scope=None, filterstr=None,
        extensions=None,
        who=None, cred=None
    ):
        self.urlscheme = urlscheme
        self.hostport = hostport
        self.dn = dn
        self.attrs = attrs
        self.scope = scope
        self.filterstr = filterstr
        self.extensions = (extensions or LDAPUrlExtensions({}))
        if ldapUrl is not None:
            self._parse(ldapUrl)
        if who is not None:
            self.who = who
        if cred is not None:
            self.cred = cred

    def __eq__(self, other):
        return \
            self.urlscheme == other.urlscheme and \
            self.hostport == other.hostport and \
            self.dn == other.dn and \
            self.attrs == other.attrs and \
            self.scope == other.scope and \
            self.filterstr == other.filterstr and \
            self.extensions == other.extensions

    def __ne__(self, other):
        return not self.__eq__(other)

    def _parse(self, ldap_url):
        """
        parse a LDAP URL and set the class attributes
        urlscheme,host,dn,attrs,scope,filterstr,extensions
        """
        if not isLDAPUrl(ldap_url):
            raise ValueError('Parameter ldap_url does not seem to be a LDAP URL.')
        scheme, rest = ldap_url.split('://', 1)
        self.urlscheme = scheme.strip()
        if self.urlscheme not in ['ldap', 'ldaps', 'ldapi']:
            raise ValueError('LDAP URL contains unsupported URL scheme %s.' % (self.urlscheme))
        slash_pos = rest.find('/')
        qemark_pos = rest.find('?')
        if (slash_pos == -1) and (qemark_pos == -1):
            # No / and ? found at all
            self.hostport = unquote(rest)
            self.dn = ''
            return
        else:
            if slash_pos != -1 and (qemark_pos == -1 or (slash_pos < qemark_pos)):
                # Slash separates DN from hostport
                self.hostport = unquote(rest[:slash_pos])
                # Eat the slash from rest
                rest = rest[slash_pos + 1:]
            elif qemark_pos != 1 and (slash_pos == -1 or (slash_pos > qemark_pos)):
                # Question mark separates hostport from rest, DN is assumed to be empty
                self.hostport = unquote(rest[:qemark_pos])
                # Do not eat question mark
                rest = rest[qemark_pos:]
            else:
                raise ValueError('Something completely weird happened!')
        paramlist = rest.split('?')
        paramlist_len = len(paramlist)
        if paramlist_len >= 1:
            self.dn = unquote(paramlist[0]).strip()
        if (paramlist_len >= 2) and (paramlist[1]):
            self.attrs = unquote(paramlist[1].strip()).split(',')
        if paramlist_len >= 3:
            scope = paramlist[2].strip()
            try:
                self.scope = SEARCH_SCOPE[scope]
            except KeyError:
                raise ValueError(
                    "Search scope must be either one of base, one or sub. LDAP URL contained %s" %
                    (repr(scope)))
        if paramlist_len >= 4:
            filterstr = paramlist[3].strip()
            if not filterstr:
                self.filterstr = None
            else:
                self.filterstr = unquote(filterstr)
        if paramlist_len >= 5:
            self.extensions = LDAPUrlExtensions()
            self.extensions.parse(paramlist[4])
        return

    def applyDefaults(self, defaults):
        """
        Apply defaults to all class attributes which are None.

        defaults
            Dictionary containing a mapping from class attributes
            to default values
        """
        for k in defaults.keys():
            if getattr(self, k) is None:
                setattr(self, k, defaults[k])

    def initializeUrl(self):
        """
        Returns LDAP URL suitable to be passed to ldap.initialize()
        """
        if self.urlscheme == 'ldapi':
            # hostport part might contain slashes when ldapi:// is used
            hostport = ldapUrlEscape(self.hostport)
        else:
            hostport = self.hostport
        return '%s://%s' % (self.urlscheme, hostport)

    def unparse(self):
        """
        Returns LDAP URL depending on class attributes set.
        """
        if self.attrs is None:
            attrs_str = ''
        else:
            attrs_str = ','.join(self.attrs)
        scope_str = SEARCH_SCOPE_STR[self.scope]
        if self.filterstr is None:
            filterstr = ''
        else:
            filterstr = ldapUrlEscape(self.filterstr)
        dn = ldapUrlEscape(self.dn)
        if self.urlscheme == 'ldapi':
            # hostport part might contain slashes when ldapi:// is used
            hostport = ldapUrlEscape(self.hostport)
        else:
            hostport = self.hostport
        ldap_url = '%s://%s/%s?%s?%s?%s' % (
            self.urlscheme,
            hostport, dn, attrs_str, scope_str, filterstr
        )
        if self.extensions:
            ldap_url = ldap_url + '?' + self.extensions.unparse()
        return ldap_url

    def htmlHREF(self, urlPrefix='', hrefText=None, hrefTarget=None):
        """Complete """
        assert isinstance(urlPrefix, StringType), "urlPrefix must be StringType"
        if hrefText is None:
            hrefText = self.unparse()
        assert isinstance(hrefText, StringType), "hrefText must be StringType"
        if hrefTarget is None:
            target = ''
        else:
            assert isinstance(hrefTarget, StringType), "hrefTarget must be StringType"
            target = ' target="%s"' % hrefTarget
        return '<a%s href="%s%s">%s</a>' % (
            target, urlPrefix, self.unparse(), hrefText
        )

    def __str__(self):
        return self.unparse()

    def __repr__(self):
        return '<%s.%s instance at %s: %s>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            hex(id(self)),
            self.__dict__
        )

    def __getattr__(self, name):
        if name in self.attr2extype:
            extype = self.attr2extype[name]
            if extype in self.extensions:
                result = unquote(self.extensions[extype].exvalue)
            else:
                return None
        else:
            raise AttributeError("%s has no attribute %s" % (
                self.__class__.__name__, name
            ))
        return result  # __getattr__()

    def __setattr__(self, name, value):
        if name in self.attr2extype:
            extype = self.attr2extype[name]
            if value is None:
                # A value of None means that extension is deleted
                delattr(self, name)
            elif value is not None:
                # Add appropriate extension
                self.extensions[extype] = LDAPUrlExtension(
                    extype=extype, exvalue=unquote(value)
                )
        else:
            self.__dict__[name] = value

    def __delattr__(self, name):
        if name in self.attr2extype:
            extype = self.attr2extype[name]
            try:
                del self.extensions[extype]
            except KeyError:
                pass
        else:
            del self.__dict__[name]
