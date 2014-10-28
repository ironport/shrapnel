# -*- Mode: Cython -*-

# See RFC1035
# History/Sources: Old-School Python DNS Demo, IronPort, Eric Huss's hand-written C update.

import socket

from libc.stdint cimport uint32_t, uint16_t, uint8_t
from libc.string cimport memcpy
from cpython.string cimport PyString_FromStringAndSize

# updated from a document at the IANA
# TYPE values (section 3.2.2)

class TYPE:
    A       = 1   # a host address                           [RFC1035]
    NS      = 2   # an authoritative name server             [RFC1035]
    MD      = 3   # a mail destination (Obsolete - use MX)   [RFC1035]
    MF      = 4   # a mail forwarder (Obsolete - use MX)     [RFC1035]
    CNAME   = 5   # the canonical name for an alias          [RFC1035]
    SOA     = 6   # marks the start of a zone of authority   [RFC1035]
    MB      = 7   # a mailbox domain name (EXPERIMENTAL)     [RFC1035]
    MG      = 8   # a mail group member (EXPERIMENTAL)       [RFC1035]
    MR      = 9   # a mail rename domain name (EXPERIMENTAL) [RFC1035]
    _NULL   = 10  # a null RR (EXPERIMENTAL)                 [RFC1035]
    WKS     = 11  # a well known service description         [RFC1035]
    PTR     = 12  # a domain name pointer                    [RFC1035]
    HINFO   = 13  # host information                         [RFC1035]
    MINFO   = 14  # mailbox or mail list information         [RFC1035]
    MX      = 15  # mail exchange                            [RFC1035]
    TXT     = 16  # text strings                             [RFC1035]
    RP      = 17  # for Responsible Person                   [RFC1183]
    AFSDB   = 18  # for AFS Data Base location               [RFC1183]
    X25     = 19  # for X.25 PSDN address                    [RFC1183]
    ISDN    = 20  # for ISDN address                         [RFC1183]
    RT      = 21  # for Route Through                        [RFC1183]
    NSAP    = 22  # for NSAP address, NSAP style A record    [RFC1706]
    NSAPPTR = 23  #
    SIG     = 24  # for security signature                   [RFC2535]
    KEY     = 25  # for security key                         [RFC2535]
    PX      = 26  # X.400 mail mapping information           [RFC2163]
    GPOS    = 27  # Geographical Position                    [RFC1712]
    AAAA    = 28  # IP6 Address                              [Thomson]
    LOC     = 29  # Location Information                     [Vixie]
    NXT     = 30  # Next Domain                              [RFC2535]
    EID     = 31  # Endpoint Identifier                      [Patton]
    NIMLOC  = 32  # Nimrod Locator                           [Patton]
    SRV     = 33  # Server Selection                         [RFC2782]
    ATMA    = 34  # ATM Address                              [Dobrowski]
    NAPTR   = 35  # Naming Authority Pointer                 [RFC2168, RFC2915]
    KX      = 36  # Key Exchanger                            [RFC2230]
    CERT    = 37  # CERT                                     [RFC2538]
    A6      = 38  # A6                                       [RFC2874]
    DNAME   = 39  # DNAME                                    [RFC2672]
    SINK    = 40  # SINK                                     [Eastlake]
    OPT     = 41  # OPT                                      [RFC2671]
    UINFO   = 100 #                                          [IANA-Reserved]
    UID     = 101 #                                          [IANA-Reserved]
    GID     = 102 #                                          [IANA-Reserved]
    UNSPEC  = 103 #                                          [IANA-Reserved]
    TKEY    = 249 # Transaction Key                          [RFC2930]
    TSIG    = 250 # Transaction Signature                    [RFC2845]
    IXFR    = 251 # incremental transfer                     [RFC1995]
    AXFR    = 252 # transfer of an entire zone               [RFC1035]
    MAILB   = 253 # mailbox-related RRs (MB, MG or MR)       [RFC1035]
    MAILA   = 254 # mail agent RRs (Obsolete - see MX)       [RFC1035]
    ANY     = 255 # A request for all records                [RFC1035]
    # Additional TYPE values from host.c source
    UNAME   = 110
    MP      = 240

