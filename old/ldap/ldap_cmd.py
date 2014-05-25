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

import coro

class ServerGroupShutdown(Exception):
    def __init__(self, sg_ctx):
        self.sg_ctx = sg_ctx


class Cmd(object):
    """The base command class for controlling the worker thread main loop """

    def __eq__(self, other):
        return (self is other)

    def run(self, sg_ctx):
        """Run the command object
        All subclass should override this method
        :Parameters:
            - `sg_ctx` : the LDAP server group context
        """
        raise Exception("Implement run()")


class CmdBootstrap(Cmd):
    """This command is initiated at the start of the worker thread.  Its
    purpose is to do any needed initialization.
    """

    def run(self, sg_ctx):
        # Populate the periodic 'inquiry_timeout_event'
        sg_ctx._inquiry_timeout_event(sg_ctx.inquiry_timeout + coro.now)


class CmdConn(Cmd):
    def __init__(self, server, via_event=False):
        self.server = server
        self.via_event = via_event

    def __eq__(self, other):
        return (self.__class__ == other.__class__ and
                self.server == other.server and
                self.via_event == other.via_event)

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.server)

    def run(self, sg_ctx):
        if self.server in sg_ctx.servers:
            self.server.update_connections()


class CmdBindConn(CmdConn):
    def __init__(self, server, via_event=False):
        self.server = server
        self.via_event = via_event

    def run(self, sg_ctx):
        if self.server in sg_ctx.servers:
            self.server.update_bind_connections()


class CmdConnTimeout(CmdConn):
    def run(self, sg_ctx):
        # Get the server that needs attention
        if self.server in sg_ctx.servers:
            self.server.timeout_old_connections(coro.now)
            # Add another 'conn_timeout' event
            self.server.calculate_next_conn_timeout()


class CmdServerState(Cmd):
    def __init__(self, server):
        self.server = server

    def run(self, sg_ctx):
        if self.server in sg_ctx.servers:
            self.server.state_transition()


class CmdShutdown(Cmd):
    def run(self, sg_ctx):
        # Tell servers to cease all connections
        if sg_ctx._shutting_down == 0:
            sg_ctx._shutting_down = 1
            for srv in sg_ctx.servers:
                srv.shutdown()

        # Clear out the event list
        sg_ctx.event_list = []

        # The server is now ready to be shutdown, this command
        # will terminate the sg worker's main loop.  It will be
        # the last thing in this server fifo queue.
        sg_ctx.worker_fifo.push(CmdShutdownSgWorker())


class CmdShutdownSgWorker(Cmd):
    def run(self, sg_ctx):
        if sg_ctx.unattached_inquiries:
            try:
                # Transfer the pending inquiries to the new server if possible
                new_sg_ctx = sg_ctx.client.server_groups[sg_ctx.name]
                new_sg_ctx.unattached_inquiries.extend(sg_ctx.unattached_inquiries)
            except KeyError:
                # Not possible to transfer, return failure
                for inq in sg_ctx.unattached_inquiries:
                    inq.state_to_done(False, "service shutdown")
        sg_ctx._shutting_down = 2
        # This will terminate the sg worker thread's main loop, and thus
        # terminate the server
        raise ServerGroupShutdown(sg_ctx)


class CmdShutdownConn(Cmd):
    def __init__(self, srv, conn):
        self.srv = srv
        self.conn = conn

    def __repr__(self):
        return '<CmdShutdownConn: %s>' % (self.conn,)

    def shutdown_connection(self, sg_ctx):
        assert(self.conn.state == self.conn.CONN_DEAD)
        assert(len(self.conn.inflight_inquiries) == 0)
        assert(len(self.conn.out_fifo) == 0)
        # shutdown the reader
        if self.conn.reader_thread:
            self.conn.reader_thread.shutdown()
            self.conn.reader_thread.join()
            self.conn.reader_thread = None
        # shutdown the writer
        if self.conn.writer_thread:
            self.conn.writer_thread.shutdown()
            self.conn.writer_thread.join()
            self.conn.writer_thread = None
        # close the socket
        if self.conn.s:
            self.conn.s.close()
            self.conn.s = None

    def run(self, sg_ctx):
        self.shutdown_connection(sg_ctx)

        # update connections
        sg_ctx.worker_fifo.push(CmdConn(self.srv))

