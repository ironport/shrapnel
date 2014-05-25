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

import coro
import coro.dns.packet as packet

# XXX move this into packet.pyx?

class dns_reply:
    """A reply to a DNS query.
    self.rcode -> The rcode of the query.
    self.q     -> List of question tuples (qname, qtype, qclass)
    self.an    -> List of answer tuples (typename, name, ttl, DATA)
    self.ns    -> List of nameserver tuples (typename, name, ttl, DATA)
    self.ar    -> List of additional record tuples (typename, name, ttl, DATA)
    DATA depends on the type of the RR entry.
    """

    def __init__ (self):
        self.rcode = 0
        self.q  = []
        self.an = []
        self.ns = []
        self.ar = []
        self.aa = 0
        self.id = 0
        self.tc = 0

    def __repr__ (self):
        return '<dns_reply rcode=%d q:%s an:%s ns:%s ar:%s>' % (
            self.rcode, self.q, self.an, self.ns, self.ar
        )


def get_rr (u, use_actual_ttl=0, ttl_min=1800):
    """get_rr (u, use_actual_ttl=0)
    Unpack and return an RR entry as
    (typename, name, ttl, DATA)
    Where DATA depends on the type of the RR.
    <use_actual_ttl>, if true, avoids using the minimum TTL.
    <min_ttl>, minimum TTL.
    """
    name, type, klass, ttl, rdlength = u.getRRheader()

    if klass != packet.CLASS.IN:
        return None
    else:
        typename = packet.TYPE_MAP[type]
        mname = 'get%sdata' % typename
        # convert ttl from relative to absolute
        # minimum ttl is <ttl_min> mins

        if not use_actual_ttl:
            ttl = max(ttl, ttl_min)

        ttl = (ttl * coro.ticks_per_sec) + coro.now
        if hasattr (u, mname):
            return (typename, name, ttl, getattr(u, mname)())
        else:
            return (typename, name, ttl, u.getbytes(rdlength))

def unpack_reply (reply, use_actual_ttl=0, ttl_min=1800):
    """unpack_reply (reply)
    Given a reply packet, it returns a dns_reply object."""
    u = packet.Unpacker(reply)
    h = u.getHeader()
    # ID - 16-bit identifier
    # QR - boolean query=0 response=1
    # AA - authoritative answer
    # TC - Truncation
    # RD - Recursion Desired
    # RA - Recursion Available
    # Z  - Reserved
    r = dns_reply()
    r.rcode = h.rcode
    r.aa = h.aa
    r.id = h.id
    r.tc = h.tc
    if h.tc:
        # don't bother trying to unpack the rest of the response, it's
        # likely to be mangled.
        pass
    else:
        __pychecker__ = 'unusednames=x'
        r.q  = [u.getQuestion() for x in range (h.qdcount)]
        r.an = filter (None, [get_rr (u, use_actual_ttl, ttl_min) for x in range (h.ancount)])
        r.ns = filter (None, [get_rr (u, use_actual_ttl, ttl_min) for x in range (h.nscount)])
        r.ar = filter (None, [get_rr (u, use_actual_ttl, ttl_min) for x in range (h.arcount)])
    return r