TYPE_MAP = {}
for name in dir(TYPE):
    if not name.startswith ('__'):
        TYPE_MAP [getattr (TYPE, name)] = name

# CLASS values (section 3.2.4)

class CLASS:
    IN = 1 # the Internet
    CS = 2 # the CSNET class (Obsolete - used only for examples in some obsolete RFCs)
    CH = 3 # the CHAOS class
    HS = 4 # Hesiod [Dyer 87]

CLASS_MAP = {}
for name in dir(CLASS):
    if not name.startswith ('__'):
        CLASS_MAP [getattr (CLASS, name)] = name

# QCLASS values (section 3.2.5)
class QCLASS:
    ANY = 255 # any class

class OPCODE:
    QUERY = 0
    IQUERY = 1
    STATUS = 2

class RCODE:
    NoError    = 0
    FormErr    = 1
    ServFail   = 2
    NXDomain   = 3
    NotImp     = 4
    Refused    = 5
    YXDomain   = 6
    YXRRSet    = 7
    NXRRSet    = 8
    NotAuth    = 9
    NotZone    = 10
    BADVERS    = 16
    BADSIG     = 16
    BADKEY     = 17
    BADTIME    = 18
    BADMODE    = 19
    BADNAME    = 20
    BADALG     = 21

RCODE_MAP = {}
for name in dir (RCODE):
    if not name.startswith ('__'):
        RCODE_MAP [getattr (RCODE, name)] = name

# Low-level 16 and 32 bit integer packing and unpacking

cpdef bytes pack16bit (uint32_t n):
    cdef unsigned char r[2]
    r[0] = (n >> 8) & 0xff
    r[1] =    n     & 0xff
    return r[:2]

cpdef bytes pack32bit (uint32_t n):
    cdef unsigned char r[4]
    r[0] = (n >> 24) & 0xff
    r[1] = (n >> 16) & 0xff    
    r[2] = (n >>  8) & 0xff
    r[3] = (n >>  0) & 0xff
    return r[:4]

cpdef int unpack16bit (unsigned char * s):
    return (s[0])<<8 | (s[1])

cpdef int unpack32bit (unsigned char * s):
    return (  (s[0]) << 24
            | (s[1]) << 16
            | (s[2]) << 8
            | (s[3]) << 0 )
            
# XXX Use inet_pton, inet_ntop directly.

def addr2bin (addr):
    cdef uint32_t n
    if type (addr) == type (0):
        return addr
    parts = addr.split ('.')
    if len (parts) != 4:
        raise ValueError ('bad IP address')
    n = 0
    for byte in parts:
        n = n<<8 | int (byte)
    return n

def bin2addr (n):
    return '%d.%d.%d.%d' % (
        (n>>24)&0xFF,
        (n>>16)&0xFF,
        (n>>8)&0xFF,
        n&0xFF
        )

