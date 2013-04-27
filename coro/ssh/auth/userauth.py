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

# ssh_userauth
#
# This implements the ssh-userauth service for authenticating a user.
#

import os

from coro.ssh.util import packet as ssh_packet
from coro.ssh.util import debug as ssh_debug
from coro.ssh.util.password import get_password
from coro.ssh.util import safe_string
from coro.ssh.auth import Authentication_Error, Authentication_System

class Userauth_Method_Not_Allowed_Error(Exception):
    """Userauth_Method_Not_Allowed_Error
    This is raised when it is determined that the method is not supported.
    """

    def __init__(self, auths_that_can_continue):
        Exception.__init__(self, auths_that_can_continue)
        self.auths_that_can_continue = auths_that_can_continue

class Userauth_Authentication_Method:

    """Userauth_Authentication_Method

    This is the base class for various different types of authentication
    methods supported by the userauth service.
    """

    name = ''

    def __init__(self, ssh_transport):
        self.ssh_transport = ssh_transport

    def authenticate(self, username, service_name):
        """authenticate(self, username, service_name) -> None
        Try to authenticate with the remote side.

        Raises Authentication_Error if it fails.
        """
        raise NotImplementedError

    def msg_userauth_failure(self, packet):
        self.ssh_transport.debug.write(ssh_debug.DEBUG_1, '%s Auth: Userauth failure.', (self.name,))
        msg, auths_that_can_continue, partial_success = ssh_packet.unpack_payload(PAYLOAD_MSG_USERAUTH_FAILURE, packet)
        # XXX: How to handle partial_success?
        if self.name not in auths_that_can_continue:
            self.ssh_transport.debug.write(ssh_debug.DEBUG_1, '%s Auth: Not in the list of auths that can continue', (self.name,))
            raise Userauth_Method_Not_Allowed_Error(auths_that_can_continue)

class Publickey(Userauth_Authentication_Method):
    name = 'publickey'

    def authenticate(self, username, service_name):
        local_username = os.getlogin()
        for key_storage in self.ssh_transport.supported_key_storages:
            self.ssh_transport.debug.write(ssh_debug.DEBUG_1, 'Publickey Auth: Trying to load keytype "%s" for user "%s".', (key_storage.__class__.__name__, local_username))
            loaded_keys = key_storage.load_keys(username=local_username)
            if loaded_keys:
                for loaded_key in loaded_keys:
                    # Test this key type.
                    self.ssh_transport.debug.write(ssh_debug.DEBUG_1, 'Publickey Auth: Sending PK test for keytype "%s".', (loaded_key.name,))
                    packet = ssh_packet.pack_payload(PAYLOAD_MSG_USERAUTH_REQUEST_PK_TEST,
                                        (SSH_MSG_USERAUTH_REQUEST,
                                         username,
                                         service_name,
                                         'publickey',
                                         0,
                                         loaded_key.name,
                                         loaded_key.get_public_key_blob()
                                         ))
                    self.ssh_transport.send_packet(packet)
                    message_type, packet = self.ssh_transport.receive_message((SSH_MSG_USERAUTH_PK_OK,
                                                                               SSH_MSG_USERAUTH_FAILURE,
                                                                               ))
                    if message_type == SSH_MSG_USERAUTH_PK_OK:
                        # This public key is ok to try.
                        try:
                            self._try_auth(packet, loaded_key, username, service_name)
                        except Authentication_Error:
                            # Nope, didn't work.  Loop and try next.
                            pass
                        else:
                            # Done!
                            return
                    elif message_type == SSH_MSG_USERAUTH_FAILURE:
                        # Key type not allowed.
                        self.msg_userauth_failure(packet)
                        # Loop through and try next key.
                    else:
                        # Should never happen.
                        raise ValueError, message_type
                else:
                    self.ssh_transport.debug.write(ssh_debug.DEBUG_1, 'Publickey Auth: No more key storage types left.')
            else:
                self.ssh_transport.debug.write(ssh_debug.DEBUG_1, 'Publickey Auth: No keys found of this key storage type.')
        else:
            self.ssh_transport.debug.write(ssh_debug.DEBUG_1, 'Publickey Auth: No more storage key types left to try.')
            raise Authentication_Error

    def _try_auth(self, packet, loaded_key, username, service_name):
        self.ssh_transport.debug.write(ssh_debug.DEBUG_1, 'Publickey Auth: Got OK for this key type.')
        msg, key_algorithm_name, key_blob = ssh_packet.unpack_payload(PAYLOAD_MSG_USERAUTH_PK_OK, packet)
        assert (key_algorithm_name == loaded_key.name)
        # XXX: Check key_blob, too?
        # Send the actual request.
        # Compute signature.
        session_id = self.ssh_transport.key_exchange.session_id
        sig_data = ssh_packet.pack_payload(PAYLOAD_USERAUTH_REQUEST_PK_SIGNATURE,
                                    (session_id,
                                     SSH_MSG_USERAUTH_REQUEST,
                                     username,
                                     service_name,
                                     'publickey',
                                     1,
                                     loaded_key.name,
                                     loaded_key.get_public_key_blob()
                                     ))
        signature = loaded_key.sign(sig_data)

        self.ssh_transport.debug.write(ssh_debug.DEBUG_1, 'Publickey Auth: Sending userauth request.')
        packet = ssh_packet.pack_payload(PAYLOAD_MSG_USERAUTH_REQUEST_PK,
                                (SSH_MSG_USERAUTH_REQUEST,
                                 username,
                                 service_name,
                                 'publickey',
                                 1,
                                 loaded_key.name,
                                 loaded_key.get_public_key_blob(),
                                 signature))
        self.ssh_transport.send_packet(packet)
        message_type, packet = self.ssh_transport.receive_message((SSH_MSG_USERAUTH_SUCCESS,
                                                                   SSH_MSG_USERAUTH_FAILURE))
        if message_type == SSH_MSG_USERAUTH_SUCCESS:
            # Success.
            return
        elif message_type == SSH_MSG_USERAUTH_FAILURE:
            self.msg_userauth_failure(packet)
            raise Authentication_Error
        else:
            # Should never happen.
            raise ValueError, message_type

