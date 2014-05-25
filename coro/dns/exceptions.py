# Copyright (c) 2002-2012 IronPort Systems and Cisco Systems
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

#
# dns_exceptions
#
# These are all the excpetions that can be raised by the DNS module.
#

import coro.dns.packet as packet

MAX_DNSRCODE = 65535

class DNS_Error(Exception):
    """Base class for DNS-related errors in this file.
    Do NOT use this directly!
    """
    pass

class DNS_Soft_Error (DNS_Error):
    def __init__(*args):
        """DNS_Soft_Error(qname, qtype, ip, error_string)"""
        DNS_Error.__init__ (*args)
        self, self.qname, self.qtype, self.nameserver, self.error_string = args

    def __str__(self):
        return 'DNS Soft Error looking up %s (%s) while asking %s. Error was: %s' % (
            self.qname, self.qtype, self.nameserver, self.error_string
        )

class DNS_Hard_Error (DNS_Error):
    def __init__(*args):
        """DNS_Hard_Error(qname, qtype, (dnsrcode, error_string))"""
        DNS_Error.__init__ (*args)
        self, self.qname, self.qtype, (self.dnsrcode, self.error_string) = args

    def __str__(self):
        return 'DNS Hard Error looking up %s (%s):  %s' % (
            self.qname, self.qtype, self.error_string
        )

class DNS_Many_Errors (DNS_Error):
    """A container class for multiple DNS errors.

    When looking up MX records we often have to look up A records and AAAA
    records. If one of the queries succeeds and one fails then we use the
    success result and carry on as normal.

    If both queries fail we need a way to communicate to the rest of the
    system (and mainly to log files) that there were two queries attempted and
    they both failed.
    """

    def __init__(self, exceptions):
        """Initialize ourselves.

        :Parameters:
            - `exceptions`: A list of exception instances.
        """
        self.exceptions = exceptions

    attributes_to_join = ('qname', 'qtype', 'error_string')

    def __getattr__(self, attrname):
        """If the attribute being requested is in `attributes_to_join` then
        request that attribute from all of the contained exceptions and
        join them with a newline. For any other attribute, the value
        returned is from the least severe exception."""

        self.exceptions = sorted(self.exceptions, key=self._exception_key_func)
        attr_values = [getattr(e, attrname) for e in self.exceptions if hasattr(e, attrname)]

        if not attr_values:
            raise AttributeError('None of \'%s\' inner exceptions has attribute \'%s\'' %
                                 (self.__class__.__name__, attrname))
        elif attrname in self.attributes_to_join:
            return '\n'.join(attr_values)
        else:
            return attr_values[0]

    def __str__(self):
        """Return all of the exception strings separated by newline."""
        exception_strings = []
        for e in self.exceptions:
            exception_strings.append(str(e))

        return 'Multiple DNS queries were attempted and failed: ' + \
            '\n'.join(exception_strings)

    def _exception_key_func(self, e):
        """This function helps to sort the contained exceptions in DNS_Many_Errors
        based on severity.

        If the given exception is not of type DNS_Hard_Error (no 'dnsrcode'
        attribute'), e.g. DNS_Soft_Error, it returns 0 so that it is treated as
        the least severe type. If the given exception is of type DNS_Hard_Error,
        then the value of the 'dnsrcode' attribute is evaluated. If the value is
        equal to dnsrcode.Refused then it returns MAX_DNSRCODE so that it is
        treated as the most severe type. NXDomain is considered as the next most
        severe type."""

        rcode = 0
        if hasattr(e, 'dnsrcode'):
            rcode = getattr(e, 'dnsrcode')
            if rcode == packet.RCODE.NXDomain:
                rcode = MAX_DNSRCODE - 1
            if rcode == packet.RCODE.Refused:
                rcode = MAX_DNSRCODE

        return rcode

class DNS_Many_Errors_Soft(DNS_Many_Errors, DNS_Soft_Error):
    pass

class DNS_Many_Errors_Hard(DNS_Many_Errors, DNS_Hard_Error):
    pass

class DNS_Lame_Error (DNS_Soft_Error):
    def __init__ (self, qname, qtype, ns_names):
        """DNS_Lame_Error(qname, qtype, ns_names)"""
        self.ns_names = ', '.join(map(lambda x: x[1], ns_names))
        DNS_Soft_Error.__init__ (
            self, qname, qtype, self.ns_names, 'Lame Delegation Error'
        )

    def __str__(self):
        return (
            'DNS Lame Delegation Error looking up %s (%s).'
            '  Nameserver list was: %s.' % (
                self.qname, self.qtype, self.ns_names
            )
        )

class DNS_Runaway_Query_Error(DNS_Soft_Error):
    def __init__(self, qname, qtype, ns_name):
        """DNS_Runaway_Query_Error(qname, qtype, ns_name)"""
        self.ns_name = ns_name
        DNS_Soft_Error.__init__ (
            self, qname, qtype, ns_name, 'Runaway Error'
        )

    def __str__(self):
        return (
            'DNS Runaway Error looking up %s (%s).'
            '  Nameserver was: %s.' % (self.qname, self.qtype, self.ns_name)
        )

class DNS_Malformed_Qname_Error (DNS_Hard_Error):
    def __str__(self):
        return 'DNS Malformed Query Error looking up %s (%s).' % (self.qname, self.qtype)

class DNS_Missing_Root_Data_Error (DNS_Soft_Error):
    def __init__(self):
        DNS_Soft_Error.__init__ (self, '', '', '', 'Missing Root Data Error')

    def __str__(self):
        return 'Failed to get root nameserver.'

class DNS_No_Local_Resolvers (DNS_Soft_Error):
    def __init__(self):
        DNS_Soft_Error.__init__ (self, '', '', '', 'No local DNS resolvers are running')

    def __str__(self):
        return 'No local DNS resolvers are running.'
