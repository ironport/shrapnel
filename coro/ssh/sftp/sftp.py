# -*- Mode: Python -*-

import struct

# there are later drafts, but are they implemented?
# http://tools.ietf.org/html/draft-ietf-secsh-filexfer-02

class FXP:
    INIT           = 1
    VERSION        = 2
    OPEN           = 3
    CLOSE          = 4
    READ           = 5
    WRITE          = 6
    LSTAT          = 7
    FSTAT          = 8
    SETSTAT        = 9
    FSETSTAT       = 10
    OPENDIR        = 11
    READDIR        = 12
    REMOVE         = 13
    MKDIR          = 14
    RMDIR          = 15
    REALPATH       = 16
    STAT           = 17
    RENAME         = 18
    READLINK       = 19
    SYMLINK        = 20
    STATUS         = 101
    HANDLE         = 102
    DATA           = 103
    NAME           = 104
    ATTRS          = 105
    EXTENDED       = 200
    EXTENDED_REPLY = 201

class FLAGS:
    READ   = 0x00000001
    WRITE  = 0x00000002
    APPEND = 0x00000004
    CREAT  = 0x00000008
    TRUNC  = 0x00000010
    EXCL   = 0x00000020

class ATTRS:
    SIZE        = 0x00000001
    UIDGID      = 0x00000002
    PERMISSIONS = 0x00000004
    ACMODTIME   = 0x00000008
    EXTENDED    = 0x80000000

FXP_VERSION = 3

class Error (Exception):
    pass