class Password(Userauth_Authentication_Method):
    name = 'password'

    def authenticate(self, username, service_name):
        password = self.get_password(username)
        packet = ssh_packet.pack_payload(PAYLOAD_MSG_USERAUTH_REQUEST_PASSWORD,
                                (SSH_MSG_USERAUTH_REQUEST,
                                 username,
                                 service_name,
                                 'password',
                                 0,
                                 password
                                 ))
        self.ssh_transport.send_packet(packet)
        # While loop in case we get a CHANGEREQ packet.
        while 1:
            try:
                message_type, packet = self.ssh_transport.receive_message(( \
                        SSH_MSG_USERAUTH_SUCCESS,SSH_MSG_USERAUTH_FAILURE,\
                        SSH_MSG_USERAUTH_PASSWD_CHANGEREQ))
            except EOFError:
                # In case of an expired user, an EOFError is raised
                # Expired accounts are also considered as authentication errors
                raise Authentication_Error
            if message_type == SSH_MSG_USERAUTH_SUCCESS:
                # Success!
                return
            elif message_type == SSH_MSG_USERAUTH_FAILURE:
                self.msg_userauth_failure(packet)
                # XXX: Could ask for user's password again?
                # XXX: Should handle partial_success flag for CHANGEREQ response.
                raise Authentication_Error
            elif message_type == SSH_MSG_USERAUTH_PASSWD_CHANGEREQ:
                self.msg_userauth_passwd_changereq(packet, username, service_name)
            else:
                # Should never happen.
                raise ValueError, message_type

    def get_password(self, username, prompt=None):
        if prompt is None:
            prompt = '%s\'s password> ' % username
        return get_password(prompt)

    def msg_userauth_passwd_changereq(self, packet, username, service_name):
        # User's password has expired.  Allow the user to enter a new password.
        msg, prompt, language = ssh_packet.unpack_payload(PAYLOAD_MSG_USERAUTH_PASSWD_CHANGEREQ, packet)
        print safe_string(prompt)
        old_password = self.get_password('%s\'s old password> ' % username)
        while 1:
            new_password = self.get_password('%s\'s new password> ' % username)
            new_password2 = self.get_password('Retype new password> ')
            if new_password != new_password2:
                print 'Passwords did not match!  Try again.'
            else:
                break
        packet = ssh_packet.pack_payload(PAYLOAD_MSG_USERAUTH_REQUEST_CHANGE_PASSWD,
                                (SSH_MSG_USERAUTH_REQUEST,
                                 username,
                                 service_name,
                                 'password',
                                 1,
                                 old_password,
                                 new_password))
        self.ssh_transport.send_packet(packet)


