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

# TODO:
#
# - most of the client API is done; what's not:
#       add "max_inflight_ldap_operations" value
#       Make this dynamic, based on round-trip time for a gold star.
# - BIND handling:
#   - bug 28550
# - Put a bound on the size of the server-group's unattached_inquiries list
#   Existing code has no bound.
# - Handle abandoning of inquiries (eg, if search time takes too long (read_timeout))

import copy
import coro
import coro_ssl
import dnsqr
import dnsrcode
import dns_exceptions
import inet_utils
import ldap
import ldapurl
import ldap_api
import ldap_cmd
import lru
import math
import sslip
import sys
import tb

PROTOCOL_VERSION = 3

TRANSPORT_PLAINTEXT = 0
TRANSPORT_SSL = 1
TRANSPORT_STARTTLS = 2

DEFAULT_COMPATIBILITY = {}
DEFAULT_INQUIRY_TIMEOUT = 120
DEFAULT_MAX_CONNS = 1
DEFAULT_MAX_TIME_PER_CONN = 21600
DEFAULT_MAX_REQUESTS_PER_CONN = 10000

CONNECT_BEHAVIOR_LOAD_BALANCE = 0
CONNECT_BEHAVIOR_FAILOVER = 1

DEFAULT_CACHE_SIZE = 10000
DEFAULT_CACHE_TTL = 0

DEFAULT_FAILOVER_TIMEOUT = 120
DEFAULT_READ_TIMEOUT = 30

MAX_REFERRAL_DEPTH = 10

PORT_LDAP = 389
PORT_LDAPS = 636

# Special processing for the error
INQUIRY_TIMED_OUT = 'inquiry timed out'

######################################################################
# INQUIRIES
#
# Inquiries encapsulate an individual LDAP Operation.  Inquiries contain
# a conditional variable on which routines can wait until resolution has
# been reached.
#
# Every supported LDAP Operation is implemented by a derived Inquiry
# class.  Each subclass then implements Operation specific result
# handling.
#
# Referral handling is a special case.  In order to follow a referral,
# an inquiry can request the ldap_client to follow the referral until it
# terminates.  In this regard, as much as possible inquiries are kept
# separate from the underlying transport.
#
# There is a twist wrt referral handling.  Referrals can include
# operation-modifying parameters.  This means that chains of referrals
# can incrementally change the original parameters; therefore, referrals
# themselves are a tuple of (parameters, URI).  By combining the two
# elements, a new operation is capable of progressing.
######################################################################
class Inquiry (object):

    __slots__ = \
        ('birth',              # Time this inquiry was created, in coro ticks.
         'timeout',            # Time this inquiry should live, in coro ticks.
         'state',              # UNATTACHED, ATTACHED, or DONE
         'rendered_request',   # Either None or a packed LDAP message, as string
         'cv',                 # None or a condition variable
         'result',             # None or a (success, result) tuple
         'referrals',          # List of referrals to follow
         'done_referrals',     # List of already followed referrals
         'resolver',           # The ldap server "(host:port)" services this inquiry.
         # taken from the ldap_connection where this inquiry
         # is resolved
         )
    STATE_UNATTACHED = 0
    STATE_ATTACHED = 1
    STATE_DONE = 2

    def __init__(self, server_group, rendered_request, timeout):
        self.server_group = server_group
        self.birth = coro.now
        self.timeout = timeout
        self.state = self.STATE_UNATTACHED
        self.rendered_request = rendered_request
        self.cv = coro.condition_variable()
        self.result = None
        self.referrals = []
        self.done_referrals = []
        self.resolver = None

    def state_to_timeout(self):
        self.state = self.STATE_DONE
        self.rendered_request = None
        self.result = (False, INQUIRY_TIMED_OUT)
        cv = self.cv
        if cv:
            self.cv = None
            cv.wake_all()

    def state_to_attached(self):
        assert(self.rendered_request is not None)
        self.state = self.STATE_ATTACHED
        return self.rendered_request

    def state_to_unattached(self):
        self.state = self.STATE_UNATTACHED

    def value_to_referral_list(self, value):
        """value_to_referral_list(value)
        Convert a fresh-from-BER-decoding referral into the list of
        parameter + URIs.

        Value is (result, base, search, ('context', 3, [uri list]))."""
        try:
            uri_list = value[3][2]
            for uri in uri_list:
                self.referrals.append((self.get_parameters(), uri))
        except IndexError:
            pass

    def handle_referrals(self):
        if self.referrals and not self.server_group:
            log.write('LDAP.DEBUG', "Could not follow referral: referral returned for transport-layer LDAP operation")
            return False

        while self.referrals and \
                (len(self.done_referrals) < MAX_REFERRAL_DEPTH):

            # Referrals are FIFO
            params, ref = self.referrals.pop(0)
            if ref in self.done_referrals:
                continue
            self.done_referrals.append(ref)

            # Tell the client to follow this referral
            if self.server_group.inquiry_referral(self, params, ref):
                log.write('LDAP.DEBUG', "Following referral: %s" % (ref,))
                return True
            else:
                log.write('LDAP.DEBUG', "Could not follow referral: %s" % (ref,))

        return False

    def handle_continuations(self):
        """handle_continuations()
        Search continuation handling hook.  Only Search inquiries need
        to override."""
        return False

    def state_to_done(self, success, result, resolver=None):
        if self.state is self.STATE_DONE:
            return

        assert(self.cv is not None)

        # Handle referrals before allowing completion
        if self.handle_referrals():
            return

        # Search continuation hook
        if self.handle_continuations():
            return

        cv = self.cv

        if self.state is self.STATE_UNATTACHED:
            self.rendered_request = None

        self.resolver = resolver
        self.state = self.STATE_DONE
        self.cv = None

        # Fix up results of (True, None).  These are referrals that
        # end without being resolved (no servers around to follow).
        # So, if result is (True, None) and we've followed some
        # referrals without actually getting data, return the right
        # thing.
        if (success is True) and (result is None) and \
           len(self.done_referrals) and (self.result is None):
            self.result = (False, "Referral following yielded no result.")
        else:
            self.result = (success, result)

        if cv:
            cv.wake_all()

    def wait_on_cv(self):
        # See bug 33294.  If cv doesn't exist, the inquiry has been
        # resolved before a cache-context has had a chance to update.
        if self.cv is not None:
            self.cv.wait()

    def get_rendered_operation(self):
        return self.rendered_request

    def get_result(self):
        return self.result

    def get_birth(self):
        return self.birth

    def get_parameters(self):
        raise Exception("Implement get_parameters()")
        return None

    def process_response(self, response):
        """Common processing."""
        try:
            kind, op, value = response
        except (ValueError, TypeError):
            return (False, 'Cannot find kind/code/answer: %s' % (response,))
        if kind != ldap.kind_application:
            return (False, '"kind" not application: %s' % (response,))

        # Note: any LDAPResult can return a result code of "referral".
        # At this point in processing we don't know if this response is
        # in fact an LDAPResult -- it could be an intermediary search
        # result.

        return self._inquiry_specific_processing(op, value)

    def _inquiry_specific_processing(self, op, value):
        """Derived classes must implement this."""
        __pychecker__ = 'unusednames=op,value'
        raise Exception("Implement process_response()")

    def update_from_referral(self, params, lurl):
        """update_from_referral(parameters, LDALUrl)
        Update this Inquiry with referral information.
        See RFC 4511 section 4.1.10
        """
        __pychecker__ = 'unusednames=params,lurl'
        raise Exception("Implement update_from_referral()")

    def get_time_to_live(self):
        """Return how much time left (in seconds) before this inquiry should
        be timed out if not resolved
        """
        time_to_live = (self.birth + self.timeout - coro.now) / float(coro.ticks_per_sec)
        if time_to_live > 0.0:
            return time_to_live
        else:
            return 0.0


class Inquiry_StartTLS(Inquiry):
    """Inquiry_StartTLS - object to implement StartTLS handling."""

    def __init__(self, server_group, timeout):
        Inquiry.__init__(self, server_group, ldap.encode_starttls(), timeout)

    def get_parameters(self):
        return None

    def _inquiry_specific_processing(self, op, value):
        # StartTLS specific handling
        if op == ldap.LDAP.ExtendedResponse:
            try:
                if value[0] == ldap.RESULT.success:
                    return (True, None)
                elif value[0] == ldap.RESULT.referral:
                    self.value_to_referral_list(value)
                    return (True, None)
                else:
                    # bug 22139, paranoid check for protocol error from
                    # the server
                    return (False, 'Got error response from starttls, '
                            'but cannot parse the error: %r' % value)
            except (IndexError, TypeError):
                return (False, 'Cannot find reponse to starttls: %r' % value)
        else:
            return (False, 'Unexpected response code: %r' % op)

    def update_from_referral(self, params, lurl):
        """update_from_referral(parameters, LDALUrl)
        Update this Inquiry with referral information.
        See RFC 4511 section 4.1.10

        StartTLS inquiries are parameterless, therefore referrals do not
        affect the previously encoded Operation.
        """
        __pychecker__ = 'unusednames=params,lurl'
        pass

class Inquiry_Simple_Bind(Inquiry):
    """Inquiry_Simple_Bind - object to encapsulate BindRequest (with
    "simple" authentication) handling."""

    def __init__(self, server_group, user, pword, timeout):
        Inquiry.__init__(self, server_group,
                         ldap.encode_simple_bind(PROTOCOL_VERSION, user, pword),
                         timeout)
        self.user = user
        self.pword = pword

    def get_parameters(self):
        return (self.user, self.pword)

    def _inquiry_specific_processing(self, op, value):
        # BIND specific handling
        if op == ldap.LDAP.BindResponse:
            try:
                if value[0] == ldap.RESULT.success:
                    return (True, True)
                elif value[0] == ldap.RESULT.referral:
                    self.value_to_referral_list(value)
                    return (True, None)
                else:
                    return (True, False)
            except (IndexError, TypeError):
                return (False, 'Cannot find response to bind: %r' % (value,))
        else:
            return (False, 'Unexpected response code: %r' % (value,))

    def update_from_referral(self, params, lurl):
        """update_from_referral(parameters, LDALUrl)
        Update this Inquiry with referral information.
        See RFC 4511 section 4.1.10

        Except for username and password, simple BIND inquiries are
        parameterless, therefore referrals do not affect the previously
        encoded Operation.
        """
        __pychecker__ = 'unusednames=params,lurl'
        pass

