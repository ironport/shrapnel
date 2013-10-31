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

"""DNS cache object.

:Variables:
    - `dns_request`: counter.  Incremented for each top-level query
      (not incremented for additional queries required for recursive queries).
    - `net_request`: counter.  A query is being sent over the network.
    - `cache_hit`: counter.  A value was successfully retrieved from
      the cache. This does not include expired entries.
    - `cache_miss`: counter.  A value was not found in the cache. This
      does not include expired entries.
    - `cache_exception`: counter.  A "negative" cache entry was hit.
    - `cache_expired`: counter.  A value was found in the cache, but
      has expired.
"""

# Two kinds of negatively-cached data
CACHE_NXDOMAIN = "NXDOMAIN"
CACHE_NODATA   = "NODATA"

# how long (in seconds) to cache non-rfc2308 negative responses
DEFAULT_NEGATIVE_TTL = 0

# limit on the amount of work we will do for any one query
RUNAWAY = 40

# limit on the amount of gluelessness we will take for any one query
GLUELESSNESS = 3

DEFAULT_MIN_TTL = 1800

# Goals:
# 1) paranoia
# 2) do not sacrifice safety for performance; i.e., send extra queries to be safe.
# 3) performance

# TODO:
# truncation (although very rare)
# pay attention to depth of gluelessness?
# flag lame NS in cache
# Add a placeholder in the cache so that while
#   a query is executing, new threads don't try to do the same query.
# detect servers that are down, and discourage their use (w/eventual rehabilitation)
# support unknown dns data types so djb doesn't embarrass us

# BUGS
# I bet we get confused if we get an empty list of IP's for a nameserver.
#

# QUESTIONS
# how common is it for a nameserver to have more than one address (from the internet)?
# djb doesn't appear to care about the AA bit?

# ===========================================================================
# It'd be nice if there were a set of 'test' domains along with some queries
# that would act as a regression test for correctness.  Another possibility
# would be a test server that would provide canned responses to do the same.
#
#                      *** THIS IS WORTH DOING ***
#
# ===========================================================================

# See rfc2181 for many clarifications to rfc1035.

# section 5.3.3 of rfc1034

#  1) must reply always come from the IP we sent it to? [yes. djb even uses a connected socket]
#  2) can we insist on authoritative data?

# updated Feb 2013
# dig @a.root-servers.net.
raw_hints = """\
a.root-servers.net.	3600000	IN	A	198.41.0.4
a.root-servers.net.	3600000	IN	AAAA	2001:503:ba3e::2:30
b.root-servers.net.	3600000	IN	A	192.228.79.201
c.root-servers.net.	3600000	IN	A	192.33.4.12
d.root-servers.net.	3600000	IN	A	199.7.91.13
d.root-servers.net.	3600000	IN	AAAA	2001:500:2d::d
e.root-servers.net.	3600000	IN	A	192.203.230.10
f.root-servers.net.	3600000	IN	A	192.5.5.241
f.root-servers.net.	3600000	IN	AAAA	2001:500:2f::f
g.root-servers.net.	3600000	IN	A	192.112.36.4
h.root-servers.net.	3600000	IN	A	128.63.2.53
h.root-servers.net.	3600000	IN	AAAA	2001:500:1::803f:235
i.root-servers.net.	3600000	IN	A	192.36.148.17
i.root-servers.net.	3600000	IN	AAAA	2001:7fe::53"""

# filtered below if !ipv6
root_hints = [ x.split()[4] for x in raw_hints.split('\n') ]

def domain_suffix (a, b):
    # is b a suffix of a?
    if a == '' or a == b:
        return 1
    else:
        la = len(a)
        return b[-la:] == a and b[-(la+1)] == '.'