class Unpacker:

    def __init__ (self, data, pos=0):
        self.pos = pos
        self.data = data

    def done (self):
        return self.pos >= len (self.data)

    def get_uint32 (self):
        val = struct.unpack ('>I', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return val

    def get_uint64 (self):
        val = struct.unpack ('>Q', self.data[self.pos:self.pos+8])[0]
        self.pos += 8
        return val

    def get_bytes (self, n):
        val = self.data[self.pos:self.pos+n]
        self.pos += n
        return val

    def get_string (self):
        slen = self.get_uint32()
        r = self.get_bytes (slen)
        assert (len(r) == slen)
        return r

class Packer:

    def __init__ (self, ptype):
        self.data = [ptype.to_bytes (1, 'big')]

    def done (self):
        return b''.join (self.data)

    def add_byte (self, n):
        self.data.append (n.to_bytes (1, signed=True))

    def add_uint32 (self, n):
        self.data.append (n.to_bytes (4, 'big'))

    def add_uint64 (self, n):
        self.data.append (n.to_bytes (8, 'big'))

    def add_int64 (self, n):
        self.data.append (n.to_bytes (8, 'big', signed=True))

    def add_string (self, s):
        if type(s) is str:
            s = s.encode()
        self.add_uint32 (len (s))
        self.data.append (s)

class Status:
    def __init__ (self, u):
        self.code = u.get_uint32()
        self.msg  = u.get_string()
        self.lang = u.get_string()
        assert (u.done())
    def __repr__ (self):
        return '<sftp status %d %s>' % (self.code, self.msg)

class FileAttributes:

    # possible attributes (see use of <flags> in Client.unpack_attrs())
    # size        : uint64
    # uid         : uint32
    # gid         : uint32
    # permissions : uint32
    # atime       : uint32
    # mtime       : uint32
    # extended    : list of (k:str, v:str) pairs

    def __init__ (self, **attrs):
        for k, v in attrs.items():
            setattr (self, k, v)

    def __repr__ (self):
        return '<attrs %r>' % (self.__dict__)

# TODO: this is a synchronous client: it sends a request and expects a
#  reply in order.  The better way is to decouple the incoming and
#  outgoing packets, allowing for multiplexed/parallel/out-of-order
#  operation.  [parallel operation can be achieved with this code by
#  opening multiple sftp channels].

class Client:

    def __init__ (self, conn):
        self.counter = 0
        self.conn = conn
        p = Packer (FXP.INIT)
        p.add_uint32 (FXP_VERSION)
        self.send_packet (p)
        ptype, data = self.read_packet()
        self.unpack_server_init (data)

    def next_request_id (self):
        val = self.counter
        self.counter += 1
        return val

    def unpack_server_init (self, data):
        u = Unpacker (data)
        self.server_version = u.get_uint32()
        r = []
        while not u.done():
            k = u.get_string()
            v = u.get_string()
            r.append ((k,v))
        self.server_extensions = r

    def send_packet (self, p):
        data = p.done()
        self.conn.send (struct.pack ('>I', len(data)) + data)

    def read_packet (self):
        h = self.conn.read_exact (5)
        length, ptype = struct.unpack ('>IB', h)
        data = self.conn.read_exact (length - 1)
        return ptype, data

    def get_reply (self, rid0):
        ptype, data = self.read_packet()
        u = Unpacker (data)
        rid1 = u.get_uint32()
        if rid0 != rid1:
            raise SyncError ((rid0, rid1))
        else:
            return ptype, u

    def get_status_reply (self, rid0):
        ptype, u = self.get_reply (rid0)
        s = Status (u)
        if s.code != 0:
            raise Error (s)
        else:
            return s

    def unpack_attrs (self, u):
        flags = u.get_uint32()
        r = FileAttributes()
        if flags & ATTRS.SIZE:
            r.size = u.get_uint64()
        if flags & ATTRS.UIDGID:
            r.uid = u.get_uint32()
            r.gid = u.get_uint32()
        if flags & ATTRS.PERMISSIONS:
            r.permissions = u.get_uint32()
        if flags & ATTRS.ACMODTIME:
            r.atime = u.get_uint32()
            r.mtime = u.get_uint32()
        if flags & ATTRS.EXTENDED:
            x = []
            count = u.get_uint32()
            for i in range (count):
                k = u.get_string()
                v = u.get_string()
                x.append ((k, v))
            r.extended = x
        return r

    def pack_attrs (self, p, attrs):
        flags = 0
        if hasattr (attrs, 'size'):
            flags |= ATTRS.SIZE
        if hasattr (attrs, 'uid'):
            flags |= ATTRS.UIDGID
        if hasattr (attrs, 'permissions'):
            flags |= ATTRS.PERMISSIONS
        if hasattr (attrs, 'atime'):
            flags |= ATTRS.ACMODTIME
        if hasattr (attrs, 'extended'):
            flags |= ATTRS.EXTENDED
        p.add_uint32 (flags)
        if hasattr (attrs, 'size'):
            p.add_uint64 (attrs.size)
        if hasattr (attrs, 'uid'):
            p.add_uint32 (attrs.uid)
            p.add_uint32 (attrs.gid)
        if hasattr (attrs, 'permissions'):
            p.add_uint32 (attrs.permissions)
        if hasattr (attrs, 'atime'):
            p.add_uint32 (attrs.atime)
            p.add_uint32 (attrs.mtime)
        if hasattr (attrs, 'extended'):
            e = attrs.extended
            p.add_uint32 (len(e))
            for k, v in e:
                p.add_string (k)
                p.add_string (v)

    def unpack_name (self, u):
        count = u.get_uint32()
        r = []
        for i in range (count):
            filename = u.get_string()
            longname = u.get_string()
            attrs = self.unpack_attrs (u)
            r.append ((filename, longname, attrs))
        return r

    def stat (self, path):
        p = Packer (FXP.STAT)
        rid0 = self.next_request_id()
        p.add_uint32 (rid0)
        p.add_string (path)
        self.send_packet (p)
        ptype, u = self.get_reply (rid0)
        if ptype == FXP.ATTRS:
            return self.unpack_attrs (u)
        elif ptype == FXP.STATUS:
            raise Error (Status (u))
        else:
            raise Error ("unexpected ptype %d" % (ptype,))

    def open (self, path, pflags, **attrs):
        p = Packer (FXP.OPEN)
        rid0 = self.next_request_id()
        p.add_uint32 (rid0)
        p.add_string (path)
        p.add_uint32 (pflags)
        if len(attrs):
            raise NotImplementedError
        p.add_uint32 (0) # no attr flags
        self.send_packet (p)
        ptype, u = self.get_reply (rid0)
        if ptype == FXP.HANDLE:
            handle = u.get_string()
            return handle
        elif ptype == FXP.STATUS:
            raise Error (Status (u))
        else:
            raise Error ("unexpected ptype %d" % (ptype,))

    def read (self, handle, offset, nbytes):
        p = Packer (FXP.READ)
        rid0 = self.next_request_id()
        p.add_uint32 (rid0)
        p.add_string (handle)
        p.add_uint64 (offset)
        p.add_uint32 (nbytes)
        self.send_packet (p)
        ptype, u = self.get_reply (rid0)
        if ptype == FXP.DATA:
            return u.get_string()
        elif ptype == FXP.STATUS:
            s = Status (u)
            if s.code == 1:
                return ''
            else:
                raise Error (s)
        else:
            raise Error ("unexpected ptype %d" % (ptype,))

    def write (self, handle, offset, data):
        p = Packer (FXP.WRITE)
        rid0 = self.next_request_id()
        p.add_uint32 (rid0)
        p.add_string (handle)
        p.add_uint64 (offset)
        p.add_string (data)
        self.send_packet (p)
        return self.get_status_reply (rid0)

    def close (self, handle):
        p = Packer (FXP.CLOSE)
        rid0 = self.next_request_id()
        p.add_uint32 (rid0)
        p.add_string (handle)
        self.send_packet (p)
        return self.get_status_reply (rid0)

    def opendir (self, path):
        p = Packer (FXP.OPENDIR)
        rid0 = self.next_request_id()
        p.add_uint32 (rid0)
        p.add_string (path)
        self.send_packet (p)
        ptype, u = self.get_reply (rid0)
        if ptype == FXP.HANDLE:
            handle = u.get_string()
            return handle
        elif ptype == FXP.STATUS:
            raise Error (Status (u))
        else:
            raise Error ("unexpected ptype %d" % (ptype,))

    def readdir (self, handle):
        p = Packer (FXP.READDIR)
        rid0 = self.next_request_id()
        p.add_uint32 (rid0)
        p.add_string (handle)
        self.send_packet (p)
        ptype, u = self.get_reply (rid0)
        if ptype == FXP.NAME:
            return self.unpack_name (u)
        elif ptype == FXP.STATUS:
            raise Error (Status (u))
        else:
            raise Error ("unexpected ptype %d" % (ptype,))

    def mkdir (self, path, **attrs):
        p = Packer (FXP.MKDIR)
        rid0 = self.next_request_id()
        p.add_uint32 (rid0)
        p.add_string (path)
        self.pack_attrs (p, FileAttributes (**attrs))
        self.send_packet (p)
        return self.get_status_reply (rid0)

    def rmdir (self, path):
        p = Packer (FXP.RMDIR)
        rid0 = self.next_request_id()
        p.add_uint32 (rid0)
        p.add_string (path)
        self.send_packet (p)
        return self.get_status_reply (rid0)

    def remove (self, path):
        p = Packer (FXP.REMOVE)
        rid0 = self.next_request_id()
        p.add_uint32 (rid0)
        p.add_string (path)
        self.send_packet (p)
        return self.get_status_reply (rid0)

    def rename (self, oldpath, newpath):
        p = Packer (FXP.RENAME)
        rid0 = self.next_request_id()
        p.add_uint32 (rid0)
        p.add_string (oldpath)
        p.add_string (newpath)
        self.send_packet (p)
        return self.get_status_reply (rid0)

    def readlink (self, path):
        p = Packer (FXP.READLINK)
        rid0 = self.next_request_id()
        p.add_uint32 (rid0)
        p.add_string (path)
        self.send_packet (p)
        ptype, u = self.get_reply (rid0)
        if ptype == FXP.NAME:
            return self.unpack_name (u)
        elif ptype == FXP.STATUS:
            raise Error (Status (u))
        else:
            raise Error ("unexpected ptype %d" % (ptype,))
