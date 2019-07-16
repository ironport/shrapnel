# -*- Mode: Python; indent-tabs-mode: nil -*-

from coro.ssh.transport.client import SSH_Client_Transport
from coro.ssh.l4_transport.coro_socket_transport import coro_socket_transport
from coro.ssh.auth.userauth import Userauth
from coro.ssh.connection.interactive_session import Interactive_Session_Client
from coro.ssh.connection.connect import Connection_Service
from coro.ssh.keys import key_storage
from coro.ssh.util import packet
from coro.ssh.sftp import sftp

import sys
import coro
# avoid full-blown dns resolver
coro.set_resolver (coro.dummy_resolver())

class client:

    # this is to avoid a PTR lookup, its value is not important
    hostname = 'host'

    def __init__ (self, ip, username, port=22, key_store=None):
        self.ip = ip
        self.port = port
        self.username = username
        self.client = None
        self.service = None
        self.channel = None
        self.key_store = key_store

    def open (self):
        self.client = SSH_Client_Transport()
        transport = coro_socket_transport (self.ip, port=self.port, hostname=self.hostname)
        if self.key_store:
            self.client.supported_key_storages = [self.key_store]
        self.client.connect (transport)
        auth_method = Userauth (self.client, self.username)
        auth_method.methods = [coro.ssh.auth.userauth.Publickey (auth_method.transport)]
        self.service = Connection_Service (self.client)
        self.client.authenticate (auth_method, self.service.name)

    def close (self):
        if self.channel is not None:
            self.channel.close()
            self.channel = None
        if self.client is not None:
            self.client.disconnect()
        self.client = None
        self.service = None

    def read_all (self, channel):
        while 1:
            try:
                yield channel.read (1000)
            except EOFError:
                break

    def command (self, cmd, output=sys.stdout.write):
        if self.client is None:
            self.open()
        channel = self.channel = Interactive_Session_Client (self.service)
        channel.open()
        channel.exec_command (cmd)
        for block in self.read_all (channel):
            output (block.decode ('us-ascii'))
        coro.sleep_relative (1)
        channel.close()
        self.channel = None
        return channel.exit_status

    def check_output (self, cmd):
        r = []
        self.command (cmd, r.append)
        return ''.join (r)

    # XXX create a class for an sftp channel so we can keep it open.

    def get_sftp_channel (self):
        if self.client is None:
            self.open()
        ch = self.channel = Interactive_Session_Client (self.service)
        ch.open()
        ch.send_channel_request ('subsystem', (packet.STRING,), ('sftp',))
        return ch

    def sftp_put (self, src_file, dst):
        try:
            ch = self.get_sftp_channel()
            fxp = sftp.Client (ch)
            h = fxp.open (dst, sftp.FLAGS.CREAT | sftp.FLAGS.WRITE | sftp.FLAGS.TRUNC)
            pos = 0
            while 1:
                block = src_file.read (8000)
                if not block:
                    break
                else:
                    fxp.write (h, pos, block)
                    pos += len (block)
            return pos
        finally:
            #fxp.close (h)
            ch.close()

    def sftp_get (self, src, dst_file):
        try:
            ch = self.get_sftp_channel()
            fxp = sftp.Client (ch)
            h = fxp.open (src, sftp.FLAGS.READ)
            pos = 0
            while 1:
                block = fxp.read (h, pos, 8000)
                if not block:
                    break
                else:
                    dst_file.write (block)
                    pos += len (block)
            return pos
        finally:
            fxp.close (h)
            ch.close()

    def sftp_stat (self, path):
        try:
            ch = self.get_sftp_channel()
            fxp = sftp.Client (ch)
            return fxp.stat (path)
        finally:
            ch.close()

    def sftp_listdir (self, path):
        try:
            ch = self.get_sftp_channel()
            fxp = sftp.Client (ch)
            handle = fxp.opendir (path)
            result = []
            while 1:
                try:
                    result.extend (fxp.readdir (handle))
                except sftp.Error:
                    break
            fxp.close (handle)
            return result
        finally:
            ch.close()

    def sftp_mkdir (self, path, **attrs):
        try:
            ch = self.get_sftp_channel()
            fxp = sftp.Client (ch)
            return fxp.mkdir (path, **attrs)
        finally:
            ch.close()

    def sftp_readlink (self, path):
        try:
            ch = self.get_sftp_channel()
            fxp = sftp.Client (ch)
            return fxp.readlink (path)
        finally:
            ch.close()

if __name__ == '__main__':

    from pprint import pprint as pp

    def test_sftp (ip, username):
        c = client (ip, username)
        c.open()
        c.sftp_put (open ('sftp.py', 'rb'), '/tmp/t1')
        c.sftp_get ('/tmp/t1', open ('/tmp/t2', 'wb'))
        tmp_files = c.sftp_listdir ('/tmp')
        c.close()
        for x in tmp_files:
            pp (x)
        coro.set_exit()

    def go (ip, username, cmds):
        c = client (ip, username)
        c.open()
        for cmd in cmds:
            c.command (cmd)
        c.close()
        coro.set_exit()

    import sys
    if len(sys.argv) < 3:
        sys.stderr.write ('Usage: %s <ip> <username> <cmd>\n' % (sys.argv[0],))
        sys.stderr.write ('Example: python %s 10.1.1.3 bubba "ls -l"\n' % (sys.argv[0],))
    elif '-sftp' in sys.argv:
        sys.argv.remove ('-sftp')
        ip, username = sys.argv[1:3]
        coro.spawn (test_sftp, ip, username)
    else:
        ip, username = sys.argv[1:3]
        cmds = sys.argv[3:]
        coro.spawn (go, ip, username, cmds)
    coro.event_loop()