class timeouts:

    """Used to control the timeouts used for queries.
    If there is one possible server, it uses a 60-second timeout.
    If there is two servers, then there is a 15-second timeout for the first
    and a 45 second timeout for the second.
    3: 5, 10, 45
    4: 1, 3, 11, 45
    5: 1, 3, 11, 45, 1
    6: 1, 3, 11, 45, 1, 1
    etc.
    """


    def __init__ (self, n):
        self.index = 0
        self.values = self.times (n)

    def times (self, n):
        """Generate the timeout list for n servers."""
        if n == 1:
            return [60]
        elif n == 2:
            return [15, 45]
        elif n == 3:
            return [5, 10, 45]
        elif n >= 4:
            return [1, 3, 11, 45]

    def next (self):
        """Return the next timeout value."""
        if self.index >= len(self.values):
            return 1
        else:
            self.index += 1
            return self.values[self.index-1]

class Work:

    def __init__ (self):
        self.work = 0
        self.glue = 0

    def indent (self):
        return '  ' * self.work

    # XXX need to decide *exactly* what constitutes work, and where's the
    #     best place in the code to do the increment.  One obvious answer
    #     is in the query() function itself - but a more finessed answer
    #     might be in cache_get().  That would catch CNAME loops that are
    #     entirely in the cache.  Think of any other types of loops that
    #     might not require calls to query() or cache_get().

    def incr (self, qname, qtype, ns_name=''):
        self.work += 1
        if self.work >= RUNAWAY:
            raise DNS_Runaway_Query_Error (qname, qtype, ns_name)

    def incr_glue (self):
        self.glue += 1