class Inquiry_Search(Inquiry):
    """Inquiry_Search - object to implement LDAP Search handling."""

    def __init__(self, server_group, base, query_str, look_for_attrs,
                 compatibility, timeout):
        encoded_req = ldap.encode_search_request(base, None,
                                                 ldap.DEREF.NEVER, 0, 0,
                                                 0, query_str,
                                                 look_for_attrs,
                                                 compatibility)
        Inquiry.__init__(self, server_group, encoded_req, timeout)
        self.base = base
        self.query_string = query_str
        self.look_for_attrs = look_for_attrs
        self.compatibility = compatibility
        self.search_results = []
        self.continuations = []  # search-specific form of referral
        self.explored_continuations = []

    def get_parameters(self):
        return (self.base, self.query_string, self.look_for_attrs, self.compatibility)

    def _inquiry_specific_processing(self, op, value):
        # Search specific handling
        #
        # Includes continuation handling -- aka search-based referrals
        if op == ldap.LDAP.SearchResultEntry:
            try:
                result_dn, attrs = value
                self.search_results.append((result_dn, dict(attrs)))
            except (ValueError, TypeError):
                return (False, 'Cannot decode DN and attributes/values: %r' % (value,))
            return (None, 'continue')
        elif op == ldap.LDAP.SearchResultDone:
            if value[0] == ldap.RESULT.success:
                return (True, self.search_results)
            elif value[0] == ldap.RESULT.referral:
                self.value_to_referral_list(value)
                return (True, None)
            elif value[0] == ldap.RESULT.noSuchObject:
                # if the searched object does not exist and we are done
                # searching, we should treat it as not-found, instead of
                # server-error (return status of False indicate server error)
                log.write('LDAP.DEBUG', value[2])  # log the error message
                return (True, [])
            else:
                return (False, value)
        elif op == ldap.LDAP.SearchResultReference:
            if not isinstance(value, list):
                value = [value]
            for val in value:
                self.continuations.append((self.get_parameters(), val))
            return (None, 'continue')
        else:
            return (False, 'Unexpected response code: %r' % (value,))

    def handle_continuations(self):
        """handle_continuations()
        Search continuation handling hook.  Class Inquiry_Search
        overrides."""
        if self.continuations and not self.server_group:
            log.write(
                'LDAP.DEBUG',
                "Could not follow continuations: continuation returned for transport-layer LDAP operation")
            return False

        while self.continuations and \
                (len(self.explored_continuations) < MAX_REFERRAL_DEPTH):

            # Continuations are FIFO
            params, c = self.continuations.pop(0)
            if c in self.explored_continuations:
                continue
            self.explored_continuations.append(c)

            # Tell the client to follow this continuation
            if self.server_group.inquiry_continuation(self, params, c):
                log.write('LDAP.DEBUG', "Query %s following continuation: %s" % (self.get_query_string(), c))
                return True
            else:
                log.write('LDAP.DEBUG', "Query %s could not follow continuation: %s" % (self.get_query_string(), c))

        return False

    def get_query_string(self):
        """get_query_string()
        Return query string for logging use."""
        return self.query_string

    def update_from_referral(self, params, lurl):
        """update_from_referral(parameters, LDALUrl)
        Update this Inquiry with referral information.
        See RFC 4511 section 4.1.10

        Search inquiries are affected by DN, filter, scope, "other"
        modifications.  For now we only care about DN and filter.
        """
        self.base, self.query_string, self.look_for_attrs, self.compatibility = params
        if lurl.dn:
            self.base = lurl.dn
        if lurl.filterstr:
            self.query_string = lurl.filterstr
        encoded_req = ldap.encode_search_request(self.base, None,
                                                 ldap.DEREF.NEVER, 0, 0,
                                                 0, self.query_string,
                                                 self.look_for_attrs,
                                                 self.compatibility)
        self.rendered_request = encoded_req

######################################################################
# CACHE ENTRIES
#
# This class encapsulates an LDAP response.  If no response exists, this
# class provides the interface between the calling thread and the inner
# workings of the ldap_client.
######################################################################
class ldap_cache_entry:

    CACHE_STATE_NEW = 0
    CACHE_STATE_INPROGRESS = 1
    CACHE_STATE_RESOLVED = 2

    def __init__(self, key):
        self.key = key
        self.when = 0
        self.data = ((False, None), None)
        self.inquiry = None
        self.state = self.CACHE_STATE_NEW
        self.resolver = None

    def abort(self, sg_ctx):
        self._set_data((False, []))
        self._state_to_resolved(sg_ctx)

    def _state_to_resolved(self, sg_ctx):
        # Delete this entry from the nascent cache list
        try:
            del sg_ctx.new_cache[self.key]
        except KeyError:
            pass

        # Results will stick around for cache-ttl time
        self._set_time(coro.now)

        # Update state
        self.state = self.CACHE_STATE_RESOLVED

    def _set_resolved(self, sg_ctx):
        """_set_resolved(sg_ctx)
        Resolve a cache-entry.  Supplied server-group object is required
        to place the cache-entry into the correct cache."""
        if not self._is_resolved():
            self._set_data(self.inquiry.get_result(), self.inquiry.resolver)
            self._state_to_resolved(sg_ctx)

            # Free up the inquiry
            self.inquiry = None

            # Place this ldap_cache_entry into the appropriate
            # cache (positive or negative).
            (success, result), resolver = self.data
            if sg_ctx.cache_size:

                # A positive cache hit is considered to be an inquiry
                # that both successfully resolved *and* contains
                # non-empty information.
                if success:
                    if result:
                        if not sg_ctx.pos_cache:
                            sg_ctx.pos_cache = lru.lru(sg_ctx.cache_size)
                        sg_ctx.pos_cache[self.key] = self
                    elif sg_ctx.is_ready():
                        # Only add to the neg cache if the server is operational
                        # ie. do not cache transport, or server failure results
                        if not sg_ctx.neg_cache:
                            sg_ctx.neg_cache = lru.lru(sg_ctx.cache_size)
                        sg_ctx.neg_cache[self.key] = self

    def _is_resolved(self):
        return (self.state == self.CACHE_STATE_RESOLVED)

    def _set_inprogress(self):
        self.state = self.CACHE_STATE_INPROGRESS

    def _set_data(self, data, resolver=None):
        """Store the ldap query result for this Inquiry

        :Parameters:
            - 'data' : result from ldap query resolution as a tuple
                       (<server status>, <ldap result>)
            - 'resolver' : the ldap server where the result is obtained
        """
        try:
            status, result = data
            self.data = ((status, result), resolver)
        except (TypeError, ValueError):
            self.data = ((False, []), resolver)
        except:
            self.data = ((False, []), resolver)
            raise

    def get_data(self, sg_ctx):
        """Return the query's result.  This call might block if the inquiry
        has not been resolved.

        :Parameters:
            - 'sg_ctx' : the server group handing this query

        :Return:
            ((server_status, results), resolver)
        """
        if self._is_resolved():
            return self.data

        def __wait_on_inquiry(ce, sg):
            ce.inquiry.wait_on_cv()
            ce._set_resolved(sg)
            return ce.data

        if not sg_ctx.is_down():
            # Wait for query resolve if the server is not down
            try:
                return coro.with_timeout(self.inquiry.get_time_to_live(), __wait_on_inquiry, self, sg_ctx)
            except coro.TimeoutError:
                # At this point, the inquiry has passed its timeout
                if self.inquiry:
                    self.inquiry.state_to_timeout()
                    self._set_resolved(sg_ctx)
                return self.data
        else:
            if self.check_ttl_expired(sg_ctx):
                return self.data
            else:
                return ((False, "LDAP server misconfigured or unreachable"), None)

    def check_ttl_expired(self, sg_ctx):
        """ This function checks if this entry has inquiry that is older than
        the inquiry time-to-live. If it is older, it sets the inquiry state to
        timeout and deletes it from the new_cache.

        :Returns:
            - True - if the entry was stale
            - False - Otherwise
        """
        if self.inquiry.get_time_to_live() <= 0:
            self.inquiry.state_to_timeout()
            self._set_resolved(sg_ctx)
            log.write('LDAP.DEBUG', "Cleared stale entry: %s" % (self.key,))
            return True

        return False

    def _set_time(self, time):
        self.when = time

    def set_inquiry(self, inquiry):
        self._set_inprogress()
        self.inquiry = inquiry

######################################################################
# CLIENT
#
# The ldap_client class is the global context.  It contains the
# one-per-process library-like initialization data.  It also acts
# as a container for server-groups.
######################################################################
class ldap_client:
    def __init__(self):
        self.server_groups = {}

    # server group API
    def create_server_group(self, name, behavior=CONNECT_BEHAVIOR_FAILOVER,
                            bind_ip=None):
        """ Create and return an empty server-group. """
        if name in self.server_groups:
            return None
        self.server_groups[name] = ldap_server_group(self, name, behavior,
                                                     bind_ip)
        return self.server_groups[name]

    def get_server_group(self, name):
        """ Given a server-group name, return an object. """
        return self.server_groups.get(name, None)

    def remove_server_group(self, name):
        """ Remove an existing server-group. """
        try:
            self.server_groups[name].shutdown()
            del self.server_groups[name]
        except KeyError:
            return

    def destroy_client(self):
        for sg in self.server_groups.values():
            sg.shutdown()

    # cache API
    def clear_all_caches(self):
        """ Clear all caches. """
        for sg in self.server_groups.values():
            sg.clear_cache(True)

    # Referral helper
    def find_server(self, host, port):
        """ Find a server. """
        for sg in self.server_groups.values():
            for server in sg.servers:
                if server.hostname == host and \
                   int(server.port) == int(port):
                    return server
        return None

######################################################################
# SERVER GROUPS
#
# The server-group class is a collection of servers.  A collection can
# be in either a "failover" or a "round-robin" configuration.
#
# This class also maintains the inquiry cache, which provides an
# interface between the application (which is essentially doing a simple
# query) and the mechanics of resolving LDAP operations.
#
# This class exposes the query API to the application.  To the
# application, only "searching" and "binding" are currently exposed.
#
# Finally, this class utilizes a single worker thread to manage servers,
# deal with configuration updates, and to manage the resolution of
# inquiries.
######################################################################
def LDAPUrl_to_host_port(lurl):
    host = None
    port = None
    try:
        colon = lurl.hostport.index(':')
    except ValueError:
        host = lurl.hostport
        if lurl.urlscheme == 'ldaps':
            port = PORT_LDAPS
        else:
            port = PORT_LDAP
    else:
        host = lurl.hostport[:colon]
        port = lurl.hostport[colon + 1:]
    return(host, port)