cdef class buffer:
    cdef uint32_t offset, size
    cdef bytes data
    def __init__ (self, size=500):
        self.data = PyString_FromStringAndSize (NULL, size)
        self.size = size
        self.offset = 0
    cdef ensure (self, int n):
        cdef int new_size = self.size + (self.size // 2)
        if self.offset + n > self.size:
            self.data = PyString_FromStringAndSize (self.data, new_size)
    def add (self, bytes d):
        cdef char * buf = self.data
        cdef char * dp = d
        cdef int n = len (d)
        self.ensure (n)
        memcpy (buf + self.offset, dp, n)
        self.offset += n
    def add_byte (self, unsigned char d):
        cdef char * buf = self.data
        self.ensure (1)
        buf[self.offset] = d
        self.offset += 1
    def get (self):
        return self.data[:self.offset]
    # used to retroactively set the size of an RR
    def set16 (self, uint32_t offset, uint16_t val):
        cdef char * buf = self.data
        if offset > 0 and offset <= self.offset - 2:
            buf[offset+0] = (val >> 8) & 0xff
            buf[offset+1] =    val     & 0xff
        else:
            raise IndexError (offset)

cdef class Header:
    cdef public uint16_t id, qdcount, ancount, nscount, arcount
    cdef public uint8_t qr, opcode, aa, tc, rd, ra, z, rcode
    cdef set (self, id,
              qr, opcode, aa, tc, rd, ra, z, rcode,
              qdcount, ancount, nscount, arcount
              ):
        self.id = id
        self.qr = qr
        self.opcode = opcode
        self.aa = aa
        self.tc = tc
        self.rd = rd
        self.ra = ra
        self.z = z
        self.rcode = rcode
        self.qdcount = qdcount
        self.ancount = ancount
        self.nscount = nscount
        self.arcount = arcount
        return self

class PackError (Exception):
    pass

cdef class Packer:
    cdef buffer buf
    cdef dict index
    cdef uint32_t rdstart
    def __init__ (self):
        self.buf = buffer()
        self.index = {}
        self.rdstart = 0
    cdef add (self, bytes d):
        self.buf.add (d)
    def getbuf (self):
        return self.buf.get()
    cpdef addbyte (self, unsigned char c):
        self.buf.add_byte (c)
    cpdef addbytes (self, bytes b):
        self.add (b)
    cpdef add16bit (self, uint16_t n):
        self.add (pack16bit (n))
    cpdef add32bit (self, uint32_t n):
        self.add (pack32bit (n))
    cpdef addaddr (self, bytes addr):
        n = addr2bin (addr)
        self.add (pack32bit (n))
    cpdef addstring (self, bytes s):
        self.addbyte (len(s))
        self.addbytes (s)
    cpdef compressed_addname (self, bytes name):
        # Domain name packing (section 4.1.4)
        # Add a domain name to the buffer, possibly using pointers.
        # The case of the first occurrence of a name is preserved.
        # Redundant dots are ignored.
        parts = [p for p in name.split ('.') if p]
        for part in parts:
            if len (part) > 63:
                raise PackError ('label too long')
        keys = []
        for i in range (len (parts)):
            key = ('.'.join (parts[i:])).lower()
            keys.append (key)
            if self.index.has_key (key):
                pointer = self.index[key]
                break
        else:
            i = len (parts)
            pointer = None
        # Do it into temporaries first so exceptions don't
        # mess up self.index and self.buf
        buf = buffer()
        new_keys = []
        for j in range(i):
            label = parts[j]
            n = len (label)
            if self.buf.offset + buf.offset < 0x3FFF:
                new_keys.append ((keys[j], self.buf.offset + buf.offset))
            buf.add_byte (n)
            buf.add (label)
        if pointer is not None:
            buf.add (pack16bit (pointer | 0xc000))
        else:
            buf.add (b'\0')
        self.buf.add (buf.get())
        for key, value in new_keys:
            self.index[key] = value
    cpdef addname (self, name):
        self.compressed_addname (name)
    # Question (section 4.1.2)
    cpdef addQuestion (self, qname, qtype, qclass):
        self.addname (qname)
        self.add16bit (qtype)
        self.add16bit (qclass)
    def addHeader (self, Header h):
        self.add16bit (h.id)
        self.add16bit (
            (h.qr&1)<<15 | (h.opcode&0xF)<<11 | (h.aa&1)<<10
            | (h.tc&1)<<9 | (h.rd&1)<<8 | (h.ra&1)<<7
            | (h.z&7)<<4 | (h.rcode&0xF)
            )
        self.add16bit (h.qdcount)
        self.add16bit (h.ancount)
        self.add16bit (h.nscount)
        self.add16bit (h.arcount)
    # RR toplevel format (section 3.2.1)
    cpdef addRRheader (self, bytes name, int type, int klass, int ttl):
        self.addname(name)
        self.add16bit(type)
        self.add16bit(klass)
        self.add32bit(ttl)
        self.add16bit(0)
        self.rdstart = self.buf.offset
    cpdef endRR (self):
        cdef int rdlength = self.buf.offset - self.rdstart
        self.buf.set16 (self.rdstart-2, rdlength)
    # Standard RRs (section 3.3)
    cpdef addCNAME (self, name, klass, ttl, cname):
        self.addRRheader (name, TYPE.CNAME, klass, ttl)
        self.addname (cname)
        self.endRR()
    cpdef addHINFO (self, name, klass, ttl, cpu, os):
        self.addRRheader (name, TYPE.HINFO, klass, ttl)
        self.addstring (cpu)
        self.addstring (os)
        self.endRR()
    cpdef addMX (self, name, klass, ttl, preference, exchange):
        self.addRRheader (name, TYPE.MX, klass, ttl)
        self.add16bit (preference)
        self.addname (exchange)
        self.endRR()
    cpdef addNS (self, name, klass, ttl, nsdname):
        self.addRRheader (name, TYPE.NS, klass, ttl)
        self.addname (nsdname)
        self.endRR()
    cpdef addPTR (self, name, klass, ttl, ptrdname):
        self.addRRheader (name, TYPE.PTR, klass, ttl)
        self.addname (ptrdname)
        self.endRR()
    cpdef addSOA (self, name, klass, ttl, mname, rname, serial, refresh, retry, expire, minimum):
        self.addRRheader (name, TYPE.SOA, klass, ttl)
        self.addname (mname)
        self.addname (rname)
        self.add32bit (serial)
        self.add32bit (refresh)
        self.add32bit (retry)
        self.add32bit (expire)
        self.add32bit (minimum)
        self.endRR()
    cpdef addTXT (self, name, klass, ttl, list):
        self.addRRheader (name, TYPE.TXT, klass, ttl)
        for txtdata in list:
            self.addstring (txtdata)
        self.endRR()
    # Internet specific RRs  (section 3.4) -- class = IN
    cpdef addA (self, name, ttl, address):
        self.addRRheader (name, TYPE.A, CLASS.IN, ttl)
        self.addaddr (address)
        self.endRR()

class UnpackError (Exception):
    pass

import sys
W = sys.stderr.write

cdef class Unpacker:
    cdef bytes buf
    cdef uint32_t offset
    cdef uint32_t length
    cdef uint32_t rdend
    def __init__ (self, bytes buf):
        self.buf = buf
        self.offset = 0
        self.length = len (self.buf)
    cpdef unsigned char getbyte (self):
        cdef unsigned char * buf = self.buf
        c = buf[self.offset]
        self.offset += 1
        return c
    cdef unsigned char * get_pointer (self, uint32_t n) except NULL:
        cdef unsigned char * p = self.buf
        self.ensure (n)
        return p + self.offset
    cpdef bytes getbytes (self, uint32_t n):
        cdef bytes s
        self.ensure (n)
        s = self.buf[self.offset : self.offset + n]
        self.offset += n
        return s
    cpdef ensure (self, uint32_t n):
        if self.offset + n > self.length:
            raise UnpackError ('not enough data left %d+%d > %d' % (n, self.offset, self.length))
    cpdef get16bit (self):
        r = unpack16bit (self.get_pointer (2))
        self.offset += 2
        return r
    cpdef get32bit (self):
        r = unpack32bit (self.get_pointer (4))
        self.offset += 4
        return r
    cpdef getaddr (self):
        return bin2addr (self.get32bit())
    cpdef getstring (self):
        return self.getbytes (self.getbyte())
    cpdef getname (self):
        # Domain name unpacking (section 4.1.4)
        cdef uint32_t i = self.getbyte()
        cdef uint32_t j = 0
        cdef uint32_t pointer = 0
        if i & 0xC0 == 0xC0:
            j = self.getbyte()
            pointer = ((i<<8) | j) & ~0xC000
            save_offset = self.offset
            try:
                self.offset = pointer
                domain = self.getname()
            finally:
                self.offset = save_offset
            return domain
        if i == 0:
            return ''
        else:
            domain = self.getbytes(i)
            remains = self.getname()
            if not remains:
                return domain.lower()
            else:
                return (domain + '.' + remains).lower()
    def getHeader (self):
        cdef uint16_t flags
        h = Header()
        h.id     = self.get16bit()
        flags    = self.get16bit()
        h.qr     = (flags>>15)&1
        h.opcode = (flags>>11)&0xF
        h.aa     = (flags>>10)&1
        h.tc     = (flags>>9)&1
        h.rd     = (flags>>8)&1
        h.ra     = (flags>>7)&1
        h.z      = (flags>>4)&7
        h.rcode  = (flags>>0)&0xF
        h.qdcount  = self.get16bit()
        h.ancount  = self.get16bit()
        h.nscount  = self.get16bit()
        h.arcount  = self.get16bit()
        return h
    # resource records
    cpdef getRRheader(self):
        rname = self.getname()
        rtype = self.get16bit()
        rclass = self.get16bit()
        ttl = self.get32bit()
        rdlength = self.get16bit()
        self.rdend = self.offset + rdlength
        return (rname, rtype, rclass, ttl, rdlength)
    cpdef getCNAMEdata(self):
        return self.getname()
    cpdef getHINFOdata(self):
        return (
            self.getstring(),
            self.getstring()
            )
    cpdef getMXdata(self):
        return self.get16bit(), self.getname()
    cpdef getNSdata(self):
        return self.getname()
    cpdef getPTRdata(self):
        return self.getname()
    cpdef getSOAdata(self):
        return (
            self.getname(),
            self.getname(), 
            self.get32bit(),
            self.get32bit(),
            self.get32bit(),
            self.get32bit(),
            self.get32bit()
            )
    cpdef getTXTdata(self):
        cdef list parts = []
        while self.offset != self.rdend:
            parts.append (self.getstring())
        return parts
    # XXX replace this with inet_ntop
    cpdef getAdata(self):
        return self.getaddr()
    cpdef getAAAAdata (self):
        return socket.inet_ntop (socket.AF_INET6, self.getbytes (16))
    # Question (section 4.1.2)    
    cpdef getQuestion (self):
        return self.getname(), self.get16bit(), self.get16bit()
    # ---------------
    cpdef getRR (self):
        rname, rtype, rclass, ttl, rdlength = self.getRRheader()
        if rtype == TYPE.CNAME:
            data = self.getCNAMEdata()
        elif rtype == TYPE.MX:
            data = self.getMXdata()
        elif rtype == TYPE.NS:
            data = self.getNSdata()
        elif rtype == TYPE.PTR:
            data = self.getPTRdata()
        elif rtype == TYPE.SOA:
            data = self.getSOAdata()
        elif rtype == TYPE.TXT:
            data = self.getTXTdata()
        elif rtype == TYPE.A:
            data = self.getAdata()
        elif rtype == TYPE.AAAA:
            data = self.getAAAAdata()
        elif rtype == TYPE.HINFO:
            data = self.getHINFOdata()
        else:
            data = self.getbytes (rdlength)
        if self.offset != self.rdend:
            raise UnpackError ('end of RR not reached')
        else:
            rtype = TYPE_MAP.get (rtype, rtype)
            rclass = CLASS_MAP.get (rclass, rclass)
            return rname, rtype, rclass, ttl, data
    def unpack (self):
        h = self.getHeader()
        qdl = []
        for i in range (h.qdcount):
            qdl.append (self.getQuestion())
        anl = []
        for i in range (h.ancount):
            anl.append (self.getRR())
        nsl = []
        for i in range (h.nscount):
            nsl.append (self.getRR())
        arl = []
        for i in range (h.arcount):
            arl.append (self.getRR())
        return h, qdl, anl, nsl, arl

# minimal dfa to accept "($|(a+(.a+)*)$)":
# ([[('$', 3), ('a', 1)],
#  [('.', 2), ('$', 3), ('a', 1)],
#  [('a', 1)]
#  []],
#  [3])
# yes, I'm sure this could have been done more simply.
# this way I don't have to think.

def dot_sane (bytes s):
    cdef char * s0 = s
    cdef char ch
    cdef int i = 0
    cdef int state = 0
    # we use the NUL terminator in the machine
    for i in range (len (s) + 1):
        ch = s0[i]
        if state == 0:
            if ch == b'\000':
                return True
            elif ch == b'.':
                return False
            else:
                state = 1
        elif state == 1:
            if ch == b'\000':
                return True
            elif ch == b'.':
                state = 2
            else:
                state = 1
        elif state == 2:
            if ch == b'\000':
                return False
            elif ch == '.':
                return False
            else:
                state = 1
    # unreachable
    return False
        
    
