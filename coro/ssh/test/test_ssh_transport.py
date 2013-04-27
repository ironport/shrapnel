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

#
# test_ssh_transport
#
# Test routines for ssh_transport.
#
# Broken into a separate file because it's quite large.
#

import coro.ssh.l4_transport
import coro.ssh.util.packet
import coro.ssh.transport
import coro.ssh.key_exchange
import coro.ssh.transport.transport
import coro.ssh.transport.client
from coro.ssh.keys.public_private_key import SSH_Public_Private_Key
from coro.ssh.transport.transport import One_Way_SSH_Transport
from coro.ssh.transport.constants import *

import unittest

class ssh_transport_test_case(unittest.TestCase):
    pass

class Null_Transport(coro.ssh.l4_transport.Transport):

    def connect(self):
        return

    def read(self, bytes):
        return ''

    def write(self, data):
        return len(data)

    def read_line(self):
        return ''

    def close(self):
        return

    def get_host_id(self):
        return None

class kexinit_test_case(ssh_transport_test_case):

    def runTest(self):
        # Simple Test

        # Can't instantiate SSH_Transport directly.
        a = coro.ssh.transport.client.SSH_Client_Transport()
        a.transport = Null_Transport()
        # Prepare kexinit packet.
        a._send_kexinit()
        # Create a fake packet.
        fake_kexinit_packet = coro.ssh.util.packet.pack_payload(
                coro.ssh.util.packet.PAYLOAD_MSG_KEXINIT, (
                    SSH_MSG_KEXINIT,
                    'A'*16, # cookie
                    ['diffie-hellman-group1-sha1'],
                    ['ssh-dss'],
                    ['3des-cbc'],
                    ['3des-cbc'],
                    ['hmac-sha1'],
                    ['hmac-sha1'],
                    ['none'],
                    ['none'],
                    [],
                    [],
                    0,  # first_kex_packet_follows
                    0   # reserved
                    )
                   )
        a.msg_kexinit(fake_kexinit_packet)
        # Set preferred algorithms.
        a.send_newkeys()
        # Make sure algorithms were set properly.
        self.assertEqual(a.key_exchange.name, 'diffie-hellman-group1-sha1')
        self.assertEqual(a.server_key.name, 'ssh-dss')
        self.assertEqual(a.c2s.cipher.name, '3des-cbc')
        self.assertEqual(a.s2c.cipher.name, '3des-cbc')
        self.assertEqual(a.c2s.mac.name, 'hmac-sha1')
        self.assertEqual(a.s2c.mac.name, 'hmac-sha1')
        self.assertEqual(a.c2s.compression.name, 'none')
        self.assertEqual(a.s2c.compression.name, 'none')

        # Complex Test 1
        a = ssh_client.SSH_Client_Transport()
        a.transport = Null_Transport()
        # Prepare kexinit packet.
        a._send_kexinit()
        # Create a fake packet.
        fake_kexinit_packet = coro.ssh.util.packet.pack_payload(
                coro.ssh.util.packet.PAYLOAD_MSG_KEXINIT, (
                    SSH_MSG_KEXINIT,
                    'A'*16, # cookie
                    ['foobar', 'diffie-hellman-group1-sha1'],
                    ['fake-server-key-type', 'ssh-dss'],
                    ['encrypt-this', '3des-cbc'],
                    ['xor', '3des-cbc'],
                    ['none', 'hmac-sha1'],
                    ['mac-daddy', 'hmac-sha1'],
                    ['zzz', 'none'],
                    ['aaa', 'none'],
                    ['pig-latin'],
                    [],
                    0,  # first_kex_packet_follows
                    0   # reserved
                    )
                   )
        a.msg_kexinit(fake_kexinit_packet)
        # Set preferred algorithms.
        a.send_newkeys()
        # Make sure algorithms were set properly.
        self.assertEqual(a.key_exchange.name, 'diffie-hellman-group1-sha1')
        self.assertEqual(a.server_key.name, 'ssh-dss')
        self.assertEqual(a.c2s.cipher.name, '3des-cbc')
        self.assertEqual(a.s2c.cipher.name, '3des-cbc')
        self.assertEqual(a.c2s.mac.name, 'hmac-sha1')
        self.assertEqual(a.s2c.mac.name, 'hmac-sha1')
        self.assertEqual(a.c2s.compression.name, 'none')
        self.assertEqual(a.s2c.compression.name, 'none')

        # Complex Test 2
        class funky_one_way(One_Way_SSH_Transport):
            def __init__(self, transport):
                self.supported_macs.reverse()
                One_Way_SSH_Transport.__init__(self, transport)
        a = ssh_client.SSH_Client_Transport(client_transport = funky_one_way())
        a.transport = Null_Transport()
        # Prepare kexinit packet.
        a._send_kexinit()
        # Create a fake packet.
        fake_kexinit_packet = coro.ssh.util.packet.pack_payload(
                coro.ssh.util.packet.PAYLOAD_MSG_KEXINIT, (
                    SSH_MSG_KEXINIT,
                    'A'*16, # cookie
                    ['foobar', 'diffie-hellman-group1-sha1'],
                    ['fake-server-key-type', 'ssh-dss'],
                    ['encrypt-this', '3des-cbc'],
                    ['xor', '3des-cbc'],
                    ['hmac-sha1', 'none'],
                    ['mac-daddy', 'hmac-sha1'],
                    ['zzz', 'none'],
                    ['aaa', 'none'],
                    ['pig-latin'],
                    [],
                    0,  # first_kex_packet_follows
                    0   # reserved
                    )
                   )
        a.msg_kexinit(fake_kexinit_packet)
        # Set preferred algorithms.
        a.send_newkeys()
        # Make sure algorithms were set properly.
        self.assertEqual(a.key_exchange.name, 'diffie-hellman-group1-sha1')
        self.assertEqual(a.server_key.name, 'ssh-dss')
        self.assertEqual(a.c2s.cipher.name, '3des-cbc')
        self.assertEqual(a.s2c.cipher.name, '3des-cbc')
        self.assertEqual(a.c2s.mac.name, 'none')
        self.assertEqual(a.s2c.mac.name, 'hmac-sha1')
        self.assertEqual(a.c2s.compression.name, 'none')
        self.assertEqual(a.s2c.compression.name, 'none')

        # Mismatch Test1
        class bogus_ssh_server_key(SSH_Public_Private_Key):
            supports_signature = 0
            supports_encryption = 0
            name = 'bogus'

        class funky_one_way2(One_Way_SSH_Transport):
            supported_server_keys = [bogus_ssh_server_key]

        a = ssh_client.SSH_Client_Transport(client_transport = funky_one_way2())
        a.transport = Null_Transport()
        # Prepare kexinit packet.
        a._send_kexinit()
        # Create a fake packet.
        fake_kexinit_packet = coro.ssh.util.packet.pack_payload(
                coro.ssh.util.packet.PAYLOAD_MSG_KEXINIT, (
                    SSH_MSG_KEXINIT,
                    'A'*16, # cookie
                    ['foobar', 'diffie-hellman-group1-sha1'],
                    ['fake-server-key-type', 'ssh-dss'],
                    ['encrypt-this', '3des-cbc'],
                    ['xor', '3des-cbc'],
                    ['hmac-sha1', 'none'],
                    ['mac-daddy', 'hmac-sha1'],
                    ['zzz', 'none'],
                    ['aaa', 'none'],
                    ['pig-latin'],
                    [],
                    0,  # first_kex_packet_follows
                    0   # reserved
                    )
                   )
        self.assertRaises(coro.ssh.transport.SSH_Protocol_Error, a.msg_kexinit, fake_kexinit_packet)

        # Mismatch Test2
        self.test_matchup_kex_and_key(['one', 'two'],
                                      ['two', 'one'],
                                      ['a', 'b'],
                                      ['b', 'c'],
                                      {'one': {'wants_enc': 1,
                                               'wants_sig': 1},
                                       'two': {'wants_enc': 1,
                                               'wants_sig': 1},
                                      },
                                      {'a': {'enc': 0,
                                             'sig': 1},
                                       'b': {'enc': 1,
                                             'sig': 0},
                                       'c': {'enc': 1,
                                             'sig': 1}
                                      },
                                      1,    # Expects exception.
                                      None, None)

    def test_matchup_kex_and_key(self, c2s_kex_supported, s2c_kex_supported,
                                       c2s_key_supported, s2c_key_supported,
                                       kex_features, key_features,
                                       expected_exception,
                                       expected_kex,
                                       expected_key):
        import new
        c2s_kex = []
        for kex in c2s_kex_supported:
            f = new.classobj(kex, (coro.ssh.key_exchange.SSH_Key_Exchange,), {})
            f.name = kex
            f.wants_signature_host_key = kex_features[kex]['wants_sig']
            f.wants_encryption_host_key = kex_features[kex]['wants_enc']
            c2s_kex.append(f)
        s2c_kex = []
        for kex in s2c_kex_supported:
            f = new.classobj(kex, (coro.ssh.key_exchange.SSH_Key_Exchange,), {})
            f.name = kex
            f.wants_signature_host_key = kex_features[kex]['wants_sig']
            f.wants_encryption_host_key = kex_features[kex]['wants_enc']
            s2c_kex.append(f)
        c2s_key = []
        for key in c2s_key_supported:
            k = new.classobj(key, (SSH_Public_Private_Key,), {})
            k.name = key
            k.supports_signature = key_features[key]['sig']
            k.supports_encryption = key_features[key]['enc']
            c2s_key.append(k)
        s2c_key = []
        for key in s2c_key_supported:
            k = new.classobj(key, (SSH_Public_Private_Key,), {})
            k.name = key
            k.supports_signature = key_features[key]['sig']
            k.supports_encryption = key_features[key]['enc']
            s2c_key.append(k)

        class client_transport(One_Way_SSH_Transport):
            supported_key_exchanges = c2s_kex
            supported_server_keys = c2s_key

        class server_transport(One_Way_SSH_Transport):
            supported_key_exchanges = s2c_key
            supported_server_keys = s2c_key

        import ssh_client
        a = ssh_client.SSH_Client_Transport(client_transport=client_transport(), server_transport=server_transport())
        a.transport = Null_Transport()
        # Prepare kexinit packet.
        a._send_kexinit()
        # Create a fake packet.
        fake_kexinit_packet = coro.ssh.util.packet.pack_payload(
                coro.ssh.util.packet.PAYLOAD_MSG_KEXINIT, (
                    SSH_MSG_KEXINIT,
                    'A'*16, # cookie
                    s2c_kex_supported,
                    s2c_key_supported,
                    ['3des-cbc'],
                    ['3des-cbc'],
                    ['hmac-sha1'],
                    ['hmac-sha1'],
                    ['none'],
                    ['none'],
                    [],
                    [],
                    0,  # first_kex_packet_follows
                    0   # reserved
                    )
                   )
        if expected_exception:
            self.assertRaises(coro.ssh.transport.SSH_Protocol_Error, a.msg_kexinit, fake_kexinit_packet)
        else:
            a.msg_kexinit(fake_kexinit_packet)
            # Set preferred algorithms.
            a.send_newkeys()
            # Make sure algorithms were set properly.
            self.assertEqual(a.key_exchange.name, expected_kex)
            self.assertEqual(a.server_key.name, expected_key)

def suite():
    suite = unittest.TestSuite()
    suite.addTest(kexinit_test_case())
    return suite

if __name__ == '__main__':
    unittest.main(module='test_ssh_transport', defaultTest='suite')