class ldap_server_group:    # server container

    def __init__(self, client, name, behavior, bind_ip):
        self.client = client
        self.name = name
        self.sg_thread = None
        self.servers = []
        self.server_pos = 0
        self.connection_behavior = behavior
        self.bind_ip = bind_ip
        self.new_cache = {}     # Nascent cache entries
        self.pos_cache = None   # LRU-based cache for positive results
        self.neg_cache = None   # LRU-based cache for negative results
        self.unattached_inquiries = []
        self.unattached_bind_inquiries = []
        self.pending_inquiries_event = False
        self.pending_bind_inquiries_event = False
        self.worker_fifo = coro.fifo()      # For immediate consumption
        self.event_list = []                # For describing future events
        self._shutting_down = 0             # 0 - not shutting down
        # 1 - shutting down servers
        # 2 - dead
        self.cache_size = DEFAULT_CACHE_SIZE
        self.cache_ttl = DEFAULT_CACHE_TTL
        self.compatibility = DEFAULT_COMPATIBILITY
        self.inquiry_timeout = DEFAULT_INQUIRY_TIMEOUT * coro.ticks_per_sec
        self.max_conns = DEFAULT_MAX_CONNS
        self.max_time_per_conn = DEFAULT_MAX_TIME_PER_CONN
        self.max_requests_per_conn = DEFAULT_MAX_REQUESTS_PER_CONN
        self.failover_timeout = DEFAULT_FAILOVER_TIMEOUT
        self.operation_timeout = DEFAULT_READ_TIMEOUT

        # These commands are used most often, so use one insteads of
        # creating anew everytime.
        self.cmd_inquiries = ldap_cmd.CmdInquiries()
        self.cmd_bind_inquiries = ldap_cmd.CmdBindInquiries()

    def start(self):
        """ Kick off the server-group by spawning a worker. """
        if not self.sg_thread and not self._shutting_down:
            self.sg_thread = coro.spawn(self.sg_thread_bootstrap)

    def shutdown(self):
        self.worker_fifo.push(ldap_cmd.CmdShutdown())

    def add_server(self, hostname, port=None, authtype='anonymous',
                   authdata={}, transport=TRANSPORT_PLAINTEXT):
        """ Add a server to this server-group.
        The following must be updated afer the server """
        if self._shutting_down:
            return
        new_server = ldap_server(self, hostname, port, self.bind_ip, authtype,
                                 authdata, transport)
        self.servers.append(new_server)
        self.worker_fifo.push(ldap_cmd.CmdServerState(new_server))

    # Server group accessors
    def get_name(self):
        """get_name() -> name"""
        return self.name

    def get_number_of_servers(self):
        """get_number_of_servers() -> number of servers"""
        return len(self.servers)

    # Configuration updates.  All others require a new server-group.
    def set_compatibility(self, compatibility):
        assert(isinstance(compatibility, dict))
        self.worker_fifo.push(ldap_cmd.CmdSetCompat(copy.deepcopy(compatibility)))

    def set_inquiry_timeout(self, timeout):
        assert(isinstance(timeout, int))
        self.worker_fifo.push(ldap_cmd.CmdSetInqTimeout(timeout))

    def set_max_connections(self, max_connections):
        assert(isinstance(max_connections, int))
        self.worker_fifo.push(ldap_cmd.CmdSetMaxConns(max_connections))

    def set_max_requests_per_connection(self, max_requests_per_connection):
        assert(isinstance(max_requests_per_connection, int))
        self.worker_fifo.push(ldap_cmd.CmdSetMaxRequestsPerConn(max_requests_per_connection))

    def set_max_time_per_connection(self, max_time_per_connection):
        assert(isinstance(max_time_per_connection, int))
        self.worker_fifo.push(ldap_cmd.CmdSetMaxTimePerConn(max_time_per_connection))

    def set_cache_size(self, cache_size):
        self.worker_fifo.push(ldap_cmd.CmdSetCacheSize(cache_size))

    def set_cache_ttl(self, cache_ttl):
        self.worker_fifo.push(ldap_cmd.CmdSetCacheTtl(cache_ttl))

    # Server group knobs when using client as diagnostic tool
    def set_operation_timeout(self, timeout):
        """set_operation_timeout(timeout)
        Change the LDAP operation timeout to <timeout> seconds.  This is
        used to limit the amount of time an operation is allowed to
        resolve against individual servers."""
        self.worker_fifo.push(ldap_cmd.CmdSetOperationTimeout(timeout))

    def set_failover_timeout(self, timeout):
        """set_failover_timeout()
        Change the amount of time a server can be DOWN before a failover
        event is noted."""
        self.worker_fifo.push(ldap_cmd.CmdSetFailoverTimeout(timeout))

    # Cache API
    def clear_cache(self, refresh_ip_list=False):
        """ Clear the server-group cache.  Only clear if the group is
        actually running."""
        if self.sg_thread and not self._shutting_down:
            log.write('LDAP.DEBUG',
                      'Clearing LDAP server-group "%s" cache' % self.name)
            self.pos_cache = None
            self.neg_cache = None

            # Reset the query time to expire IPs in ip list
            if refresh_ip_list:
                for srv in self.servers:
                    srv.ip_list = [(0, ip) for ttl, ip in srv.ip_list]

    def get_cache_context(self, key):
        """get_cache_context(key) -> cache context
        Retrieve the cache context if it exists.  If the context has
        been resolved, caller will pull results from it.  If the context
        references an inquiry that is still resolving, then the caller
        waits (using the context).

        The cache exists all the time, regardless of cache-size. If the
        cache-size is zero, entries are not preserved; however,
        concurrent requests are still serviced by a single LDAP
        transaction."""

        # Figure out if we already have a cache entry for this
        cache_to_use = None
        if key in self.new_cache:
            entry = self.new_cache[key]
            # If the entry is stale (pending more than inquiry_timeout) then do not
            # use this inquiry as it will fail this query immediately
            if not entry.check_ttl_expired(self):
                # new_cache is always not resolved yet, simply return it
                return (False, entry)
        # Check the positive cache
        elif self.pos_cache and key in self.pos_cache:
            cache_to_use = self.pos_cache
        # Check the negative cache
        elif self.neg_cache and key in self.neg_cache:
            cache_to_use = self.neg_cache

        if cache_to_use:
            entry = cache_to_use[key]
            if (coro.now - entry.when) < (self.cache_ttl * coro.ticks_per_sec):
                # Cache hit is still valid
                return (False, entry)

        # Create a new entry and add to to the nascent cache list
        ce = ldap_cache_entry(key)
        self.new_cache[key] = ce

        return (True, ce)

    def clear_cache_entry(self, query_string):
        """clear_cache_entry(query_string) -> Bool
        Clear caches of results for specific query_string.
        Returns whether any caches have been cleared."""
        # This interface is used by ldap_api to implement a remote_cmd
        # call.  ldap_api needs to change to pass the query_string,
        # instead of (queryname, address, group_or_envelop_sender)

        # qta - It is very inefficient that we have to do a
        # table scan to clear the cache.  Restructure the
        # cache to avoid this problem!

        def __clear_cache_entry(cache):
            cache_entry_found = False
            if cache:
                for (k, v) in cache.items():
                    if k[0] == query_string:
                        del cache[k]
                        cache_entry_found = True
                        log.write('LDAP.DEBUG', "Cache cleared: %s" % (query_string,))
            return cache_entry_found

        if __clear_cache_entry(self.pos_cache):
            return True
        if __clear_cache_entry(self.neg_cache):
            return True

        log.write('LDAP.DEBUG', "Cache not found: %s" % (query_string,))
        return False

    # query API
    def enqueue_operation(self, operation):
        """ Place the operation & context onto the server's
        "execute me" queue. """
        # Place operation/Inquiry on ops-to-execute queue
        self.unattached_inquiries.append(operation)
        # Only service inquiries if the server group is ready.
        if not self.pending_inquiries_event:
            self.pending_inquiries_event = True
            self.worker_fifo.push(self.cmd_inquiries)

    def enqueue_bind_operation(self, operation):
        """ Place the BIND operation & context onto the server's
        BIND "execute me" queue. """
        # Place operation/Inquiry on ops-to-execute queue
        self.unattached_bind_inquiries.append(operation)
        # Only service inquiries if the server group is ready.
        if not self.pending_bind_inquiries_event:
            self.pending_bind_inquiries_event = True
            self.worker_fifo.push(self.cmd_bind_inquiries)

    def search_query(self, query_string, base, look_for_attrs):  # maybe timeout &
        """search_query(query_string, base, look_for_attrs)
        XXX previously known as "query()" to ldap_api.  App doesn't care
        which of the underlying servers executes the "query" (LDAPSearch
        operation)."""
        if self._shutting_down:
            return None

        # Grab a cache/query context (may or may not be resolved)
        nascent, ctx = self.get_cache_context((query_string, base, "%s" % (look_for_attrs,)))

        if nascent and ctx.inquiry is None:
            try:
                # Get ourselves an appropriate Inquiry
                the_inc = Inquiry_Search(self, base, query_string, look_for_attrs,
                                         self.compatibility, self.inquiry_timeout)
            except ldap.QuerySyntaxError as e:
                # Abort this operation
                ctx.abort(self)
                return ((False, str(e)), None)

            ctx.set_inquiry(the_inc)
            # Enqueue this operation for future processing by the client
            self.enqueue_operation(the_inc)

        elif ctx._is_resolved():
            log.write('LDAP.DEBUG', "Query %s resolved via cache hit" % (query_string,))

        return ctx.get_data(self)

    def simple_bind_query(self, username, password):
        """simple_bind_query(username, password)
        BIND API (using 'simple' authentication)."""

        # Explicitly disallow 'unauthenticated bind'
        if username and not password.strip():
            return (
                (False, "Failed binding with user '%s' and supplied password: Invalid credentials" % username), None)

        if self._shutting_down:
            return None

        # Grab a cache/query context (may or may not be resolved)
        nascent, ctx = self.get_cache_context((username, password))

        if nascent:
            # Get ourselves an appropriate Inquiry
            the_inc = Inquiry_Simple_Bind(self, username, password,
                                          self.inquiry_timeout)
            ctx.set_inquiry(the_inc)

            # Enqueue this operation for future processing by the client
            self.enqueue_bind_operation(the_inc)

        return ctx.get_data(self)

    def is_down(self):
        """ Determine if the server-group is down: all servers in this
        server-group is is down
        """
        for srv in self.servers:
            if not srv.is_down():
                return False
        return True

    def is_ready(self):
        """ Determine if the server-group is ready to service request,
        in other words, if all servers are not marked DOWN.
        """
        for srv in self.servers:
            if srv.is_connected():
                return True
        return False

    def get_server_for_inquiry(self):
        """ Return a server that is ready to accept a new query.
            This is where failover/round-robin handling occurs.
        """
        # If only one server configured:
        if len(self.servers) == 1:
            if self.servers[0].is_connected():
                return self.servers[0]
            else:
                return None

        # Failover
        #
        # Published documentation says to stick to original if it
        # exists.  Otherwise, if we're running on a non-primary server,
        # check every few minutes to see if primary comes online. When
        # it does, use it.
        #
        if self.connection_behavior == CONNECT_BEHAVIOR_FAILOVER:

            if self.server_pos != 0 and self.servers[0].is_connected():
                return self.servers[0]
            if self.servers[self.server_pos].is_connected():
                return self.servers[self.server_pos]
            else:
                index = self.server_pos + 1
                count = len(self.servers)
                for offset in xrange(count):
                    next_index = (index + offset) % count
                    if self.servers[next_index].is_connected():
                        self.server_pos = next_index
                        return self.servers[next_index]

            # No servers are available
            return None

        # Load balance
        #
        # Load balancing behavior means to round-robin across existing
        # (working) servers.  This behavior is similar to simple DNS-based
        # round-robining (more complicated as we track which servers are
        # down).
        elif self.connection_behavior == CONNECT_BEHAVIOR_LOAD_BALANCE:

            count = len(self.servers)
            for offset in xrange(count):
                next_index = (self.server_pos + offset) % count
                if self.servers[next_index].is_connected():
                    self.server_pos = next_index + 1
                    return self.servers[next_index]

            # No available server
            return None

        else:
            # Unknown behavior
            log.write('LDAP.DEBUG', "Unknown connection behavior type: %d"
                      % (self.connection_behavior))
            return None

    def find_referral_server(self, host, port):
        """find_referral_server(host, port)"""
        # If host/port points to this server-group, we're good
        for server in self.servers:
            if server.hostname == host and \
               int(server.port) == int(port):
                return server
        # Otherwise find a different server_group to pass this off to
        return self.client.find_server(host, port)

    def inquiry_referral(self, inquiry, params, referral):
        """inquiry_referral(inquiry, params, referral)
        An inquiry is in need of referral-following."""
        # Extract host/port from referral
        lurl = ldapurl.LDAPUrl(referral)
        host, port = LDAPUrl_to_host_port(lurl)

        # If host/port points to this server-group, we're good
        referral_server = self.find_referral_server(host, port)
        if referral_server:

            # Update inquiry with new parameters
            inquiry.update_from_referral(params, lurl)

            if isinstance(inquiry, Inquiry_Simple_Bind):
                referral_server.resolve_bind_inquiry(inquiry)
            else:
                referral_server.resolve_inquiry(inquiry)
            return True

        log.write('LDAP.DEBUG', "Could not find a server to follow referral: %s" % (referral,))

        return False

    def inquiry_continuation(self, inquiry, params, continuation):
        """inquiry_continuation(inquiry, params, continuation)
        An inquiry is in need of continuation-following.

        For now this is pretty much identical to inquiry_referral(), but
        in the future continuation handling will involve parsing and
        dealing with all sorts of extras like filter modifications and
        base changes."""
        # Extract host/port from continuation
        lurl = ldapurl.LDAPUrl(continuation)
        host, port = LDAPUrl_to_host_port(lurl)

        # If host/port points to this server-group, we're good
        continuation_server = self.find_referral_server(host, port)
        if continuation_server:

            # Update inquiry with new parameters
            # See RFC 4511 section 4.5.3
            # For now, only Search cares about referrals and
            # continuations, and for now the modifications are the
            # same.
            inquiry.update_from_referral(params, lurl)

            continuation_server.resolve_inquiry(inquiry)
            return True

        log.write('LDAP.DEBUG', "Could not find a server to follow continuation: %s" % (continuation,))

        return False

    def sg_thread_bootstrap(self):
        """ the work-thread """
        while True:
            try:
                self.sg_thread_worker()
            except coro.Interrupted:
                raise
            except ldap_cmd.ServerGroupShutdown:
                # Shutdown raised up by the worker thread
                assert(self._shutting_down == 2)
                break
            except:
                log.write('COMMON.APP_FAILURE', tb.traceback_string())
                coro.sleep_relative(10)
            else:
                # If worker returns with no exception, that means we're
                # shut down, but let's do an assert to make sure.
                assert(self._shutting_down == 2)
                break

    def _add_event(self, server, wait_time, event):
        for (t, e) in self.event_list:
            if e == event:
                return
        if wait_time is None:
            wait_time = coro.now + (server.normalized_delay_time() * coro.ticks_per_sec)
        else:
            wait_time = coro.now + (wait_time * coro.ticks_per_sec)
        self.event_list.append((wait_time, event))

    def _add_bind_event(self, server, wait_time=None):
        for conn in server.bind_connections.values():
            if conn['conn_obj'].is_connected():
                return
        self._add_event(server, wait_time, ldap_cmd.CmdBindConn(server, True))

    def _get_due_events(self):
        time_to_sleep = DEFAULT_READ_TIMEOUT
        due_events = []

        if self.event_list:
            time_now = coro.now
            ticks_per_sec = coro.ticks_per_sec
            events = []
            for entry in self.event_list:
                event_time, event = entry
                if time_now >= event_time:
                    due_events.append(event)
                else:
                    time_to_sleep = min(time_to_sleep,
                                        int(math.ceil(float(event_time - time_now) / ticks_per_sec)))
                    events.append(entry)
            self.event_list = events

        if due_events:
            # if there are event to process, we will not wait around for the fifo queue
            return (0, due_events)
        else:
            return (time_to_sleep, [])

    def check_auth_failure(self):
        """Check if all servers in this server group has failed to connect
        due to authentication error

        :Return:
            - True if all server is down due to auth failure, False otherwise.
                   if there is no server in the server group, return False
                   (i.e., there is no auth failure)
        """
        for srv in self.servers:
            if not srv.is_auth_failure():
                return False
                break
        return (len(self.servers) > 0)

    def _inquiry_timeout_event(self, wake_time):
        self.event_list.append((wake_time, ldap_cmd.CmdInquiryTimeout()))

    def _inquiry_timeout_request(self):
        self.worker_fifo.push(ldap_cmd.CmdInquiryTimeout())

    def sg_thread_worker(self):
        self.worker_fifo.push(ldap_cmd.CmdBootstrap())   # Bootstrap

        def list_iter(*ell):
            for el in ell:
                for e in el:
                    yield e

        while True:
            requests = []
            due_events = []

            # pop_all() will wait() until there is something to do
            try:
                time_to_sleep, due_events = self._get_due_events()
                requests = coro.with_timeout(time_to_sleep, self.worker_fifo.pop_all)
            except coro.TimeoutError:
                # If we got timeout, go check inquiries and bind_inquiries, there
                # might be left over from previous run.
                if self.unattached_bind_inquiries:
                    requests.append(self.cmd_bind_inquiries)
                if self.unattached_inquiries:
                    requests.append(self.cmd_inquiries)

            # Service any requests
            for req in list_iter(due_events, requests):
                req.run(self)

