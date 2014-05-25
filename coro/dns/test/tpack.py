# -*- Mode: Python -*-

import coro
import coro.dns.packet as dns

def testpacker():
    # See section 4.1.4 of RFC 1035
    p = dns.Packer()
    p.addbytes('*' * 20)
    p.addname('f.ISI.ARPA')
    p.addbytes('*' * 8)
    p.addname('Foo.F.isi.arpa')
    p.addbytes('*' * 18)
    p.addname('arpa')
    p.addbytes('*' * 26)
    p.addname('')
    packet = p.getbuf()
    assert packet == (
        '********************\x01f\x03ISI\x04ARPA\x00'
        '********\x03Foo\xc0\x14******************\xc0\x1a'
        '**************************\x00'
    )
    u = dns.Unpacker (packet)
    res = (
        u.getbytes(20),
        u.getname(),
        u.getbytes(8),
        u.getname(),
        u.getbytes(18),
        u.getname(),
        u.getbytes(26),
        u.getname(),
    )
    assert res == (
        '********************',
        'f.isi.arpa',
        '********',
        'foo.f.isi.arpa',
        '******************',
        'arpa',
        '**************************',
        ''
    )

def test_packer_2 ():
    p = dns.Packer()
    h = dns.Header()
    h.id = 3141
    h.opcode = dns.OPCODE.QUERY
    h.rd = 0
    h.ancount = 1
    h.arcount = 1
    h.qdcount = 1
    p.addHeader (h)
    p.addQuestion ('glerg.org', dns.TYPE.CNAME, dns.CLASS.IN)
    p.addCNAME ('glerg.org', dns.CLASS.IN, 3000, 'blerb.com')
    p.addHINFO ('brodig.com', dns.CLASS.IN, 5000, 'vax', 'vms')
    data = p.getbuf()
    u = dns.Unpacker (data)
    h, qdl, anl, nsl, arl = u.unpack()
    assert qdl == [('glerg.org', 5, 1)]
    assert anl == [('glerg.org', 'CNAME', 'IN', 3000, 'blerb.com')]
    assert arl == [('brodig.com', 'HINFO', 'IN', 5000, ('vax', 'vms'))]
    assert nsl == []
    assert h.id == 3141
    assert h.opcode == dns.OPCODE.QUERY
    assert h.ancount == 1
    assert h.qdcount == 1

def t0 (qname='www.nightmare.com', qtype=dns.TYPE.A):
    m = dns.Packer()
    h = dns.Header()
    h.id = 3141
    h.opcode = dns.OPCODE.QUERY
    h.rd = 1
    h.qdcount = 1
    m.addHeader (h)
    m.addQuestion (qname, qtype, dns.CLASS.IN)
    p = m.getbuf()
    return p

def t1 (qname, qtype):
    p = t0 (qname, getattr (dns.TYPE, qtype))
    s = coro.udp_sock()
    s.connect (('192.168.200.1', 53))
    s.send (p)
    r = s.recv (8192)
    coro.write_stderr ('reply=%r\n' % (r,))
    u = dns.Unpacker (r)
    return u.unpack()

def t2():
    import coro.dns.stub_resolver
    r = coro.dns.stub_resolver.stub_resolver (['192.168.200.1'])
    coro.set_resolver (r)

# XXX make this into a real unit test.
if __name__ == '__main__':
    # import coro.backdoor
    # coro.spawn (coro.backdoor.serve, unix_path='/tmp/xx.bd')
    # coro.event_loop()
    test_packer_2()