class dns_cache:

    # If parent_ns is set, then it should be a dictionary:
    # {domain: ns_list}
    # Domain should be a string such as "ironport.com".
    # ns_list should be a list of (TTL, ns_name) tuples.
    # A domain of the empty string is used if none of the other domains match.
    # More specific domains "win", so "sfo.ironport.com" would get used over
    # "ironport.com" for something like "foo.sfo.ironport.com".
    #
    # Entries in ns_list will be processed in order.
    parent_ns = None

    # Turns on/off debug log calls.
    debug = False

    def __init__ (self, cache_size=10000, negative_ttl=DEFAULT_NEGATIVE_TTL, ttl_min=DEFAULT_MIN_TTL):
        self.cache = lru_with_pin (cache_size)
        # hardcode localhost, TTL=0 means never expire
        self._pin_localhost()
        # The maximum number of parallel queries allowed
        self.max_outstanding = 500
        # used to control the concurrency
        self.outstanding_sem = coro.semaphore(self.max_outstanding)

        self.bootstrap_cv = coro.condition_variable()
        self.source_ip = ''
        self.negative_ttl = negative_ttl
        self.flush_callbacks = []
        self.use_actual_ttl = 0
        self.ttl_min = ttl_min

    def log (self, *args):
        coro.write_stderr (repr(args) + '\n')

    def _pin_localhost(self):
        """_pin_localhost() -> None
        Adds the localhost entries to the pinned cache.
        """
        self.cache.pin (('localhost','A'), [(0, '127.0.0.1')])
        self.cache.pin (('localhost','AAAA'), [(0, '::1')])
        self.cache.pin (('1.0.0.127.in-addr.arpa','PTR'), [(0, 'localhost')])
        self.cache.pin (
            ('1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.ip6.arpa.', 'PTR'),
            [(0, 'localhost')]
            )

    def empty(self, pinned_as_well = 0):
        """empty(self, pinned_as_well = 0) -> None
        Clears out the cache.
        Be sure to know what you are doing when setting pinned_as_well.
        """
        self.cache.empty(pinned_as_well)
        if pinned_as_well:
            self._pin_localhost()

    def build_request (self, qid, name, qtype, qclass, recursion):
        """build_request (self, qid, name, qtype, qclass, recursion)
        Build a request packet.  Returns the raw packet as a string."""
        m = packet.Packer()
        h = packet.Header()
        h.id = qid
        h.opcode = packet.OPCODE.QUERY
        h.rd = recursion
        h.qdcount = 1
        m.addHeader (h)
        qtype_code = getattr (packet.TYPE, qtype)
        m.addQuestion (name, qtype_code, qclass)
        return m.getbuf()

    def send_request (self, request, use_tcp=0):
        """send_request (self, request)
        Send a request over a socket.  request is a tuple:
        qid, ip, (qname, qtype, qclass, recursion)
        Returns a dns_reply object.
        """
        net_request.inc()
        qid, ip, (qname, qtype, qclass, recursion) = request
        r = self.build_request (qid, qname, qtype, qclass, recursion)
        import struct
        try:
            if ':' in ip:
                sfamily = coro.AF.INET6
            else:
                sfamily = coro.AF.INET
            if use_tcp:
                stype = coro.SOCK.STREAM
            else:
                stype = coro.SOCK.DGRAM
            s = coro.make_socket (sfamily, stype)
        except OSError, why:
            self.log ('COMMON.APP_FAILURE', tb.traceback_string() + ' why: ' + str(why))
            raise DNS_Soft_Error, (qname, qtype, ip, str(why))

        try:
            try:
                if self.source_ip:
                    s.bind((self.source_ip,0))
                s.connect ((ip, 53))
                while 1:
                    if use_tcp:
                        r = struct.pack ('>h', len(r)) + r
                    n = s.send (r)
                    if n != len(r):
                        self.log('DNS.NETWORK_ERROR', 'send', ip, qname)
                        raise DNS_Soft_Error, (qname, qtype, ip, 'Failed to send all data.')
                    if use_tcp:
                        rlen_bytes = s.recv_exact(2)
                        rlen, = struct.unpack ('>H', rlen_bytes)
                        # rlen is the length of the packet (not including the 2 rlen bytes)
                        data = s.recv_exact(rlen)
                    else:
                        # UDP
                        # 1024 - ~PyStringObject overhead (which is actually 20 bytes)
                        # RFC actually limits it to 512 bytes
                        data = s.recv (1000)
                    try:
                        reply = unpack_reply (data, use_actual_ttl=self.use_actual_ttl, ttl_min=self.ttl_min)
                    except packet.UnpackError:
                        self.log('DNS.RESPONSE_ERROR', repr(data), ip, qname)
                        raise DNS_Soft_Error, (qname, qtype, ip, 'Packet was corrupted.')
                    except:
                        self.log('COMMON.APP_FAILURE', tb.traceback_string() + ' REPR:' + repr(data))
                        raise DNS_Soft_Error, (qname, qtype, ip, 'Unknown Error')
                    if reply.id != qid:
                        # probably a DoS attack...
                        self.log('DNS.RESPONSE_ERROR', 'id(%i)!=qid(%i)' % (reply.id, qid), ip, qname)
                        # ... don't let 'em hog us
                        coro.sleep_relative (1)
                    elif reply.rcode and reply.rcode != packet.RCODE.NXDomain:
                        rcode = packet.RCODE_MAP.get (reply.rcode, str(reply.rcode))
                        self.log('DNS.RESPONSE_ERROR', 'rcode=%s data=%r' % (rcode, repr(data)), ip, qname)
                        raise DNS_Soft_Error, (qname, qtype, ip, rcode)
                    else:
                        return reply
            except OSError, why:
                self.log('DNS.NETWORK_ERROR', why, ip, qname)
                raise DNS_Soft_Error (qname, qtype, ip, str(why))
            except EOFError:
                # recv_exact will raise EOFError if it doesn't get enough data.
                self.log('DNS.NETWORK_ERROR', 'EOF', ip, qname)
                raise DNS_Soft_Error (qname, qtype, ip, 'EOF')
        finally:
            s.close()

    def do_query(self, q, ip):
        """do_query(self, q, ip)
        Execute a request to the given IP.
        q is a query tuple of (qname, qtype, qclass, recursion)
        This will generate the query ID.
        Returns a dns_reply object.
        """
        if self.outstanding_sem.avail<=0:
            # we've hit a system resource limit
            # we use max_outstanding twice here because the log message wants "current" and "max"
            # but these are always going to be the same in the dns server
            self.log('DNS.LIMIT', self.max_outstanding, self.max_outstanding)
        self.outstanding_sem.acquire(1)
        try:
            qid = dns_random (65536)
            reply = self.send_request ((qid, ip, q))
            if reply.tc:
                # truncated, try tcp
                qid = dns_random (65536)
                return self.send_request ((qid, ip, q), use_tcp=1)
            else:
                return reply
        finally:
            self.outstanding_sem.release(1)

    # ==================================================
    # resolver algorithm, cache management
    # ==================================================

    def bootstrap_cache (self):
        """bootstrap_cache(self)
        Bootstrap the cache.  Seeds the initial root servers
        into the cache starting with root_hints."""
        if self.need_bootstrapping==2:
            # bootstrapping is already in progress
            # wait for it to finish
            # 60 seconds should be a good timeout to prevent an infinite hang
            try:
                coro.with_timeout (60, self.bootstrap_cv.wait)
            except coro.TimeoutError:
                pass
            if self.need_bootstrapping:
                # the bootstrapping process failed
                self.log('DNS.BOOTSTRAP_FAILED')
                raise DNS_Soft_Error, ('', 'NS', 'bootstrapping', 'Failed to bootstrap the DNS cache.')
        elif self.need_bootstrapping==1:
            # need to bootstrap the cache
            self.need_bootstrapping = 2
            try:
                try:
                    self._bootstrap_cache()
                except:
                    self.need_bootstrapping = 1
                    raise
            finally:
                self.bootstrap_cv.wake_all()

    def _bootstrap_cache (self):
        if self.parent_ns:
            self.need_bootstrapping = 0
            return

        self.log('DNS.STRAPPING')
        # XXX try them all w/timeout schedule...
        for ip in permute (root_hints):
            try:
                result = self.query_by_ip ('', 'NS', ip, 5.0, Work())
                # Check that the reply is kosher.  We have seen situations
                # where root server responses had an empty reply.
                if not result.an or not result.ar:
                    continue
                d = {}
                for kind, rname, ttl, data in result.an:
                    d[data] = ttl
                records_with_matching_glue = []
                for kind, rname, ttl, data in result.ar:
                    if d.has_key (rname) and kind in ('A', 'AAAA'):
                        # record glue with TTL=0 (never expires)
                        self.encache (rname, kind, [(0, data)], permanent=1)
                        records_with_matching_glue.append(rname)
                if not records_with_matching_glue:
                    # Hm, none of the glue matches the answer.  I've never
                    # seen this, but might as well guard against it.
                    continue
                # Only record entries that had matching glue records.
                # Otherwise, we'd stick glueless NS entries into the cache,
                # and that can cause problems.
                self.encache ('', 'NS', [(0,ns) for ns in records_with_matching_glue], permanent=1)
                self.log('DNS.STRAPPED')
                self.need_bootstrapping = 0
                return
            except DNS_Error:
                pass
            except coro.TimeoutError:
                pass
        self.log('DNS.BOOTSTRAP_FAILED')
        raise DNS_Soft_Error, ('', 'NS', 'bootstrapping', 'Failed to bootstrap the DNS cache.')

    def authoritative (self, name, base):
        "is a reply from server for <base> authoritative for <name>?"
        # 1) if equal, yes
        # 2) if a subdomain of <base>, yes.
        # 3) root servers are authoritative for everything [scary]
        return domain_suffix (base, name)

    def authoritative_ns (self, ns_name, domain):
        "check the cache to see if <ns_name> happens to be authoritative for <domain>"
        while domain:
            for ttl, name in self.cache_get (domain, 'NS', ()):
                if ns_name == name:
                    return 1
            domain = self.up_domain (domain)
        return 0

    def up_domain (self, name):
        if not name:
            raise DNS_Missing_Root_Data_Error
        i = name.find ('.')
        if i == -1:
            return ''
        else:
            return name[i+1:]

    def merge_answers (self, key, new):
        """merge new data with data from the cache for key=(qname,qtype)"""
        old = self.cache.get (key, None)
        if old is None:
            return new
        else:
            d = {}
            for ttl, data in old:
                if data not in (CACHE_NODATA, CACHE_NXDOMAIN):
                    d[data] = ttl
            for ttl, data in new:
                d[data] = ttl
            return [ (ttl, data) for (data, ttl) in d.items() ]

    def encache (self, qname, qtype, answers, permanent=0, stomp=0):
        """encache (self, qname, qtype, answers, permanent=0)
        Add qname/qtype with results 'answers' into the cache.
        If permanent, the value is permanent in the cache."""
        if self.debug:
            self.log('DNS.ENCACHE', qname, qtype, answers)
        key = (qname, qtype)
        if permanent:
            self.cache.pin (key, answers)
        else:
            if stomp:
                self.cache[key] = answers
            else:
                self.cache[key] = self.merge_answers (key, answers)

    def _cache_get (self, key, instead):
        # This function acts as a ttl-expiring front end to self.cache.get().
        # If a record exists but has a ttl that has expired, this
        # function will expire it and pretend it never existed.  This
        # simplifies the work in the 'real' cache_get() method.
        probe = self.cache.get (key, instead)
        if probe is instead:
            return instead
        else:
            # check for any expired TTL's.  If we find one, act as if
            # every record has expired. [XXX justify this policy]
            for ttl, data in probe:
                # TTL of zero means it's a permanent entry
                if ttl and (coro.now > ttl):
                    cache_expired.inc()
                    # blow away stale data
                    del self.cache[key]
                    # pretend the record was never there
                    return instead
            else:
                # nothing expired, return the record
                return probe

    def cache_get (self, qname, qtype, instead=None, work=None):
        """cache_get (self, qname, qtype, instead)
        Returns the value in the cache for qname/qtype.
        If it isn't in the cache, it returns 'instead'.
        """
        #coro.print_stderr ('cache_get(%r,%r)\n' % (qname, qtype))
        if work is None:
            work = Work()
        work.incr (qname, qtype)
        cname_probe = self._cache_get ((qname, 'CNAME'), instead)
        if cname_probe is not instead:
            # follow CNAME in the cache as well
            ttl, cname = cname_probe[0]
            return self.cache_get (cname, qtype, instead, work)
        else:
            val = self._cache_get ((qname, qtype), instead)
            if val is instead:
                cache_miss.inc()
                return instead
            else:
                cache_hit.inc()
                ttl0, data0 = val[0]
                if data0 is CACHE_NXDOMAIN:
                    # negative cache
                    cache_exception.inc()
                    raise DNS_Hard_Error, (qname, qtype, (packet.RCODE.NXDomain, 'NXDomain'))
                elif data0 is CACHE_NODATA:
                    # negative cache
                    # [XXX in what way does this qualify as an exception?]
                    cache_exception.inc()
                    return []
                else:
                    return val

    # 0 - no
    # 1 - yes
    # 2 - in progress
    need_bootstrapping = 1

    def best_nameserver (self, qname):
        "the best nameserver for <qname> in our cache"
        if self.need_bootstrapping:
            self.bootstrap_cache()
        while 1:
            ns = self.cache_get (qname, 'NS', None)
            if ns is None:
                # will terminate with qname == ''
                qname = self.up_domain (qname)
            else:
                return ns, qname

    def _pick_parent_ns_fast(self, domain):
        # This is a performance hack.  Most people do not override domains in
        # their dns configuration.  No need to spin cycles doing the
        # "up_domain" thing.  This function is dynamically replaced via the
        # configuration management code in PrioritizedIP.py.
        return self.parent_ns['']

    def _pick_parent_ns_slow(self, domain):
        while 1:
            if self.parent_ns.has_key(domain):
                return self.parent_ns[domain]
            # This will raise an exception if domain=='' which should never
            # happen because parent_ns should always have a '' entry.
            domain = self.up_domain(domain)

    _pick_parent_ns = _pick_parent_ns_slow

    def query (self, qname, qtype, work=None, no_cache=0, timeout=None):
        """query (self, qname, qtype, work=[0], no_cache=0)
        Return the result [(ttl, value),...] of qname/qtype
        timeout supplies a manual override to generated timeouts based on number of servers
        """
        qname = qname.lower()
        # This function doesn't support the 'ANY' query.  use query_by_{name,ip} instead.
        # Why, you say? because ANY returns *many* types of records,
        #  whereas this method returns a *specific* type of record.  In other words,
        #  query_by_{name,ip}() return a <dns_reply> object, but this method returns
        #  a list of answers (i.e., <dns_reply.an>).
        if work is None:
            dns_request.inc()
            work = Work()
        if self.debug:
            self.log ('DNS.QUERY', 'Q', work.indent(), "%r, %r" % (qname, qtype))
        if not packet.dot_sane (qname):
            raise DNS_Malformed_Qname_Error, (qname, qtype, (packet.RCODE.ServFail, ''))
        if not no_cache:
            results = self.cache_get (qname, qtype, None)
            if results is not None:
                return results
        # what's the best NS we have in the cache?
        if self.parent_ns:
            ns_names = self._pick_parent_ns(qname)
            zone = ""
        elif work.glue > GLUELESSNESS:
            # once we go past our tolerance for gluelessness, force
            # things to start back at the root...
            self.log ('DNS.GLUELESSNESS', qname, qtype)
            ns_names, zone = self.best_nameserver ('')
            work.glue = 0
        else:
            ns_names, zone = self.best_nameserver (qname)

        last_dns_soft_error = None
        while 1:
            r = None
            lame_count = 0

            t = timeouts (len(ns_names))
            to = timeout

            if not self.parent_ns:
                # Don't permute when using recursive resolvers since they are
                # ordered in a specific prioritized fashion.
                ns_names = permute (ns_names)
            for ttl, ns_name in ns_names:
                # timeout override check
                if timeout == None:
                    to = t.next()

                try:
                    r = self.query_by_name (qname, qtype, ns_name, to, work)

                except DNS_Soft_Error, why:
                    # try the next nameserver...
                    last_dns_soft_error = why

                except DNS_Hard_Error:
                    # nameserver doesn't exist. dripping in lameness.
                    lame_count += 1

                except DNS_Lame_Error:
                    # all the nameservers for *this* nameserver are lame.
                    lame_count += 1

                else:
                    cname = None
                    soa = None
                    ref_zone = None
                    results = []
                    referrals = []

                    # collect answers...
                    for kind, rname, ttl, data in r.an:
                        if kind == qtype and self.authoritative (rname, zone):
                            results.append ((ttl, data))
                        elif kind == 'CNAME':
                            cname = ttl, data

                    # collect referrals

                    for kind, rname, ttl, data in r.ns:
                        # should we check that all <rname> are equal?
                        if kind == 'NS':
                            if ref_zone is None:
                                #coro.print_stderr ('ref %s %s\n' % (repr(rname), repr(data)))
                                ref_zone = rname
                                referrals.append ((ttl, data))
                            elif ref_zone == rname:
                                referrals.append ((ttl, data))
                            else:
                                self.log('DNS.ODD_AUTHORITY', r.ns)
                        elif kind == 'SOA':
                            # XXX should we cache SOA?
                            soa = rname, ttl, data

                    # scan the additional records for glue...
                    for kind, rname, ttl, data in r.ar:
                        if kind in ('A', 'AAAA'):
                            if self.authoritative (rname, zone):
                                if self.debug:
                                    self.log('DNS.GLUE.ACCEPT', rname, zone, data, ns_name)
                                self.encache (rname, kind, [(ttl, data)])
                            elif self.authoritative_ns (ns_name, rname):
                                if self.debug:
                                    self.log('DNS.GLUE.ACCEPT.LUCKY', rname, zone, data, ns_name)
                                self.encache (rname, kind, [(ttl, data)])
                            else:
                                if self.debug:
                                    self.log('DNS.GLUE.DENY', rname, zone, data, ns_name)

                    # 1.``The query was not answered because the query name is an alias. I need to
                    # change the query name and try again.'' This applies if the answer section of the
                    # response contains a CNAME record for the query name and CNAME does not match the
                    # query type.

                    if cname and qtype != 'CNAME':
                        self.encache (qname, 'CNAME', [cname])
                        if self.debug:
                            self.log('DNS.FOLLOWING_CNAME', qname, cname)
                        return self.query (cname[1], qtype, work)

                    # 2.``The query name has no records answering the query, and is also guaranteed to
                    # have no records of any other type.'' This applies if the response code is NXDOMAIN
                    # and #1 doesn't apply. The amount of time that this information can be cached
                    # depends on the contents of the SOA record in the authority section of the
                    # response, if there is one.

                    elif not results and r.rcode == packet.RCODE.NXDomain:
                        if soa:
                            self.encache (qname, qtype, [(soa[1], CACHE_NXDOMAIN)], stomp=1)
                        elif self.negative_ttl:
                            ttl = (self.negative_ttl * coro.ticks_per_sec) + coro.now
                            self.encache (qname, qtype, [(ttl, CACHE_NXDOMAIN)], stomp=1)
                        if self.debug:
                            self.log('DNS.NXDOMAIN', qname, qtype)
                        raise DNS_Hard_Error, (qname, qtype, (r.rcode, packet.RCODE_MAP[r.rcode]))

                    # 3.``The query name has one or more records answering the query.''  This applies if
                    # the answer section of the response contains one or more records under the query
                    # name matching the query type, and #1 doesn't apply, and #2 doesn't apply.

                    elif results:
                        self.encache (qname, qtype, results)
                        return results

                    # 4.``The query was not answered because the server does not have the answer. I need
                    # to contact other servers.'' This applies if the authority section of the response
                    # contains NS records, and the authority section of the response does not contain
                    # SOA records, and #1 doesn't apply, and #2 doesn't apply, and #3 doesn't apply. The
                    # ``other servers'' are named in the NS records in the authority section.

                    elif referrals and not soa:

                        # lame example:
                        # we ask sca02.sec.dns.exodus.net, which is supposed to be an NS for briefcase.com
                        # it replies with a referral to 'com', and gives us the gtld servers.
                        # djb detects this with:
                        # if (dns_domain_equal(referral,control) || !dns_domain_suffix(referral,control)) {...}

                        # 'unlameness'.  sometimes queries will get here and show up as lame when they're
                        # not.  An SOA query will appear lame if the SOA really belongs to a parent of
                        # of qname.  The SOA will appear in the authority section correctly tagged with the
                        # parent domain name.  Special case we're not going to need since we don't normally
                        # do SOA queries.

                        if (zone == ref_zone or not domain_suffix (zone, ref_zone)):
                            lame_count += 1
                            self.log('DNS.LAME_REFERRAL', ns_name, zone, ref_zone, referrals, qname)
                            # now go to the next name server, i.e., continue in for ns_name...
                        else:
                            self.encache (ref_zone, 'NS', referrals)
                            ns_names, zone = referrals, ref_zone
                            # break out of ns_names loop so we can follow the referral
                            break

                    # 5.``The query name has no records answering the query, but it may have records of
                    # another type.'' This applies if #1 doesn't apply, and #2 doesn't apply, and #3
                    # doesn't apply, and #4 doesn't apply. The amount of time that this information can
                    # be cached depends on the contents of the SOA record in the authority section, if
                    # there is one.

                    else:
                        if soa:
                            self.encache (qname, qtype, [(soa[1], CACHE_NODATA)], stomp=1)
                        elif self.negative_ttl:
                            ttl = (self.negative_ttl * coro.ticks_per_sec) + coro.now
                            self.encache (qname, qtype, [(ttl, CACHE_NODATA)], stomp=1)
                        return []
            else:
                if lame_count == len(ns_names):
                    # all servers were lame (either lame delegation or DNS Hard Error)
                    raise DNS_Lame_Error (qname, qtype, ns_names)
                else:
                    # None of the servers worked...at least 1 return DNS Soft Error)
                    if last_dns_soft_error is None:
                        ns_names_list = ', '.join ([x[1] for x in ns_names])
                        raise DNS_Soft_Error (qname, qtype, ns_names_list, 'All nameservers failed.')
                    else:
                        raise last_dns_soft_error


    def query_by_name (self, qname, qtype, ns_name, timeout, work):
        """query_by_name (self, qname, qtype, ns_name, timeout, work)
        Send the query qname/qtype to the nameserver 'ns_name'.
        Returns a dns_reply object.
        """

        if self.debug:
            self.log('DNS.QUERY', 'QN', work.indent(), "%r, %r, %r" % (qname, qtype, ns_name))
        work.incr (qname, qtype)
        # do we have this glue in the cache?
        addrs = self.cache_get (ns_name, 'A', None)

        # XXX IPv6 caching the root servers and/or TLD servers doesn't work
        # right. We end up in infinite recursion trying to find AAAA results
        # for hosts that don't actually have AAAAs. The world eventually
        # rights itself but not after a lot of trying. Need to do something
        # better here.
        #v6_addrs = self.cache_get (ns_name, 'AAAA', None)

        if addrs is None:
            work.incr_glue()
            addrs = self.query (ns_name, 'A', work, no_cache=True)
        #if v6_addrs is None:
            #work.incr_glue()
            #print "up", qname, "but no entry for ns server", ns_name
            #v6_addrs = self.query (ns_name, 'AAAA', work, no_cache=True)
            #print "6 Lookup glue for", ns_name, "got results", repr(v6_addrs)

        if not addrs:
            raise DNS_Soft_Error (qname, qtype, ns_name, 'Empty reply for NS IP.')

        for ttl, ip in permute (addrs):
            # Don't send queries to 127.xx or 0.xx.  On a production system we
            # have our resolver listening on 127.0.0.1.  If a hostname has
            # a nameserver with the IP of 127.0.0.1, this would cause a flurry
            # of queries going to ourself.
            if not ip.startswith('127.') and not ip.startswith('0.'):
                try:
                    return self.query_by_ip (qname, qtype, ip, timeout=timeout, work=work)
                except coro.TimeoutError:
                    pass
                except DNS_Soft_Error:
                    pass

        raise DNS_Soft_Error (qname, qtype, ns_name, 'unable to reach nameserver on any valid IP')

    def query_by_ip (self, qname, qtype, ip, timeout, work):
        """query_by_ip (self, qname, qtype, ip, timeout, work)
        Send the query qname/qtype to the nameserver 'ip'.
        Returns a dns_reply object.
        """
        if self.debug:
            self.log('DNS.QUERY', 'QIP', work.indent(), "%r,%r,%r,%d" % (qname, qtype, ip, int(timeout)))
        if self.parent_ns:
            recursion = 1
        else:
            recursion = 0
        q = (qname, qtype, packet.CLASS.IN, recursion)
        return coro.with_timeout (timeout, self.do_query, q, ip)

    def __delitem__ (self, key):
        del self.cache[key]