######################################################################
# SERVERS
#
# The server class is the glue between the server-group and individual
# connections.  This class is basically two parts:
#
#   - Top half - manipulated by the server-group's worker thread.
#   - Bottom half - manipulated by the server's connections.
#
# This class does not maintain any execution contexts itself; it simply
# keeps the mechanics of the tranports layer separate from the logic of
# inquiry resolution.
#
# The top half interfaces with the server-group by placing operands on
# the server-group's work-FIFO.  The server-group's worker then services
# the operand during it's next work loop.
#
# The bottom half consists of creating and managing connections. As
# connections come and go, connections use callbacks to inform the
# server of changes.
######################################################################
class ldap_server:
    """ldap_server -- the glue between the server-group and individual
    connections.  This abstraction is basically two parts.  The top half
    is manipulated by the server-group's worker thread.  The bottom half
    is manipulated by the server's connections.  The ldap_server doesn't
    actually do anything but act as a state for the upper and lower
    execution contexts.
    """

    SRV_STATE_NEW = 0
    SRV_STATE_CONNECTING = 1
    SRV_STATE_CONNECTED = 2
    SRV_STATE_DOWN = 3

    reconnect_delay = 30
    recentness_threshold = 120

    def __init__(self, sg_context, hostname, port, bind_ip, authtype,
                 authdata, transport):
        self.sg_context = sg_context
        self.hostname = hostname
        self.port = port
        self.bind_ip = bind_ip
        self.authtype = authtype
        self.authdata = authdata
        self.transport = transport

        self.max_conns = sg_context.max_conns
        self.max_conn_time = sg_context.max_time_per_conn
        self.max_conn_requests = sg_context.max_requests_per_conn
        self.ldap_op_timeout = sg_context.operation_timeout
        self.failover_if_err_in_last = sg_context.failover_timeout

        self.connections = {}
        self.bind_connections = {}
        self.next_connection_id = 1
        self.next_conn_die_time = 0
        self.most_recent_cid = 0   # Used to round-robin connections
        # when dispatching inquiries
        self.ip_list = []
        self.ip_pos = 0

        self.state = self.SRV_STATE_NEW
        self.shutdown_flag = False
        self.auth_failure = False

        # Start with the assumption that this server has successfully
        # connected.  This acts as the starting point from which the
        # "how long until this server gets marked as down" calculation
        # can be made.
        self.last_conn_read_time = coro.now
        self.last_conn_success_time = coro.now
        self.last_conn_err = None
        self.last_conn_err_time = None
        self.last_spawned_connection_time = None
        self.last_spawned_bind_time = None

        self.inquiries_to_send = []
        self.binds_to_send = []

        # Tracking if a connection spawner is active
        self.connection_spawner_thread = None

    ##################################################################
    # TOP HALF
    ##################################################################
    def resolve_inquiry(self, inquiry):
        """resolve_inquiry(inquiry) -> Bool
        Give this inquiry to the server to resolve.  If no connections
        are CONNECTED, inquiry is placed onto self.inquiries_to_send."""

        # If the inquiry has previously timed out, let it be taken off
        # the inquiry list.  If rendered_request is None, this inquiry
        # has been timed out, we won't try it again until it is retired
        # from the cache

        if inquiry and inquiry.rendered_request:
            resolving_conn_obj = self.get_conn_obj_for_inquiry()
            if resolving_conn_obj:
                resolving_conn_obj.send_inquiry(inquiry)
            else:
                self.inquiries_to_send.append(inquiry)

    def resolve_bind_inquiry(self, inquiry):
        """resolve_bind_inquiry(inquiry) -> Bool
        Give this inquiry to the server to resolve. If no connections
        can be made, inquiry is placed on self.binds_to_send."""
        assert(self.state is not self.SRV_STATE_DOWN)
        # Find an existing connection:
        try:
            binder_conn_obj = self.get_conn_obj_for_bind()
        except dns_exceptions.DNS_Error as e:
            log.write('LDAP.ERROR', 'DNS', e)
            self.state = self.SRV_STATE_DOWN
            binder_conn_obj = None
            # Retry later
            self.sg_context._add_bind_event(self)
            # Fall through to allow inquiry to find self.binds_to_send

        if inquiry and inquiry.rendered_request:
            if binder_conn_obj is None:
                self.binds_to_send.append(inquiry)
            else:
                binder_conn_obj.send_inquiry(inquiry)

    def is_down(self):
        """is_down() -> Bool
        Determine if this server is down."""
        return self.state is self.SRV_STATE_DOWN

    def is_connected(self):
        """is_connected() -> Bool
        Determine if this server has any active connection.
        """
        if self.connections:
            return True
        else:
            return False

    def is_auth_failure(self):
        """is_auth_failure() -> Bool
        Determine if this server failed to authenticate."""
        return self.auth_failure

    def shutdown(self):
        """shutdown()
        Gracefully disconnect everything.  Setting the shutdown_flag
        will prevent new connections.
        """
        self.shutdown_flag = True

        # Kill existing connections.  Doing this causes all outstanding
        # inquiries to be finished.
        for conn in self.connections.keys():
            self.connections[conn]['conn_obj'].teardown_connection(with_error=False)

        # Kill existing bind_connections.
        for bind_conn in self.bind_connections.keys():
            self.bind_connections[bind_conn]['conn_obj'].teardown_connection(with_error=False)

        # Shutdown any queued inquiries
        while (self.inquiries_to_send):
            inq = self.inquiries_to_send.pop()
            inq.state_to_unattached()
        while (self.binds_to_send):
            inq = self.binds_to_send.pop()
            inq.state_to_unattached()

    def state_transition(self):
        """Deal with server state transitions."""
        # If NEW, we're only NEW once.  Transition to CONNECTING.
        if self.state == self.SRV_STATE_NEW:
            self.spawn_connections(bootstrap=True)
            # Move to CONNECTING once the start() thread starts
            # We're CONNECTED when all connections have finished

    def resolve_hostname_lookup(self):
        """Refresh this server's IP address list.
        Resolve self.hostname into a list of IPs: [ip, ..]."""
        if self.shutdown_flag:
            return

        # Did they give us an IP addres?
        try:
            inet_utils.atoh(self.hostname)
        except ValueError:
            # They gave us a hostname
            pass
        else:
            # They gave us an IP.  Fake it up.
            self.ip_list = [(0, self.hostname)]
            return

        # Query for a result
        dns_results = dnsqr.query(self.hostname, 'A')
        if not dns_results:
            # Allow this to propagate
            raise dns_exceptions.DNS_Hard_Error(self.hostname, 'A',
                                                (dnsrcode.ServFail,
                                                 'Empty result set'))
        # Result is a list of (ttl, value) tuples
        self.ip_list = dns_results

        # Sanity check
        if len(self.ip_list) == 0:
            raise dns_exceptions.DNS_Malformed_Qname_Error('', 'A',
                                                           (dnsrcode.ServFail,
                                                            ''))

    def get_ip(self):
        """Return an ip address to use.  Round-robin across the available
        IPs.  Track entries as they expire."""
        list_length = len(self.ip_list)
        if list_length == 0:
            return None

        # Check to see if a TTL has expired.  If any TTL has expired,
        # we'll requery.
        ttl_list = sorted([ttl for ttl, value in self.ip_list])
        if coro.now > ttl_list[0]:
            try:
                self.resolve_hostname_lookup()
            except dns_exceptions.DNS_Error as e:
                log.write('LDAP.ERROR', 'DNS', e)
                return None

            # Recalculate in case things changed
            list_length = len(self.ip_list)
            if list_length == 0:
                return None

        self.ip_pos = (self.ip_pos + 1) % list_length
        return self.ip_list[self.ip_pos][1]

    def get_port(self):
        """Return a port to use."""
        if self.port is not None:
            return self.port
        else:
            # TRANSPORT_SSL is special.  Other start off on standard port.
            if self.transport == TRANSPORT_SSL:
                return PORT_LDAPS
            else:
                return PORT_LDAP

    def calculate_next_conn_timeout(self):
        """calculate_next_conn_timeout()
        Determine when the sg-worker needs to timeout old connections."""
        max_ctime_ticks = self.max_conn_time * coro.ticks_per_sec
        key_list = self.connections.keys()
        next_time = self.next_conn_die_time
        for i in key_list:
            if next_time <= 0 or \
               ((self.connections[i]['birth'] + max_ctime_ticks) < next_time):
                next_time = self.connections[i]['birth'] + max_ctime_ticks
        if self.next_conn_die_time > next_time:
            self.next_conn_die_time = next_time
            # CmdConnTimeout is self-generating, so we only need to have one copy of it
            self.sg_context.event_list = filter((lambda t_e: not isinstance(t_e[1], ldap_cmd.CmdConnTimeout)),
                                                self.sg_context.event_list)
            self.sg_context.event_list.append((self.next_conn_die_time, ldap_cmd.CmdConnTimeout(self)))

    def new_connection(self):
        # Increment the connection ID
        conn_id = self.next_connection_id
        self.next_connection_id += 1

        # Construct connection-dictionary.  Like a light-weight class.
        conn_dict = {
            'server_context': self,
            'birth': coro.now,
            'conn_obj': None,  # can't fill in now because of circular reference
            'conn_id': conn_id,
            'bind_ip': self.bind_ip,
            'max_requests': self.max_conn_requests,
            'waiting_for_flight_inquiries': [],
            'use_ssl': self.transport == TRANSPORT_SSL,
            'authtype': self.authtype,
            'authdata': self.authdata,
            'transport': self.transport,
        }

        # Create a connection and wrap it with all the trim'ns
        conn_dict['conn_obj'] = ldap_connection(conn_dict,
                                                self.sg_context.get_name(),
                                                self.hostname,
                                                self.get_ip(),
                                                self.get_port(),
                                                self.ldap_op_timeout)

        # Check for shutdown condition
        if self.shutdown_flag:
            return

        conn_dict['conn_obj'].start()
        self.last_spawned_connection_time = coro.now

        return conn_dict

    def new_bind_connection(self):
        """new_bind_connection()
        Very similar to new_connection() above, but don't interfere
        with the machinary of maintaining connections."""
        # Increment the connection ID
        conn_id = self.next_connection_id
        self.next_connection_id += 1

        # Construct connection-dictionary.
        bind_conn_dict = {
            'server_context': self,
            'birth': coro.now,
            'conn_obj': None,  # can't fill in now because of circular reference
            'conn_id': conn_id,
            'bind_ip': self.bind_ip,
            'max_requests': self.max_conn_requests,
            'waiting_for_flight_inquiries': [],
            'use_ssl': self.transport == TRANSPORT_SSL,
            'transport': self.transport,
            'bind_inquiry': None,   # XXX fill this in later
        }

        # Create a connection and wrap it with all the trim'ns
        bind_conn_dict['conn_obj'] = ldap_binder_connection(bind_conn_dict,
                                                            self.sg_context.get_name(),
                                                            self.hostname,
                                                            self.get_ip(),
                                                            self.get_port(),
                                                            self.ldap_op_timeout)

        # Check for shutdown condition
        if self.shutdown_flag:
            return None

        bind_conn_dict['conn_obj'].start()

        self.last_spawned_bind_time = coro.now

        return bind_conn_dict

    def spawn_connections(self, bootstrap=False):
        """spawn_connections()
        Spawn a thread to do the work of creating connections.  Thread is
        spawned to allow DNS resolution to block.  Pass "bootstrap" to
        indicate if this is a first-time through to forces initial DNS
        lookup."""
        if not self.connection_spawner_thread:
            self.connection_spawner_thread = \
                coro.spawn(self.connection_spawner, bootstrap)

    def connection_spawner(self, bootstrap):
        """connection_spawner()
        Encapsulate the kicking off of new connections in a thread to
        allow DNS resolution to block."""
        try:
            if self.state == self.SRV_STATE_NEW:
                self.state = self.SRV_STATE_CONNECTING

            wait_time = 1
            while not self.shutdown_flag and \
                    (len(self.connections) < self.max_conns):

                if bootstrap or not self.ip_list:
                    try:
                        self.resolve_hostname_lookup()
                        if self.ip_list:
                            bootstrap = False
                    except dns_exceptions.DNS_Soft_Error as e:
                        log.write('LDAP.ERROR', 'DNS', e)
                        coro.sleep_relative(wait_time)
                        continue
                    except dns_exceptions.DNS_Error as e:
                        log.write('LDAP.ERROR', 'DNS', e)
                        self.state = self.SRV_STATE_DOWN
                        coro.sleep_relative(self.reconnect_delay)
                        continue

                # Create a connection
                conn_dict = self.new_connection()
                if conn_dict is None:   # server shutdown
                    break

                # Wait around until this connection is completed before
                # spawn the next one to avoid spawning too many failed
                # connection attempts.  If the connect attempt fails, we
                # increase the wait time upto 30 sec (the current default)
                # and reset the wait time if connect is successful.
                conn = conn_dict['conn_obj']
                while not (self.shutdown_flag or conn.is_connected()):

                    # If authentication fails, then delay retry the whole
                    # default reconnect delay
                    if self.auth_failure:
                        wait_time = self.reconnect_delay
                        break

                    if conn.is_dead():
                        if wait_time < self.reconnect_delay:
                            wait_time += 1
                        break
                    coro.sleep_relative(0.2)

                if conn.is_connected():
                    wait_time = 1
                else:
                    coro.sleep_relative(wait_time)

        finally:
            self.connection_spawner_thread = None

    def normalized_delay_time(self):
        """normalized_delay_time()
        Normalize the delay-before-reconnect-time.  Either use the
        default reconnect-delay-time, or 1/2 of the failover time,
        whichever is less."""
        half_failover = int(math.ceil(self.failover_if_err_in_last / 2))
        return min(self.reconnect_delay, half_failover)

    def wait_time_until_spawn(self, last_spawn_time):
        """wait_time_until_spawn(last_spawn_time) -> time
        Returns if this server should insert a delay before spawning the
        next connection."""
        # If we've never received a transport-layer error, don't wait
        if self.last_conn_err_time is None:
            return None
        delay_time = self.normalized_delay_time()
        ticks_since_last_conn_err = coro.now - self.last_conn_err_time
        if ticks_since_last_conn_err > (self.recentness_threshold
                                        * coro.ticks_per_sec):
            return None

        if last_spawn_time is None:
            return None
        next_can_spawn_connection = last_spawn_time \
            + (delay_time * coro.ticks_per_sec)
        if coro.now >= next_can_spawn_connection:
            return None
        else:
            # Avoid feeding coro.with_timeout() an int(zero) timeout value.
            return int(math.ceil(float(next_can_spawn_connection - coro.now)
                                 / float(coro.ticks_per_sec)))

    def update_connections(self):
        """Called by connection event handler in response to connection event
        generated by sg-worker to update this server's connection pool.  It
        cleans up any dead connection, and create addition connection if the
        number of active connection is less than the pool size.
        """
        # Reap dead connections.  If they contain any inquiries, pluck 'em.
        delete_list = []
        for conn_id in self.connections:
            if self.connections[conn_id]['conn_obj'].is_dead():
                self.connections[conn_id]['conn_obj'] = None
                delete_list.append(conn_id)
        if delete_list:
            self.state = self.SRV_STATE_CONNECTING
            for del_item in delete_list:
                del self.connections[del_item]

        # If we're not fully connected, figure out if we should be
        # spawning new connections.
        if not self.shutdown_flag and self.state != self.SRV_STATE_CONNECTED:
            self.spawn_connections()

    def update_bind_connections(self):
        """update_bind_connections()
        Called by sg-worker to update this server's bind connections."""
        # Reap dead connections.  If they contain any inquiries, pluck 'em.
        delete_list = []
        for conn_id in self.bind_connections:
            if self.bind_connections[conn_id]['conn_obj'].is_dead():
                self.bind_connections[conn_id]['conn_obj'] = None
                delete_list.append(conn_id)
        if delete_list:
            self.state = self.SRV_STATE_CONNECTING
            for del_item in delete_list:
                del self.bind_connections[del_item]

        # Are new connections in need of spawning?
        if self.binds_to_send:
            # Do we wait until later?
            wait_time = self.wait_time_until_spawn(self.last_spawned_bind_time)
            if wait_time is not None:
                log.write('LDAP.DEBUG', 'Waiting period until next '
                          'bind connection attempt is %d seconds' % wait_time)
                # Convert from "wait X secs" to absolute time
                wake_time = (wait_time * coro.ticks_per_sec) + coro.now

                # We only need 1 outstanding event
                self.sg_context._add_bind_event(self, wake_time)
            else:
                local_bind_list = self.binds_to_send
                self.binds_to_send = []
                while(local_bind_list):
                    self.resolve_bind_inquiry(local_bind_list.pop(0))

    def timeout_old_connections(self, now_time):
        """timeout_old_connections()
        Called by sg-worker to kill off too-old connections."""
        # Check connections
        stopped_something = False
        for conn_id in self.connections.keys():
            if (self.connections[conn_id]['birth'] +
                    (self.max_conn_time * coro.ticks_per_sec) < now_time):
                self.connections[conn_id]['conn_obj'].teardown_connection(with_error=False)
                stopped_something = True
        if stopped_something:
            self.sg_context.worker_fifo.push(ldap_cmd.CmdConn(self))

        # Check BIND connections
        stopped_something = False
        for conn_id in self.bind_connections.keys():
            if (self.bind_connections[conn_id]['birth'] +
                    (self.max_conn_time * coro.ticks_per_sec) < now_time):
                self.bind_connections[conn_id]['conn_obj'].teardown_connection(with_error=False)
                stopped_something = True
        if stopped_something:
            self.sg_context.worker_fifo.push(ldap_cmd.CmdBindConn(self))

    def update_max_connections(self, max_connections):
        """update_max_connections()"""
        old_max = self.max_conns
        self.max_conns = max_connections

        if max_connections < old_max:

            # Close the delta via graceful-disconnection
            num_to_close = old_max - max_connections
            key_list = self.connections.keys()
            for i in key_list:
                # Have we killed enough?
                if not num_to_close:
                    break
                num_to_close -= 1
                # Kill!
                self.connections[i]['conn_obj'].teardown_connection(with_error=False)

        elif max_connections > old_max:
            # Only spawn more if we're doing that sort of thing
            if self.state == self.SRV_STATE_CONNECTING or \
               self.state == self.SRV_STATE_CONNECTED:
                self.spawn_connections()

    def update_max_time_per_connection(self, mtpc):
        """update_max_time_per_connection()
        :Parameters:
            - 'mtpc' : The maximum time allowed for each connection
        Determine if the new max connection time will cause some connections
        to expire, if so kill and restart them anew, other wise update the
        conn timeout event"""
        # Safety measure - bogus value could send LDAP spinning
        if mtpc <= 60:
            mtpc = DEFAULT_MAX_TIME_PER_CONN
        old_time = self.max_conn_time
        self.max_conn_time = mtpc
        if mtpc < old_time:
            inform_new_connections = False
            mtpc_ticks = mtpc * coro.ticks_per_sec
            key_list = self.connections.keys()
            for i in key_list:
                if self.connections[i]['birth'] + mtpc_ticks <= coro.now:
                    self.connections[i]['conn_obj'].teardown_connection(with_error=False)
                    inform_new_connections = True
            if inform_new_connections:
                self.spawn_connections()
            else:
                self.calculate_next_conn_timeout()

    def update_max_requests_per_connection(self, mrpc):
        """update_max_requests_per_connection()
        Go through connections to determine if any should be stopped."""
        old_reqs = self.max_conn_requests
        self.max_conn_requests = mrpc

        # Update all existing connection's 'max_requests' item.  While
        # walking the list, discontinue any connections that are over
        # the new maximum.
        key_list = self.connections.keys()
        inform_new_connections = False
        for i in key_list:
            self.connections[i]['max_requests'] = mrpc
            if mrpc < old_reqs:
                if self.connections[i]['conn_obj'].request_count() > mrpc:
                    self.connections[i]['conn_obj'].teardown_connection(with_error=False)
                    inform_new_connections = True
        if inform_new_connections:
            self.spawn_connections()

    def update_operation_timeout(self, timeout):
        """update_operation_timeout(timeout)
        Update the operation timeout.  Timeout is essentially the read
        timeout allowed for an LDAP Operation to resolve."""
        self.ldap_op_timeout = timeout

    def update_failover_timeout(self, timeout):
        """update_failover_timeout(timeout)
        Update the failover timeout."""
        self.failover_if_err_in_last = timeout

    def get_conn_obj_for_inquiry(self):
        """get_conn_obj_for_inquiry() -> connection
        Discover a connection to transport an inquiry.  Attempt to
        round-robin across connections, skipping non-connected
        connections.

        Return None if no fully-connected connections are available."""

        next_cid = self.most_recent_cid + 1
        conn_count = len(self.connections)

        for count in xrange(conn_count):
            next_cid = (next_cid + count) % conn_count
            conn_obj = self.connections.values()[next_cid]['conn_obj']
            if conn_obj and conn_obj.is_connected() and \
                    conn_obj.request_count() < self.max_conn_requests:
                self.most_recent_cid = next_cid
                return conn_obj

        return None

    def get_conn_obj_for_bind(self):
        """get_conn_obj_for_bind() -> connection or None
        Discover a connection to complete a BIND.  Use an existing
        connection if possible, otherwise create a new connection up
        until the max-connections limit is hit."""
        conn_obj = None

        # Can we use an existing connection?
        cid_list = self.bind_connections.keys()
        list_len = len(cid_list)
        for i in xrange(list_len):
            conn_obj = self.bind_connections[cid_list[i]]['conn_obj']
            if conn_obj and conn_obj.is_connected():
                if not conn_obj.inquiry_count():
                    # Connected with Zero requests, use this
                    return conn_obj

        # If no existing connection, can a new one be created?
        if len(self.bind_connections) < self.max_conns:
            new_conn = self.new_bind_connection()
            if new_conn:
                self.bind_connections[new_conn['conn_id']] = new_conn
                return new_conn['conn_obj']
            else:
                self.sg_context._add_bind_event(self)

        # Still no connection?  Return None
        return None

    def give_back_inquiries(self):
        """give_back_inquiries()
        Give any queued inquiries back to the server-group."""
        if self.inquiries_to_send:
            self.sg_context.worker_fifo.push(ldap_cmd.CmdInquiryList(self.inquiries_to_send))
            self.inquiries_to_send = []
        if self.binds_to_send:
            self.sg_context.worker_fifo.push(ldap_cmd.CmdBindInquiryList(self.binds_to_send))
            self.binds_to_send = []

    def build_log(self, msg):
        """build_log(msg)
        Dress up an error message with server info."""
        return '%s:%s(%s:%d) %s' % \
            (self.sg_context.get_name(), self.hostname,
             self.get_ip(), self.get_port(), msg)

    ##################################################################
    # BOTTOM HALF
    ##################################################################

    def note_connection_read(self):
        """note_connection_read()
        Note that a connection has successful read.  This updates this
        amount of time that must pass before a server can be marked as
        down."""
        self.last_conn_read_time = coro.now

    def _set_srv_state(self, with_error, auth_error):
        # A dead connection means we're no longer fully connected
        if self.state == self.SRV_STATE_CONNECTED:
            self.state = self.SRV_STATE_CONNECTING

        if auth_error:
            self.auth_failure = True
            self.state = self.SRV_STATE_DOWN

        # Track if this is due to a transport error
        if with_error:
            self.last_conn_err_time = coro.now

            if self.state != self.SRV_STATE_DOWN:

                # This server is down if we haven't successfully
                # connected in at least the past 3 minutes.  Hueristic
                # loosely imported from old code.
                last_traffic_time = max(self.last_conn_success_time,
                                        self.last_conn_read_time)

                if (self.last_conn_err_time >= (last_traffic_time +
                                                (self.failover_if_err_in_last *
                                                 coro.ticks_per_sec))):
                    # Yes, it's been at least 3 minutes
                    log.write('LDAP.DEBUG',
                              self.build_log('this server marked DOWN'))
                    self.state = self.SRV_STATE_DOWN

    def dead_connection(self, conn, with_error=False, auth_error=False):
        """dead_connection()
        Dead connection callback."""
        self._set_srv_state(with_error, auth_error)

        # Return our inquiries back to server-group
        self.give_back_inquiries()

        self.sg_context.worker_fifo.push(ldap_cmd.CmdShutdownConn(self, conn))

    def dead_bind_connection(self, conn, with_error=False):
        """dead_bind_connection()
        Dead BIND connection callback."""
        self._set_srv_state(with_error, False)

        # Return our inquiries back to server-group
        self.give_back_inquiries()

        self.sg_context.worker_fifo.push(ldap_cmd.CmdShutdownBindConn(self, conn))

    def server_responsive(self):
        """server_responsive(conn_id)
        Connection has negotiated transport-layer successfully.  If
        server is DOWN, it should move to CONNECTING."""
        if self.state == self.SRV_STATE_DOWN:
            self.state = self.SRV_STATE_CONNECTING

    def completed_connection(self, conn_id, conn):
        """completed_connection()
        Live connection callback."""
        self.last_conn_success_time = coro.now

        # Add self to connection list
        self.connections[conn_id] = conn.cookie

        # Update the ConnTimeout event
        self.calculate_next_conn_timeout()

        # If server is down, it's now connecting
        if self.state == self.SRV_STATE_DOWN:
            self.state = self.SRV_STATE_CONNECTING

        # If server is connecting, it might now be fully connected
        if self.state == self.SRV_STATE_CONNECTING and \
           self.max_conns == len(self.connections):
            # Count how many connections have connected
            total_connected = 0
            for conn_id in self.connections:
                if self.connections[conn_id]['conn_obj'].is_connected():
                    total_connected += 1
            if total_connected == self.max_conns:
                self.state = self.SRV_STATE_CONNECTED

        # Update auth state
        self.auth_failure = False

        # Inform the server-group
        self.sg_context.worker_fifo.push(ldap_cmd.CmdServerConnected(self))

    def connection_inquiry_give_back(self, inquiry_list):
        """connection_inquiry_give_back(inquiry_list)
        Connection callback to give back a list of inquiries that could
        not be completed."""
        self.sg_context.worker_fifo.push(ldap_cmd.CmdInquiryList(inquiry_list))

    def connection_bind_inquiry_give_back(self, inquiry_list):
        """connection_bind_inquiry_give_back(inquiry_list)
        Connection callback to give back a list of BIND inquiries that
        could not be completed."""
        if self.shutdown_flag:
            for inqr in inquiry_list:
                inqr.state_to_unattached()
            return
        self.binds_to_send.extend(inquiry_list)

