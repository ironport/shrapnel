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
# ssh.keys
#
# This implements the interface to parse and use various different key types.
#

from coro.ssh.util import packet
import dss
import rsa

# Map of supported key types.
keytypes = {
    'ssh-dss': dss.SSH_DSS,
    'ssh-rsa': rsa.SSH_RSA,
}

class Unknown_Key_Type(Exception):

    def __init__(self, keytype):
        self.keytype = keytype
        Exception.__init__(self, keytype)

    def __str__(self):
        return '<Unknown_Key_Type: %r>' % self.keytype

def parse_public_key(public_key):
    """parse_public_key(public_key) -> SSH_Public_Private_Key instance
    This takes a public key and generates an SSH_Public_Private_Key instance.

    <public_key>: A packed public key.  The format should be a packed string
                  with the first value being a string to identify the type.
    """
    data, offset = packet.unpack_payload_get_offset((packet.STRING,), public_key)
    keytype = data[0]
    if not keytypes.has_key(keytype):
        raise Unknown_Key_Type(keytype)

    key_obj = keytypes[keytype]()
    key_obj.set_public_key(public_key)
    return key_obj
