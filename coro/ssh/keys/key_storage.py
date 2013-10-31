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
# ssh.keys.key_storage
#
# This module loads and saves various types of SSH public/private keys.
#

class Invalid_Server_Public_Host_Key(Exception):

    """Invalid_Server_Public_Host_Key(host_id, public_host_key)
    This exception is raised when we have no knowledge of the server's
    public key.  Normally what happens is the user is asked if the fingerprint
    of the public key is OK.

    <host_id>: A Remote_Host_ID instance.
    <public_host_key>: A SSH_Public_Private_Key instance.
    """

    def __init__(self, host_id, public_host_key):
        self.host_id = host_id
        self.public_host_key = public_host_key
        Exception.__init__(self, host_id, public_host_key)

    def __str__(self):
        return '<Invalid_Server_Public_host_Key host_id=%s>' % self.host_id

# XXX: include the filename and line number of the conflict.
class Host_Key_Changed_Error(Exception):

    """Host_Key_Changed_Error(host_id, location)
    This exception is raised when the server's public host key does not match
    our database.

    <host_id>: A Remote_Host_ID instance
    <location>: A string to direct the user to how to find the offending key
                in their local database.  May be the empty string if it is
                not relevant.
    """

    def __init__(self, host_id, location):
        self.host_id = host_id
        self.location = location
        Exception.__init__(self, host_id, location)

    def __str__(self):
        return '<Host_Key_Changed_Error host_id=%s location=%s>' % (self.host_id, self.location)

class SSH_Key_Storage:

    def load_keys(self, username=None, **kwargs):
        """load_keys(self, username=None, **kwargs) -> [private_public_key_obj, ...]
        Loads the public and private keys.

        <username> defaults to the current user.

        Different key storage classes take different arguments.

        Returns a list of SSH_Public_Private_Key objects.
        Returns an empty list if the key is not available.
        """
        raise NotImplementedError

    def load_private_keys(self, username=None, **kwargs):
        """load_private_keys(self, username=None, **kwargs) -> [private_key_obj, ...]
        Loads the private keys.

        <username> defaults to the current user.

        Different key storage classes take different arguments.

        Returns a list of SSH_Public_Private_Key objects.
        Returns an empty list if the key is not available.
        """
        raise NotImplementedError

    def load_public_keys(self, username=None, **kwargs):
        """load_public_keys(self, username=None, **kwargs) -> [public_key_obj, ...]
        Loads the public keys.

        <username> defaults to the current user.

        Different key storage classes take different arguments.

        Returns a list of SSH_Public_Private_Key objects.
        Returns an empty list if the key is not available.
        """
        raise NotImplementedError

    def verify(self, host_id, server_key_types, public_host_key, username=None):
        """verify(self, host_id, server_key_types, public_host_key) -> boolean
        This verifies that the given public host key is known.
        Returns true if it is OK.

        <username>: defaults to the current user.
        <server_key_types>: A list of SSH_Public_Private_Key objects that we support.
        <public_host_key>: A SSH_Public_Private_Key instance.
        <host_id>: Remote_Host_ID instance.
        """
        raise NotImplementedError

    def update_known_hosts(self, host, public_host_key, username=None):
        """update_known_hosts(self, host, public_host_key, username=None) -> None
        Updates the known hosts database for the given user.

        <host>: The host string.
        <public_host_key>: A SSH_Public_Private_Key instance.
        <username>: Defaults to the current user.
        """
        raise NotImplementedError