class CmdShutdownBindConn(CmdShutdownConn):
    def run(self, sg_ctx):
        self.shutdown_connection(sg_ctx)

        # update bind connections
        sg_ctx.worker_fifo.push(CmdBindConn(self.srv))

class CmdSetCompat(Cmd):
    def __init__(self, compatibility):
        self.compatibility = compatibility

    def run(self, sg_ctx):
        sg_ctx.compatibility = self.compatibility


class CmdSetInqTimeout(Cmd):
    def __init__(self, inquiry_timeout):
        self.inquiry_timeout = inquiry_timeout

    def run(self, sg_ctx):
        sg_ctx.inquiry_timeout = self.inquiry_timeout * coro.ticks_per_sec
        # Update timeout by forcing 'inquiry_timeout_event'
        sg_ctx._inquiry_timeout_request()


class CmdSetMaxConns(Cmd):
    def __init__(self, max_conns):
        self.max_conns = max_conns

    def run(self, sg_ctx):
        if sg_ctx.max_conns != self.max_conns:
            sg_ctx.max_conns = self.max_conns
            for srv in sg_ctx.servers:
                srv.update_max_connections(self.max_conns)


class CmdSetMaxTimePerConn(Cmd):
    def __init__(self, max_time_per_conn):
        self.max_time_per_conn = max_time_per_conn

    def run(self, sg_ctx):
        if sg_ctx.max_time_per_conn != self.max_time_per_conn:
            sg_ctx.max_time_per_conn = self.max_time_per_conn
            for srv in sg_ctx.servers:
                srv.update_max_time_per_connection(self.max_time_per_conn)


class CmdSetMaxRequestsPerConn(Cmd):
    def __init__(self, max_requests_per_conn):
        self.max_requests_per_conn = max_requests_per_conn

    def run(self, sg_ctx):
        if sg_ctx.max_requests_per_conn != self.max_requests_per_conn:
            sg_ctx.max_requests_per_conn = self.max_requests_per_conn
            for srv in sg_ctx.servers:
                srv.update_max_requests_per_connection(self.max_requests_per_conn)


class CmdSetCacheSize(Cmd):
    def __init__(self, cache_size):
        self.cache_size = cache_size

    def run(self, sg_ctx):
        sg_ctx.cache_size = self.cache_size
        sg_ctx.clear_cache()


class CmdSetCacheTtl(Cmd):
    def __init__(self, cache_ttl):
        self.cache_ttl = cache_ttl

    def run(self, sg_ctx):
        sg_ctx.cache_ttl = self.cache_ttl
        sg_ctx.clear_cache()


class CmdSetOperationTimeout(Cmd):
    def __init__(self, operation_timeout):
        self.operation_timeout = operation_timeout

    def run(self, sg_ctx):
        if sg_ctx.operation_timeout != self.operation_timeout:
            sg_ctx.operation_timeout = self.operation_timeout
            for srv in sg_ctx.servers:
                srv.update_operation_timeout(self.operation_timeout)


class CmdSetFailoverTimeout(Cmd):
    def __init__(self, failover_timeout):
        self.failover_timeout = failover_timeout

    def run(self, sg_ctx):
        if sg_ctx.failover_timeout != self.failover_timeout:
            sg_ctx.failover_timeout = self.failover_timeout
            for srv in sg_ctx.servers:
                srv.update_failover_timeout(self.failover_timeout)


class CmdInquiries(Cmd):
    def run(self, sg_ctx):
        sg_ctx.pending_inquiries_event = False
        for index in xrange(len(sg_ctx.unattached_inquiries)):
            inq = sg_ctx.unattached_inquiries.pop(0)
            q_server = sg_ctx.get_server_for_inquiry()
            if q_server:
                q_server.resolve_inquiry(inq)
            else:
                sg_ctx.unattached_inquiries.append(inq)

        # Check to see if all servers are failed because
        # of bad-authentication
        if sg_ctx.check_auth_failure() and sg_ctx.unattached_inquiries:
            while sg_ctx.unattached_inquiries:
                inq = sg_ctx.unattached_inquiries.pop(0)
                inq.state_to_done(False, "server authentication failed")


class CmdInquiryList(Cmd):
    def __init__(self, inquiries):
        self.inquiries = inquiries

    def run(self, sg_ctx):
        if isinstance(self.inquiries, list) and self.inquiries:
            sg_ctx.unattached_inquiries.extend(self.inquiries)
            if not sg_ctx.pending_inquiries_event:
                sg_ctx.pending_inquiries_event = True
                sg_ctx.worker_fifo.push(CmdInquiries())