# Not implemented, yet.
#class Hostbased(Userauth_Authentication_Method):
#    name = 'hostbased'
#
#    def get_userauth_request(self, username, service_name):
#        pass

class Userauth(Authentication_System):

    name = 'ssh-userauth'
    methods = None

    def __init__(self, ssh_transport):
        # Default...You can change.
        self.username = os.getlogin()
        self.ssh_transport = ssh_transport
        # Instantiate methods.
        self.methods = [Publickey(ssh_transport), Password(ssh_transport)]

    def authenticate(self, service_name):
        """authenticate(self, service_name) -> None
        Attempts to authenticate with the remote side.
        Assumes you have already confirmed that ssh-userauth is OK to use
        by sending a SSH_MSG_SERVICE_REQUEST packet.  This will try the
        authentication methods listed in self.methods in order until one of
        them works.

        Raises Authentication_Error if none of the authentication methods work.

        <service_name>: The name of the service that you want to use after
                        authenticating.  Typically 'ssh-connection'.
        """
        # Assume that all of our auths can continue.
        # Userauth_Method_Not_Allowed_Error will update this list if we
        # ever receive an error.
        auths_that_can_continue = [ method.name for method in self.methods ]
        callbacks = {SSH_MSG_USERAUTH_BANNER:  self.msg_userauth_banner}
        self.ssh_transport.register_callbacks(self.name, callbacks)
        try:
            for method in self.methods:
                if method.name in auths_that_can_continue:
                    self.ssh_transport.debug.write(ssh_debug.DEBUG_1, 'Trying authentication method "%s".', (method.name,))
                    try:
                        method.authenticate(self.username, service_name)
                    except Authentication_Error:
                        self.ssh_transport.debug.write(ssh_debug.DEBUG_1, 'Authentication method "%s" failed.', (method.name,))
                    except Userauth_Method_Not_Allowed_Error, why:
                        auths_that_can_continue = why.auths_that_can_continue
                    else:
                        # Authentication success.
                        return
            else:
                raise Authentication_Error
        finally:
            self.ssh_transport.unregister_callbacks(self.name)

    def msg_userauth_banner(self, packet):
        msg, message, language = ssh_packet.unpack_payload(PAYLOAD_MSG_USERAUTH_BANNER, packet)
        print safe_string(message)

SSH_MSG_USERAUTH_REQUEST    = 50
SSH_MSG_USERAUTH_FAILURE    = 51
SSH_MSG_USERAUTH_SUCCESS    = 52
SSH_MSG_USERAUTH_BANNER     = 53

SSH_MSG_USERAUTH_PK_OK      = 60
SSH_MSG_USERAUTH_PASSWD_CHANGEREQ = 60

PAYLOAD_MSG_USERAUTH_FAILURE = (ssh_packet.BYTE,      # SSH_MSG_USERAUTH_FAILURE
                                ssh_packet.NAME_LIST, # authentications that can continue
                                ssh_packet.BOOLEAN)   # partial success

PAYLOAD_MSG_USERAUTH_SUCCESS = (ssh_packet.BYTE,)   # SSH_MSG_USERAUTH_SUCCESS

PAYLOAD_MSG_USERAUTH_BANNER = (ssh_packet.BYTE,     # SSH_MSG_USERAUTH_BANNER
                               ssh_packet.STRING,   # message
                               ssh_packet.STRING)   # language tag

