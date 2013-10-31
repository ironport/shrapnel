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
# ssh.keys.static_key_storage
#
# This module is a key storage type where they keys are retained in memory.
#

import os

import key_storage
import remote_host
import openssh_key_storage

class Static_Key_Storage(key_storage.SSH_Key_Storage):

    """Static_Key_Storage

    A key storage mechanism where all keys are maintained in memory.

    Note that this isn't terribly secure.
    """

    key_types = ('dsa', 'rsa')

    def __init__(self):
        # The key is the username, the value is the key object.
        self.public_key = {}
        self.private_key = {}
        # List of (hosts, (SSH_Public_Private_Key,...)) where hosts is a list of strings.
        # Does not support any fancy meta-matching, sorry.
        # Does not support user-specific known hosts.
        self.known_hosts = []

    def set_private_host_key(self, username, key_obj):
        self.private_key[username] = key_obj

    def set_public_host_key(self, username, key_obj):
        self.public_key[username] = key_obj

    def add_known_hosts(self, hosts, keystrings):
        """add_known_hosts(self, hosts, keystrings) -> None
        Add a known host.

        <hosts>: List of host strings.
        <keystrings>: List of strings of the host's public key.
                      Must be in OpenSSH's standard format.
        """
        key_storage = openssh_key_storage.OpenSSH_Key_Storage
        key_objs = []
        for keystring in keystrings:
            key_obj = key_storage.parse_public_key(keystring)
            key_objs.append(key_obj)
        # XXX: Could merge host entries.
        self.known_hosts.append((hosts, key_objs))

    def load_keys(self, username=None):
        if not self.public_key.has_key(username) or not self.private_key.has_key(username):
            return None
        if username is None:
            username = os.getlogin()
        key_obj = self.private_key[username]
        public_key = self.public_key[username]
        key_obj.public_key = public_key.public_key
        return [key_obj]

    load_keys.__doc__ = key_storage.SSH_Key_Storage.load_keys.__doc__

    def load_private_keys(self, username=None):
        if not self.private_key.has_key(username):
            return []
        if username is None:
            username = os.getlogin()
        return [self.private_key[username]]

    load_private_keys.__doc__ = key_storage.SSH_Key_Storage.load_private_keys.__doc__

    def load_public_keys(self, username=None):
        if not self.public_key.has_key(username):
            return []
        if username is None:
            username = os.getlogin()
        return [self.public_key[username]]

    load_public_keys.__doc__ = key_storage.SSH_Key_Storage.load_public_keys.__doc__

    def verify(self, host_id, server_key_types, public_host_key, username=None):
        if username is None:
            username = os.getlogin()
        for key in server_key_types:
            if public_host_key.name == key.name:
                # This is a supported key type.
                if self._verify_contains(host_id, public_host_key, username):
                    return 1
        return 0

    verify.__doc__ = key_storage.SSH_Key_Storage.verify.__doc__

    def _verify_contains(self, host_id, public_host_key, username):
        __pychecker__ = 'unusednames=username'
        # Currently only supported IPv4
        if not isinstance(host_id, remote_host.IPv4_Remote_Host_ID):
            return 0
        for hosts, key_objs in self.known_hosts:
            for key_obj in key_objs:
                if key_obj.name == public_host_key.name:
                    for host in hosts:
                        if host == host_id.ip or host == host_id.hostname:
                            if key_obj.public_key == public_host_key.public_key:
                                return 1
        return 0

    def update_known_hosts(self, host, public_host_key, username=None):
        __pychecker__ = 'unusednames=username'
        self.known_hosts.append(([host], public_host_key))

    update_known_hosts.__doc__ = key_storage.SSH_Key_Storage.update_known_hosts.__doc__