setup_connection_timeout = 60

######################################################################
# CONNECTIONS
#
# The connection class wraps sockets with reader and writer threads. In
# order to become connected, this class implements LDAP-specific
# connectivity logic such as authentication and SSL negotiation.
#
# Other LDAPism are maintained, such as tracking per-connection message
# identifiers.
######################################################################
class ldap_connection:

    # State descriptions
    # NEW - Connection has been newly created.
    # CONNECTING - A thread has been spawned off to take care of all things
    #              connection-related up until the point where LDAP operations
    #              can be executed.
    # CONNECTED - Stable connection w/ 2 service threads - reader and writer.
    # DEAD - Connection is in need of clean up.

    CONN_NEW = 0
    CONN_CONNECTING = 1
    CONN_AUTHENTICATING = 2
    CONN_CONNECTED = 3
    CONN_DEAD = 4

    def __init__(self, cookie, sg_name, hostname, ip, port, read_timeout):
        self.sg_name = sg_name
        self.hostname = hostname
        self.ip = ip
        self.port = port
        self.cookie = cookie
        self.read_timeout = read_timeout
        self.state = self.CONN_NEW
        self.inflight_inquiries = {}
        self.out_fifo = coro.fifo()
        self.next_ldap_msg_id = 1
        self.buffer = ''
        self.last_err = ''
        self.completed_requests = 0
        self.last_write = 0
        self.auth_failed = False
        self.s = None

        self.connect_thread = None
        self.reader_thread = None
        self.writer_thread = None

        self.shutdown_flag = False
        self.connection_name = "(%s:%s)" % (self.hostname, self.port)

    def start(self):
        """start()
        Kick off this connection.  A "setup_connection_thread" thread is
        spawned to allow the calling thread to continue on. The spawned
        thread wraps the connection-operation with a time-out wrapper.
        """
        self.connect_thread = coro.spawn(self.setup_connection_thread)

    def _get_drain_list(self):
        """_get_drain_list()
        Generate a list of to-be-drained-inquiries."""
        inquiry_list = []

        # Drain any inquiries found in in-flight bucket
        if self.inflight_inquiries:
            for inflight in self.inflight_inquiries.keys():
                inflight_inqr = self.inflight_inquiries.pop(inflight)
                inflight_inqr.state_to_unattached()
                inquiry_list.append(inflight_inqr)
            self.inflight_inquiries = {}

        # Drain any inquiries found in out_fifo
        if len(self.out_fifo):
            op_list = self.out_fifo.pop_all()
            for mid, inqr in op_list:
                inqr.state_to_unattached()
                inquiry_list.append(inqr)

        return inquiry_list

    def drain_inquiries(self):
        """drain_inquiries()
        Return inquiries back to server."""
        drain_list = self._get_drain_list()
        if drain_list:
            sc = self.cookie['server_context']
            sc.connection_inquiry_give_back(drain_list)

    def is_connected(self):
        """is_connected() -> Bool"""
        return self.state == self.CONN_CONNECTED

    def is_dead(self):
        """is_dead() -> Bool"""
        return self.state == self.CONN_DEAD

    def request_count(self):
        """request_count() -> number of completed, outstanding, and
        inflight requests.
        NOTE: authenticate operations are not counted.

        Server calls this to determine if this connection can take
        any more requests."""
        return self.completed_requests + \
            len(self.out_fifo) + \
            len(self.inflight_inquiries)

    def setup_connection_thread(self):
        """Method to be called as thread to construct/connect socket.
        Doesn't do much except wrap everything in timeout code."""
        if self.shutdown_flag:
            return
        # log.write('LDAP.DEBUG', self.build_last_err('creating a new connection'))
        try:
            coro.with_timeout(setup_connection_timeout, self.setup_connection)

        except coro.TimeoutError as e:
            # Log this timeout
            self.last_err = self.build_last_err(
                'Timeout attempting to connect: %s' % e)
            log.write('LDAP.DEBUG', self.last_err)

            # Mark this connection as dead
            self.teardown_connection()

        except coro.Interrupted:
            raise

        except:
            # Mark this connection as dead after logging important bits
            exc_info = sys.exc_info()
            self.last_err = tb.traceback_string(*exc_info)
            log.write('COMMON.APP_FAILURE', self.last_err)
            self.teardown_connection()

    def setup_connection(self):
        """setup_connection(); connect to a socket.  Once a socket has
        been connected, reader and writer threads are spawned to handle
        LDAP operations."""
        log.write('LDAP.DEBUG', self.build_last_err("connecting to server"))
        try:
            self.state = self.CONN_CONNECTING
            if self.cookie['use_ssl']:
                sock = coro_ssl.ssl_sock(ldap_api.ssl_ctx)
                sock.create()
            else:
                sock = coro.tcp_sock()

            if self.cookie['bind_ip'] is not None:
                sock.bind((self.cookie['bind_ip'], 0))

            sock.connect((self.ip, self.port))
            if self.cookie['use_ssl']:
                sock.ssl_connect()

            self.s = sock

        except sslip.Error as e:
            self.last_err = self.build_last_err('SSL Error: %s' % e)
            log.write('LDAP.DEBUG', self.last_err)
            self.teardown_connection()

        except OSError as e:
            self.last_err = self.build_last_err('Connection Error: %s' % e)
            log.write('LDAP.DEBUG', self.last_err)
            self.teardown_connection()

        else:
            # Server is responsive
            self.cookie['server_context'].server_responsive()

            # Deal with StartTLS
            if not self.start_starttls():
                self.teardown_connection()
                return

            # Deal with authentication
            if not self.authenticate_connection():
                self.teardown_connection()
                return

            # If we get this far, we should already have a servicable
            # connection, set the state as connected and start the
            # reader and writer threads
            self.state = self.CONN_CONNECTED

            # Spawn readers and writers
            self.writer_thread = coro.spawn(self.writer)
            self.reader_thread = coro.spawn(self.reader)

            log.write('LDAP.DEBUG', self.build_last_err('connected to server'))

            # Tell the server we're connected
            sc = self.cookie['server_context']
            sc.completed_connection(self.cookie['conn_id'], self)

    def upgrade_connection_to_ssl(self):
        """upgrade_connection_to_ssl()
        Upgrade a connection's existing non-SSL socket with an SSL wrapper.
        This must occur before the connection's reader and writer threads
        have been spawned.
        """
        sock = coro_ssl.ssl_sock(ldap_api.ssl_ctx)
        sock.create(sock=self.s)
        sock.ssl_connect()
        self.s = sock

    def start_starttls(self):
        """start_starttls()
        Deal with transport type of TRANSPORT_STARTTLS."""
        if self.state == self.CONN_CONNECTING or \
           self.state == self.CONN_CONNECTED:

            if self.cookie['transport'] == TRANSPORT_STARTTLS:

                # Create LDAP StartTLS operation
                starttls_inquiry = Inquiry_StartTLS(None, DEFAULT_INQUIRY_TIMEOUT * coro.ticks_per_sec)

                # Send the StartTLS operation
                response = self.send_inquiry_and_wait(starttls_inquiry)

                # Decode response, if any.  A "None" response means the
                # connection has failed.  self.last_err contains the error.
                if response:
                    # Process inquiry and result to yield a (code, value) tuple
                    success, result = starttls_inquiry.process_response(response)
                    if success:
                        # If successful, "upgrade" the underlying socket into an
                        # SSL socket.
                        try:
                            self.upgrade_connection_to_ssl()

                        except sslip.Error as e:
                            self.last_err = self.build_last_err('SSL Error: %s' % e)
                            log.write('LDAP.DEBUG', self.last_err)
                            return False

                        except OSError as e:
                            self.last_err = self.build_last_err('Connection Error: %s' % e)
                            log.write('LDAP.DEBUG', self.last_err)
                            return False

                        except EOFError:
                            self.last_err = self.build_last_err("Connection closed (EOF)")
                            log.write('LDAP.DEBUG', self.last_err)
                            return False

                    else:
                        self.last_err = self.build_last_err(result)
                        return False
                else:
                    # Failed to StartTLS
                    log.write('LDAP.DEBUG', self.last_err)
                    return False
        return True

    def authenticate_connection(self):
        """authenticate_connection()
        Authenticate a connection via 'anonymous' or 'password'."""
        if self.state != self.CONN_CONNECTING and \
                self.state != self.CONN_CONNECTED:
            return False

        # Mark as authenticating
        self.state = self.CONN_AUTHENTICATING
        if self.cookie['authtype'] == 'anonymous':
            # No auth needed
            pass
        elif self.cookie['authtype'] == 'password':
            auth_inquiry = Inquiry_Simple_Bind(None,
                                               self.cookie['authdata']['user'],
                                               self.cookie['authdata']['password'],
                                               DEFAULT_INQUIRY_TIMEOUT * coro.ticks_per_sec)

            response = self.send_inquiry_and_wait(auth_inquiry)

            # If 'response' is None, the connection has gone away.
            if response is None:
                log.write('LDAP.DEBUG', self.last_err)
                return False
            else:
                success, result = auth_inquiry.process_response(response)
                if not success or (success is True and result is False):
                    if not success:
                        self.last_err = self.build_last_err(result)
                    else:
                        self.last_err = self.build_last_err('auth failed')
                        self.auth_failed = True
                    log.write('LDAP.DEBUG', self.last_err)
                    return False
        # --> support SASL here <---
        else:
            self.last_err = self.build_last_err('unknown auth type %r' %
                                                (self.cookie['authtype'],))
            return False

        return True

    def send_inquiry(self, inquiry):
        """send_inquiry()
        Send an inquiry over this connection."""
        # Get a message ID for this inquiry
        new_msgid = self.next_ldap_msgid()

        # Place data on "send me" queue
        self.out_fifo.push((new_msgid, inquiry))
        inquiry.state_to_attached()

    def send_inquiry_and_wait(self, inquiry):
        """send_inquiry_and_wait(inquiry)
        Send out an inquiry and wait for a result.  This should only be
        called before the reader and writer threads are spawned.  That
        is, before the connection reaches "CONNECTED" state.

        Returns a result or None if the connection has gone or needs to
        go away.
        """

        # Get a message ID for this inquiry
        new_msgid = self.next_ldap_msgid()

        rendered_request = inquiry.state_to_attached()

        packet_to_send = self._render_packet(new_msgid, rendered_request)

        try:
            # Send packet
            self.s.send(packet_to_send)

            # Wait for a response
            try:
                message_id, response = self._recv_packet()
            except coro.TimeoutError:
                self.last_err = self.build_last_err("read timeout")
                return None

            if message_id != new_msgid:
                self.last_err = self.build_last_err(
                    'Received unexpected LDAP msg ID: %s, buffer: %s' %
                    (message_id, self.buffer))
                return None

            # Return to caller.  Caller must process the response.
            return response

        except OSError as e:
            self.last_err = self.build_last_err("Connection Error: %s" % e)
            return None
        except coro.ClosedError:
            self.last_err = self.build_last_err("Connection closed")
            return None
        except sslip.Error as e:
            self.last_err = self.build_last_err("SSL Error: %s" % e)
            return None
        except EOFError:
            self.last_err = self.build_last_err("Connection closed (EOF)")
            return None
        except coro.Interrupted:
            raise
        except:
            exc_info = sys.exc_info()
            self.last_err = self.build_last_err(tb.traceback_string(*exc_info))
            log.write('COMMON.APP_FAILURE', self.last_err)

            # Raise this generic error
            raise

    def has_read_timeout(self):
        """has_read_timeout()
        Determine if connection has waited self.read_timeout time for an
        inquiry to be processed."""
        if self.last_write and (coro.now >
                                (self.last_write + (self.read_timeout * coro.ticks_per_sec))):
            return True
        return False

    def reader(self):
        """reader() - thread/method that reads from network"""
        try:
            while self.state == self.CONN_CONNECTED:
                try:
                    # Receive a packet
                    message_id, response = self._recv_packet()

                    # _recv_packet() returns (None, None) if conn dies
                    if message_id is None:
                        # self.last_err already populated
                        log.write('LDAP.DEBUG', self.last_err)
                        break

                    # Lookup in-flight operation
                    try:
                        inquiry = self.inflight_inquiries[message_id]
                    except KeyError:
                        self.last_err = self.build_last_err('unexpected msg id: %s' % message_id)
                        log.write('LDAP.DEBUG', self.last_err)
                        break

                    # A successful read means this server is not dead
                    sc = self.cookie['server_context']
                    sc.note_connection_read()

                    # Process this response.  If the operation is still
                    # outstanding (eg, an on-going search),
                    # process_response returns (success==None,
                    # result=='continue').
                    success, result = inquiry.process_response(response)
                    if success is None and result == 'continue':
                        continue

                    # No longer in flight
                    del self.inflight_inquiries[message_id]

                    inquiry.state_to_done(success, result, self.connection_name)

                    # Update self.last_write if nothing else is on the wire
                    if not self.inflight_inquiries:
                        self.last_write = 0

                    # Increment completed request counter
                    self.completed_requests += 1

                    # Shutdown if max-requests-per-conn exceeded
                    if self.completed_requests >= self.cookie['max_requests']:
                        break

                except OSError as e:
                    self.last_err = self.build_last_err("Connection Error: %s" % e)
                    log.write('LDAP.DEBUG', self.last_err)
                    break
                except coro.ClosedError:
                    self.last_err = self.build_last_err("Connection closed")
                    log.write('LDAP.DEBUG', self.last_err)
                    break
                except coro.TimeoutError:
                    # This is only an error if we've been waiting for
                    # self.read_timeout in response to inflight requests.
                    # Otherwise the connection is simply idle.
                    if self.has_read_timeout():
                        self.last_err = self.build_last_err("read timeout")
                        log.write('LDAP.DEBUG', self.last_err)
                        break
                    else:
                        # Idle connection, keep reading
                        pass
                except sslip.Error as e:
                    self.last_err = self.build_last_err("SSL Error: %s" % e)
                    log.write('LDAP.DEBUG', self.last_err)
                    break
                except EOFError:
                    self.last_err = self.build_last_err("Connection closed (EOF)")
                    log.write('LDAP.DEBUG', self.last_err)
                    break
                except coro.Interrupted:
                    log.write('LDAP.DEBUG',
                              self.build_last_err("Connection interrupted (reader)"))
                    break
                except:
                    exc_info = sys.exc_info()
                    self.last_err = self.build_last_err(tb.traceback_string(*exc_info))
                    log.write('COMMON.APP_FAILURE', self.last_err)

                    # Raise this generic error
                    raise

        finally:
            self.teardown_connection()

    def writer(self):
        """writer() - thread/method that writes to network"""
        try:
            while self.state == self.CONN_CONNECTED:
                try:
                    mid, inqr = self.out_fifo.pop()

                    try:
                        rendered_packet = self._rendered_packet_from_inquiry((mid, inqr))
                    except TypeError:
                        # If we have problem render the packet, then return it as an error
                        exc_info = sys.exc_info()
                        self.last_err = self.build_last_err(tb.traceback_string(*exc_info))
                        log.write('COMMON.APP_FAILURE', self.last_err)

                        inqr.state_to_done(False, self.last_err, None)
                        continue

                    try:
                        self.inflight_inquiries[mid] = inqr
                        self.s.send(rendered_packet)
                        self.last_write = coro.now
                    except:
                        # If problem while sending it over the wire, then requeue
                        if mid in self.inflight_inquiries:
                            del self.inflight_inquiries[mid]
                        self.out_fifo.push((mid, inqr))
                        raise

                except OSError as e:
                    self.last_err = self.build_last_err("Connection Error: %s" % e)
                    log.write('LDAP.DEBUG', self.last_err)
                    break
                except coro.ClosedError:
                    self.last_err = self.build_last_err("Connection closed")
                    log.write('LDAP.DEBUG', self.last_err)
                    break
                except sslip.Error as e:
                    self.last_err = self.build_last_err("SSL Error: %s" % e)
                    log.write('LDAP.DEBUG', self.last_err)
                    break
                except EOFError:
                    self.last_err = self.build_last_err("Connection closed (EOF)")
                    log.write('LDAP.DEBUG', self.last_err)
                    break
                except coro.Interrupted:
                    log.write('LDAP.DEBUG',
                              self.build_last_err("Connection interrupted (writer)"))
                    break
                except:
                    exc_info = sys.exc_info()
                    self.last_err = self.build_last_err(tb.traceback_string(*exc_info))
                    log.write('COMMON.APP_FAILURE', self.last_err)

                    # Raise this generic error
                    raise

        finally:
            self.teardown_connection()

    def _teardown_connection(self):
        if self.state == self.CONN_DEAD:
            return False

        # Mark as DEAD
        self.state = self.CONN_DEAD

        self.shutdown_flag = True

        # Return inquiries to server
        self.drain_inquiries()

        return True

    def teardown_connection(self, with_error=True):
        """teardown_connection()
        A connection has died due to a transport problem, or a
        connection has died because too many requests have been
        completed.  In short, teardown_connection() is called by the
        transport handling threads (reader or writer).

        Do everything necessary to move a connection into the DEAD
        state. DEAD connections are reaped by the sg_worker thread."""

        if self._teardown_connection():
            # Inform the parent
            sc = self.cookie['server_context']
            sc.dead_connection(self, with_error, auth_error=self.auth_failed)

    def next_ldap_msgid(self):
        """next_ldap_msgid()
        Utility to return next msg ID for this connection."""
        ldap_msgid = self.next_ldap_msg_id
        while True:
            next_id = ldap_msgid + 1
            # Detect ID roll-over
            if next_id >= 0x40000000:
                next_id = 1
            if ldap_msgid not in self.inflight_inquiries:
                break
            ldap_msgid = next_id
        self.next_ldap_msg_id = next_id
        return ldap_msgid

    def build_last_err(self, msg):
        """build_last_err(msg)
        Dress up an error message with connection info."""
        return '%s:%s(%s:%d) (%d) %s' % \
            (self.sg_name, self.hostname, self.ip, self.port,
             self.cookie['conn_id'], msg)

    def _render_packet(self, message_id, request):
        return ldap.encode_message(message_id, request)

    def _rendered_packet_from_inquiry(self, xxx_todo_changeme):
        """_render_operation_list()
        Convert a list of (id, inquiry) into a """
        (message_id, inquiry) = xxx_todo_changeme
        return ldap.encode_message(message_id, inquiry.get_rendered_operation())

    def _need(self, n):
        "Ensure at least <n> bytes in self.buffer"
        while len(self.buffer) < n:
            # Let caller deal with timeout
            block = coro.with_timeout(self.read_timeout, self.s.recv, 8192)
            if not block:
                raise EOFError
            # tdraegen XXX - um, string concatenation?
            self.buffer += block

    def _recv_packet(self):
        # All received packets must be BER SEQUENCE. We can tell from
        # the header how much data we need to complete the packet.
        # ensure we have the sequence header - I'm inlining the (type,
        # length) detection here to get good buffering behavior
        self._need(2)
        tag = self.buffer[0]
        if tag != '0':  # SEQUENCE | STRUCTURED
            self.last_err = self.build_last_err(
                'Received invalid LDAP packet: invalid starting tag: %s' %
                self.buffer)
            return (None, None)
        l = ord(self.buffer[1])
        if l & 0x80:
            # <l> tells us how many bytes of actual length
            ll = l & 0x7f
            self._need(2 + ll)
            # fetch length
            n = 0
            for i in xrange (ll):
                n = (n << 8) | ord(self.buffer[2 + i])
            if (n < 0) or (n > 1000000):
                # let's be reasonable, folks
                self.last_err = self.build_last_err(
                    'Received invalid LDAP packet: '
                    'invalid packet length: %d, buffer: %s' %
                    (n, self.buffer))
                return (None, None)
            need = n + 2 + ll
        else:
            # <l> is the length of the sequence
            need = l + 2
        # fetch the rest of the packet...
        self._need(need)
        # this will probably empty self.buffer
        packet, self.buffer = self.buffer[:need], self.buffer[need:]
        try:
            # We could do: return ldap.decode(packet)[0]
            # but then we'd lose debugging info related to bug 12719.
            try:
                (message_id, answer), unused = ldap.decode(packet)
            except ValueError:
                self.last_err = self.build_last_err(
                    'Received invalid LDAP packet: Top-level LDAP packet '
                    'is composed of something other than message ID and '
                    'response: %r' % (packet,))
                return (None, None)
            else:
                return (message_id, answer)
        except ldap.DecodeError as e:
            self.last_err = self.build_last_err(
                'Received invalid LDAP packet: %s, %r' % (str(e), packet))
            return (None, None)