PAYLOAD_MSG_USERAUTH_REQUEST_PK_TEST = (ssh_packet.BYTE,    # SSH_MSG_USERAUTH_REQUEST
                                        ssh_packet.STRING,  # username
                                        ssh_packet.STRING,  # service
                                        ssh_packet.STRING,  # "publickey"
                                        ssh_packet.BOOLEAN, # FALSE
                                        ssh_packet.STRING,  # public key algorithm name
                                        ssh_packet.STRING)  # public key blob

PAYLOAD_MSG_USERAUTH_REQUEST_PK = (ssh_packet.BYTE,    # SSH_MSG_USERAUTH_REQUEST
                                   ssh_packet.STRING,  # username
                                   ssh_packet.STRING,  # service
                                   ssh_packet.STRING,  # "publickey"
                                   ssh_packet.BOOLEAN, # TRUE
                                   ssh_packet.STRING,  # public key algorithm name
                                   ssh_packet.STRING,  # public key blob
                                   ssh_packet.STRING)  # signature

PAYLOAD_USERAUTH_REQUEST_PK_SIGNATURE = (ssh_packet.STRING,  # session identifier
                                         ssh_packet.BYTE,    # SSH_MSG_USERAUTH_REQUEST
                                         ssh_packet.STRING,  # username
                                         ssh_packet.STRING,  # service
                                         ssh_packet.STRING,  # "publickey"
                                         ssh_packet.BOOLEAN, # TRUE
                                         ssh_packet.STRING,  # public key algorithm name
                                         ssh_packet.STRING)  # public key to be used for authentication

PAYLOAD_MSG_USERAUTH_PK_OK = (ssh_packet.BYTE,      # SSH_MSG_USERAUTH_PK_OK
                              ssh_packet.STRING,    # public key algorithm name from the request
                              ssh_packet.STRING)    # public key blob from the request

PAYLOAD_MSG_USERAUTH_REQUEST_PASSWORD = (ssh_packet.BYTE,   # SSH_MSG_USERAUTH_REQUEST
                                         ssh_packet.STRING, # username
                                         ssh_packet.STRING, # service
                                         ssh_packet.STRING, # "password"
                                         ssh_packet.BOOLEAN,# FALSE
                                         ssh_packet.STRING) # plaintext password

PAYLOAD_MSG_USERAUTH_PASSWD_CHANGEREQ = (ssh_packet.BYTE,   # SSH_MSG_USERAUTH_PASSWD_CHANGEREQ
                                         ssh_packet.STRING, # prompt
                                         ssh_packet.STRING) # language tag

PAYLOAD_MSG_USERAUTH_REQUEST_CHANGE_PASSWD = (ssh_packet.BYTE,      # SSH_MSG_USERAUTH_REQUEST
                                              ssh_packet.STRING,    # username
                                              ssh_packet.STRING,    # service
                                              ssh_packet.STRING,    # "password"
                                              ssh_packet.BOOLEAN,   # TRUE
                                              ssh_packet.STRING,    # plaintext old password
                                              ssh_packet.STRING)    # plaintext new password

PAYLOAD_MSG_USERAUTH_REQUEST_HOSTBASED = (ssh_packet.BYTE,      # SSH_MSG_USERAUTH_REQUEST
                                          ssh_packet.STRING,    # username
                                          ssh_packet.STRING,    # service
                                          ssh_packet.STRING,    # "hostbased"
                                          ssh_packet.STRING,    # public key algorithm for host key
                                          ssh_packet.STRING,    # public host key and certificates for client host
                                          ssh_packet.STRING,    # client host name
                                          ssh_packet.STRING,    # username on the client host
                                          ssh_packet.STRING)    # signature

PAYLOAD_USERAUTH_REQUEST_HOSTBASED_SIGNATURE = (ssh_packet.STRING,  # session identifier
                                                ssh_packet.BYTE,    # SSH_MSG_USERAUTH_REQUEST
                                                ssh_packet.STRING,  # username
                                                ssh_packet.STRING,  # service
                                                ssh_packet.STRING,  # "hostbased"
                                                ssh_packet.STRING,  # public key algorithm for host key
                                                ssh_packet.STRING,  # public host key and certificates for client host
                                                ssh_packet.STRING,  # client host name
                                                ssh_packet.STRING)  # username on the client host