def permute (x):
    if len(x) == 1:
        return x
    else:
        x0 = list (x)
        random.shuffle (x0)
        return x0

import coro
import coro.dns
import coro.dns.packet as packet
from coro.dns.surf import dns_random, set_seed
import random
from coro import tb
import coro
import socket
from coro.dns.exceptions import *
from coro.lru import lru_with_pin
from coro.dns.reply import unpack_reply

import os
set_seed (os.urandom (128))

if not coro.has_ipv6():
    root_hints = [ x for x in root_hints if not ':' in x ]

class resolver:
    def __init__ (self):
        self.cache = dns_cache()

    def gethostbyname (self, name, qtype):
        for ttl, addr in permute (self.cache.query (name, qtype)):
            return addr

    def resolve_ipv4 (self, name):
        return self.gethostbyname (name, 'A')

    def resolve_ipv6 (self, name):
        return self.gethostbyname (name, 'AAAA')

def install():
    "install the builtin resolver into the coro socket layer"
    coro.set_resolver (resolver())

# emulate 'statsmon' module
class StaticCounter:
    def __init__ (self, name):
        self.name = name
        self.val = 0
    def inc (self):
        self.val += 1
    def __repr__ (self):
        return '<counter %r %r>' % (self.name, self.val)

dns_request     = StaticCounter('dns_request')
net_request     = StaticCounter('net_request')
cache_hit       = StaticCounter('cache_hit')
cache_miss      = StaticCounter('cache_miss')
cache_exception = StaticCounter('cache_exception')
cache_expired   = StaticCounter('cache_expired')

if __name__ == '__main__':
    import backdoor
    d = dns_cache()
    d.debug = True
    coro.spawn (backdoor.serve)
    coro.event_loop (30.0)