class ldap_binder_connection(ldap_connection):
    """Derived class to override BIND-specific connection behavior."""

    def drain_inquiries(self):
        """drain_inquiries()
        Return inquiries back to server."""
        drain_list = self._get_drain_list()
        if drain_list:
            sc = self.cookie['server_context']
            sc.connection_bind_inquiry_give_back(drain_list)

    def inquiry_count(self):
        """inquiry_count() -> number of outstanding, and inflight
        requests.

        Server calls this to determine if this connection is currently
        devoid of inquiries.
        """
        return len(self.out_fifo) + len(self.inflight_inquiries)

    def setup_connection(self):
        """setup_connection(); connect to a socket.  Once a socket has
        been connected, reader and writer threads are spawned to handle
        LDAP operations."""
        log.write('LDAP.DEBUG', self.build_last_err("connecting to server"))
        try:
            self.state = self.CONN_CONNECTING
            if self.cookie['use_ssl']:
                sock = coro_ssl.ssl_sock(ldap_api.ssl_ctx)
                sock.create()
            else:
                sock = coro.tcp_sock()

            if self.cookie['bind_ip'] is not None:
                sock.bind((self.cookie['bind_ip'], 0))

            sock.connect((self.ip, self.port))
            if self.cookie['use_ssl']:
                sock.ssl_connect()

            self.s = sock

        except sslip.Error as e:
            self.last_err = self.build_last_err('SSL Error: %s' % e)
            log.write('LDAP.DEBUG', self.last_err)
            self.teardown_connection()

        except OSError as e:
            self.last_err = self.build_last_err('Connection Error: %s' % e)
            log.write('LDAP.DEBUG', self.last_err)
            self.teardown_connection()

        else:
            # Server is responsive
            self.cookie['server_context'].server_responsive()

            # Deal with StartTLS
            if not self.start_starttls():
                self.teardown_connection()
                return

            # Spawn readers and writers
            if self.state == self.CONN_CONNECTING:
                self.state = self.CONN_CONNECTED
                self.writer_thread = coro.spawn(self.writer)
                self.reader_thread = coro.spawn(self.reader)

    def reader(self):
        """reader() - thread/method that reads from network"""
        try:
            while self.state == self.CONN_CONNECTED:
                try:
                    # Receive a packet
                    message_id, response = self._recv_packet()

                    # _recv_packet() returns (None, None) if conn dies
                    if message_id is None:
                        # self.last_err already populated
                        log.write('LDAP.DEBUG', self.last_err)
                        break

                    # Lookup in-flight operation
                    try:
                        inquiry = self.inflight_inquiries[message_id]
                    except KeyError:
                        self.last_err = self.build_last_err('unexpected msg id: %s' % message_id)
                        log.write('LDAP.DEBUG', self.last_err)
                        break

                    # A successful read means this server is not dead
                    sc = self.cookie['server_context']
                    sc.note_connection_read()

                    # Process this response.
                    success, result = inquiry.process_response(response)

                    # No longer in flight
                    del self.inflight_inquiries[message_id]

                    inquiry.state_to_done(success, result, self.connection_name)

                    # Update self.last_write if nothing else is on the wire
                    if not self.inflight_inquiries:
                        self.last_write = 0

                    # Increment completed request counter
                    self.completed_requests += 1

                    # Shutdown if max-requests-per-conn exceeded
                    if self.completed_requests >= self.cookie['max_requests']:
                        break

                except OSError as e:
                    self.last_err = self.build_last_err("Connection Error: %s" % e)
                    log.write('LDAP.DEBUG', self.last_err)
                    break
                except coro.ClosedError:
                    self.last_err = self.build_last_err("Connection closed")
                    log.write('LDAP.DEBUG', self.last_err)
                    break
                except coro.TimeoutError:
                    # This is only an error if we've been waiting for
                    # self.read_timeout in response to inflight requests.
                    # Otherwise the connection is simply idle.
                    if self.has_read_timeout():
                        self.last_err = self.build_last_err("read timeout")
                        log.write('LDAP.DEBUG', self.last_err)
                        break
                    else:
                        # Idle connection, keep reading
                        pass
                except sslip.Error as e:
                    self.last_err = self.build_last_err("SSL Error: %s" % e)
                    log.write('LDAP.DEBUG', self.last_err)
                    break
                except EOFError:
                    self.last_err = self.build_last_err("Connection closed (EOF)")
                    log.write('LDAP.DEBUG', self.last_err)
                    break
                except coro.Interrupted:
                    log.write('LDAP.DEBUG',
                              self.build_last_err("Connection interrupted (reader)"))
                    break
                except:
                    exc_info = sys.exc_info()
                    self.last_err = self.build_last_err(tb.traceback_string(*exc_info))
                    log.write('COMMON.APP_FAILURE', self.last_err)

                    # Raise this generic error
                    raise

        finally:
            self.teardown_connection()

    def teardown_connection(self, with_error=True):
        """teardown_connection()
        A connection has died due to a transport problem, or a
        connection has died because too many requests have been
        completed.  In short, tearddown_connection() is called by the
        transport handling threads (reader or writer).

        Do everything necessary to move a connection into the DEAD
        state. DEAD connections are reaped by the sg_worker thread."""

        if self._teardown_connection():
            # Inform the parent
            sc = self.cookie['server_context']
            sc.dead_bind_connection(self, with_error)

