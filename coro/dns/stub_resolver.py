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
        self.inflight_ids = set()

    def lookup (self, qname, qtype, timeout=10, retries=3):
        m = packet.Packer()
        h = packet.Header()
        while 1:
            qid = random.randrange (65536)
            # avoid collisions
            if qid not in self.inflight_ids:
                break
        h.id = qid
        h.opcode = packet.OPCODE.QUERY
        h.rd = 1
        h.qdcount = 1
        m.addHeader (h)
        m.addQuestion (qname, qtype, packet.CLASS.IN)
        p = m.getbuf()
        for addr in self.nameservers:
            for i in range (retries):
                self.inflight.acquire (1)
                self.inflight_ids.add (qid)
                try:
                    s = coro.udp_sock()
                    s.connect ((addr, 53))
                    s.send (p)
                    try:
                        reply = coro.with_timeout (timeout, s.recv, 1000)
                        u = packet.Unpacker (reply)
                        result = u.unpack()
                        rh = result[0]
                        if rh.id != qid:
                            raise QueryFailed ("bad id in reply")
                        else:
                            return result
                    except coro.TimeoutError:
                        pass
                finally:
                    self.inflight.release (1)
                    self.inflight_ids.remove (qid)

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

def install (nameserver_ips):
    "install a stub resolver into the coro socket layer"
    coro.set_resolver (
        stub_resolver (nameserver_ips)
    )