class CmdBindInquiries(Cmd):
    def run(self, sg_ctx):
        sg_ctx.pending_bind_inquiries_event = False
        attachment_failures = []
        while (sg_ctx.unattached_bind_inquiries):
            inq = sg_ctx.unattached_bind_inquiries.pop(0)
            q_server = sg_ctx.get_server_for_inquiry()
            if q_server:
                q_server.resolve_bind_inquiry(inq)
            else:
                attachment_failures.append(inq)
        if attachment_failures:
            # Some inquiries couldn't be attached; this is
            # only possible if no servers are available.
            sg_ctx.unattached_bind_inquiries = attachment_failures


class CmdBindInquiryList(Cmd):
    def __init__(self, inquiries):
        self.inquiries = inquiries

    def run(self, sg_ctx):
        # Put list of inquiries back on unattached_bind_inquiries
        if isinstance(self.inquiries, list) and self.inquiries:
            sg_ctx.unattached_bind_inquiries.extend(self.inquiries)
            if not sg_ctx.pending_bind_inquiries_event:
                sg_ctx.pending_bind_inquiries_event = True
                sg_ctx.worker_fifo.push(CmdBindInquiries())


class CmdServerConnected(Cmd):
    def __init__(self, server):
        self.server = server

    def __repr__(self):
        return '<CmdServerConnected: %s>' % (self.server,)

    def run(self, sg_ctx):
        # A server has completely connected
        if not sg_ctx.pending_inquiries_event and \
                sg_ctx.unattached_inquiries:
            sg_ctx.pending_inquiries_event = True
            sg_ctx.worker_fifo.push(CmdInquiries())
        if not sg_ctx.pending_bind_inquiries_event and \
                sg_ctx.unattached_bind_inquiries:
            sg_ctx.pending_bind_inquiries_event = True
            sg_ctx.worker_fifo.push(CmdBindInquiries())


class CmdInquiryTimeout(Cmd):
    def run(self, sg_ctx):
        # It's time to expire some inquiries, maybe
        valid_list = []
        valid_birth = None
        while (sg_ctx.unattached_inquiries):
            inq = sg_ctx.unattached_inquiries.pop(0)

            if (inq.get_birth() + sg_ctx.inquiry_timeout) > coro.now:
                valid_list.append(inq)
                if not valid_birth or (inq.get_birth() < valid_birth):
                    valid_birth = inq.get_birth()

        if valid_list:
            sg_ctx.unattached_inquiries = valid_list
            sg_ctx.pending_inquiries_event = True
            sg_ctx.worker_fifo.push(CmdInquiries())

        # Check the BIND list
        valid_bind_list = []
        valid_bind_birth = None
        while (sg_ctx.unattached_bind_inquiries):
            inq = sg_ctx.unattached_bind_inquiries.pop(0)

            if (inq.get_birth() + sg_ctx.inquiry_timeout) > coro.now:
                valid_bind_list.append(inq)
                if not valid_bind_birth or (inq.get_birth() < valid_bind_birth):
                    valid_bind_birth = inq.get_birth()

        if valid_bind_list:
            sg_ctx.unattached_bind_inquiries = valid_bind_list
            sg_ctx.pending_bind_inquiries_event = True
            sg_ctx.worker_fifo.push(CmdBindInquiries())

        # Add a new 'inquiry_timeout_event' event
        if valid_birth and valid_bind_birth:
            wake_time = min(valid_birth, valid_bind_birth) + sg_ctx.inquiry_timeout
        elif valid_birth:
            wake_time = valid_birth + sg_ctx.inquiry_timeout
        elif valid_bind_birth:
            wake_time = valid_bind_birth + sg_ctx.inquiry_timeout
        else:
            wake_time = sg_ctx.inquiry_timeout + coro.now
        # Only add one
        add_event = True
        for wt, event in sg_ctx.event_list:
            if isinstance(event, CmdInquiryTimeout):
                add_event = False
                if wt > wake_time:
                    # Replace 'wt' with 'wake_time'
                    rindex = sg_ctx.event_list.index((wt, event))
                    sg_ctx.event_list[rindex] = (wake_time, event)
        if add_event:
            sg_ctx._inquiry_timeout_event(wake_time)