class QlogWrapper:
    def __init__(self):
        self._thread = None
        self._fifo = coro.fifo()

    def _run(self):
        import qlog
        while True:
            try:
                while True:
                    msgs = self._fifo.pop_all()
                    for message, args, kwargs in msgs:
                        qlog.write(message, *args, **kwargs)
            except coro.Interrupted:
                raise
            except:
                qlog.write('COMMON.APP_FAILURE', tb.traceback_string())
                coro.sleep_relative(10)

    def write(self, message, *args, **kwargs):
        if self._thread is None:
            self._thread = coro.spawn(self._run)
        self._fifo.push((message, args[:], copy.copy(kwargs)))

# Fake one for bootstrapping/development
class QlogWrapperFake:
    def __init__(self):
        self._thread = None
        self._fifo = coro.fifo()

    def _run(self):
        while True:
            try:
                while True:
                    msgs = self._fifo.pop_all()
                    for message, args, kwargs in msgs:
                        print message + ' ' + args[0]
            except coro.Interrupted:
                raise
            except:
                print 'COMMON.APP_FAILURE ' + tb.traceback_string()
                coro.sleep_relative(10)

    def write(self, message, *args, **kwargs):
        if self._thread is None:
            self._thread = coro.spawn(self._run)
        self._fifo.push((message, args[:], copy.copy(kwargs)))

log = QlogWrapper()

# __main__

if __name__ == '__main__':
    import backdoor
    import comm_path
    import os
    import service

    log = QlogWrapperFake()

    bd_path = comm_path.mk_backdoor_path('ldap')
    coro.spawn (backdoor.serve, unix_path=bd_path, global_dict=service.__dict__, thread_name='backdoor')

    # Make a client context
    client = ldap_client()

    # Make a server-group
    sg = client.create_server_group("my_test_group")

    # Add a server
    sg.add_server("localhost", 1111, 'password',
                  {'user': 'fakie', 'password': 'mypass'},
                  TRANSPORT_PLAINTEXT)

    sg.add_server("localhost", 1112, 'anonymous',
                  {'user': 'fakie', 'password': 'mypass'},
                  TRANSPORT_PLAINTEXT)

    # XXX modify max number of connections
    sg.set_max_connections(10)

    # Start the sg
    sg.start()

    try:
        coro.event_loop(30.0)
    finally:
        try:
            os.unlink(bd_path)
        except:
            pass
