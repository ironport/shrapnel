# -*- Mode: Python -*-

import coro
import coro.dns
import coro.dns.packet as packet

import random

class QueryFailed (Exception):
    pass

class stub_resolver:

    def __init__ (self, nameservers, inflight=200):
        self.nameservers = nameservers
        self.inflight = coro.semaphore (inflight)

    def lookup (self, qname, qtype, timeout=10, retries=3):
        m = packet.Packer()
        h = packet.Header()
        # XXX need to avoid collisions
        h.id = random.randrange (65536)
        h.opcode = packet.OPCODE.QUERY
        h.rd = 1
        h.qdcount = 1
        m.addHeader (h)
        m.addQuestion (qname, qtype, packet.CLASS.IN)
        p = m.getbuf()
        for addr in self.nameservers:
            for i in range (retries):
                self.inflight.acquire (1)
                try:
                    s = coro.udp_sock()
                    s.connect ((addr, 53))
                    s.send (p)
                    try:
                        reply = coro.with_timeout (timeout, s.recv, 1000)
                        u = packet.Unpacker (reply)
                        return u.unpack()
                    except coro.TimeoutError:
                        pass
                finally:
                    self.inflight.release (1)
        raise QueryFailed ("no reply from nameservers")

    def gethostbyname (self, name, qtype):
        header, qdl, anl, nsl, arl = self.lookup (name, qtype)
        for answer in anl:
            name, rtype, _, ttl, addr = answer
            if getattr (packet.TYPE, rtype) == qtype:
                return addr
        else:
            raise QueryFailed ("no answer in nameserver reply")

    def resolve_ipv4 (self, name):
        return self.gethostbyname (name, packet.TYPE.A)

    def resolve_ipv6 (self, name):
        return self.gethostbyname (name, packet.TYPE.AAAA)
