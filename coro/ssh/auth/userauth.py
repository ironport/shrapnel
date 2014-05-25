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

from coro.ssh.util.packet import unpack_payload, pack_payload, BYTE, STRING, BOOLEAN, NAME_LIST
from coro.ssh.util import debug as ssh_debug
from coro.ssh.util.password import get_password
from coro.ssh.util import safe_string
from coro.ssh.auth import Authentication_Error, Authentication_System

import coro

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

    def __init__(self, transport):
        self.transport = transport

    def authenticate(self, username, service_name):
        """authenticate(self, username, service_name) -> None
        Try to authenticate with the remote side.

        Raises Authentication_Error if it fails.
        """
        raise NotImplementedError

    def msg_userauth_failure(self, packet):
        self.transport.debug.write(ssh_debug.DEBUG_1, '%s Auth: Userauth failure.', (self.name,))
        msg, auths_that_can_continue, partial_success = unpack_payload(PAYLOAD_MSG_USERAUTH_FAILURE, packet)
        # XXX: How to handle partial_success?
        if self.name not in auths_that_can_continue:
            self.transport.debug.write(
                ssh_debug.DEBUG_1, '%s Auth: Not in the list of auths that can continue', (self.name,))
            raise Userauth_Method_Not_Allowed_Error(auths_that_can_continue)

class Publickey(Userauth_Authentication_Method):
    name = 'publickey'

    def authenticate(self, username, service_name):
        local_username = os.getlogin()
        for key_storage in self.transport.supported_key_storages:
            self.transport.debug.write(
                ssh_debug.DEBUG_1, 'Publickey Auth: Trying to load keytype "%s" for user "%s".',
                (key_storage.__class__.__name__, local_username))
            loaded_keys = key_storage.load_keys(username=local_username)
            if loaded_keys:
                for loaded_key in loaded_keys:
                    # Test this key type.
                    self.transport.debug.write(
                        ssh_debug.DEBUG_1, 'Publickey Auth: Sending PK test for keytype "%s".', (loaded_key.name,))
                    packet = pack_payload(PAYLOAD_MSG_USERAUTH_REQUEST_PK_TEST,
                                          (SSH_MSG_USERAUTH_REQUEST,
                                           username,
                                           service_name,
                                           'publickey',
                                           0,
                                           loaded_key.name,
                                           loaded_key.get_public_key_blob()
                                           ))
                    self.transport.send_packet(packet)
                    message_type, packet = self.transport.receive_message((SSH_MSG_USERAUTH_PK_OK,
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
                        raise ValueError(message_type)
                else:
                    self.transport.debug.write(ssh_debug.DEBUG_1, 'Publickey Auth: No more key storage types left.')
            else:
                self.transport.debug.write(ssh_debug.DEBUG_1, 'Publickey Auth: No keys found of this key storage type.')
        else:
            self.transport.debug.write(ssh_debug.DEBUG_1, 'Publickey Auth: No more storage key types left to try.')
            raise Authentication_Error

    def _try_auth(self, packet, loaded_key, username, service_name):
        self.transport.debug.write(ssh_debug.DEBUG_1, 'Publickey Auth: Got OK for this key type.')
        msg, key_algorithm_name, key_blob = unpack_payload(PAYLOAD_MSG_USERAUTH_PK_OK, packet)
        assert (key_algorithm_name == loaded_key.name)
        # XXX: Check key_blob, too?
        # Send the actual request.
        # Compute signature.
        session_id = self.transport.key_exchange.session_id
        sig_data = pack_payload(PAYLOAD_USERAUTH_REQUEST_PK_SIGNATURE,
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

        self.transport.debug.write(ssh_debug.DEBUG_1, 'Publickey Auth: Sending userauth request.')
        packet = pack_payload(PAYLOAD_MSG_USERAUTH_REQUEST_PK,
                              (SSH_MSG_USERAUTH_REQUEST,
                               username,
                               service_name,
                               'publickey',
                               1,
                               loaded_key.name,
                               loaded_key.get_public_key_blob(),
                               signature))
        self.transport.send_packet(packet)
        message_type, packet = self.transport.receive_message((SSH_MSG_USERAUTH_SUCCESS,
                                                               SSH_MSG_USERAUTH_FAILURE))
        if message_type == SSH_MSG_USERAUTH_SUCCESS:
            # Success.
            return
        elif message_type == SSH_MSG_USERAUTH_FAILURE:
            self.msg_userauth_failure(packet)
            raise Authentication_Error
        else:
            # Should never happen.
            raise ValueError(message_type)

class Password(Userauth_Authentication_Method):
    name = 'password'

    def authenticate(self, username, service_name):
        password = self.get_password(username)
        packet = pack_payload(PAYLOAD_MSG_USERAUTH_REQUEST_PASSWORD,
                              (SSH_MSG_USERAUTH_REQUEST,
                               username,
                               service_name,
                               'password',
                               0,
                               password
                               ))
        self.transport.send_packet(packet)
        # While loop in case we get a CHANGEREQ packet.
        while 1:
            try:
                message_type, packet = self.transport.receive_message((
                    SSH_MSG_USERAUTH_SUCCESS, SSH_MSG_USERAUTH_FAILURE,
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
                raise ValueError(message_type)

    def get_password(self, username, prompt=None):
        if prompt is None:
            prompt = '%s\'s password> ' % username
        return get_password(prompt)

    def msg_userauth_passwd_changereq(self, packet, username, service_name):
        # User's password has expired.  Allow the user to enter a new password.
        msg, prompt, language = unpack_payload(PAYLOAD_MSG_USERAUTH_PASSWD_CHANGEREQ, packet)
        print safe_string(prompt)
        old_password = self.get_password('%s\'s old password> ' % username)
        while 1:
            new_password = self.get_password('%s\'s new password> ' % username)
            new_password2 = self.get_password('Retype new password> ')
            if new_password != new_password2:
                print 'Passwords did not match!  Try again.'
            else:
                break
        packet = pack_payload(PAYLOAD_MSG_USERAUTH_REQUEST_CHANGE_PASSWD,
                              (SSH_MSG_USERAUTH_REQUEST,
                               username,
                               service_name,
                               'password',
                               1,
                               old_password,
                               new_password))
        self.transport.send_packet(packet)

# Not implemented, yet.
# class Hostbased(Userauth_Authentication_Method):
#    name = 'hostbased'
#
#    def get_userauth_request(self, username, service_name):
#        pass

class Userauth(Authentication_System):

    name = 'ssh-userauth'
    methods = None

    def __init__(self, transport, username=None):
        if username is None:
            self.username = os.getlogin()
        else:
            self.username = username
        self.transport = transport
        # Instantiate methods.
        self.methods = [Publickey(transport), Password(transport)]

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
        auths_that_can_continue = [method.name for method in self.methods]
        callbacks = {SSH_MSG_USERAUTH_BANNER: self.msg_userauth_banner}
        self.transport.register_callbacks(self.name, callbacks)
        try:
            for method in self.methods:
                if method.name in auths_that_can_continue:
                    self.transport.debug.write(ssh_debug.DEBUG_1, 'Trying authentication method "%s".', (method.name,))
                    try:
                        method.authenticate(self.username, service_name)
                    except Authentication_Error:
                        self.transport.debug.write(
                            ssh_debug.DEBUG_1, 'Authentication method "%s" failed.', (method.name,))
                    except Userauth_Method_Not_Allowed_Error, why:
                        auths_that_can_continue = why.auths_that_can_continue
                    else:
                        # Authentication success.
                        return
            else:
                raise Authentication_Error
        finally:
            self.transport.unregister_callbacks(self.name)

    def msg_userauth_banner(self, packet):
        msg, message, language = unpack_payload(PAYLOAD_MSG_USERAUTH_BANNER, packet)
        print safe_string(message)

# ----------------------------------------------------------------------------------------------------
# server side authentication
# ----------------------------------------------------------------------------------------------------

class Authenticator:

    # maximum number of auth attempts per session
    max_tries = 5
    # amount of time to pause between attempts
    sleep_time = 0.1

    def __init__ (self, transport, methods):
        self.transport = transport
        self.methods = methods
        # XXX this assumes only one of each method type?  e,g, might a user want multiple entries under 'publickey'?
        self.by_name = dict((method.name, method) for method in self.methods)

    def send (self, format, values):
        self.transport.send_packet (pack_payload (format, values))

    def send_failure (self):
        self.send (PAYLOAD_MSG_USERAUTH_FAILURE, (SSH_MSG_USERAUTH_FAILURE, self.by_name.keys(), 0))

    def authenticate (self, service_name):
        session_id = self.transport.key_exchange.session_id
        tries = self.max_tries
        while tries:
            # this is relatively stateless, because the RFC says the client can send requests without bothering
            #  to see if the server even wants them.
            # XXX allow each method to be tried, then removed from the list of
            # possibles? [think about combinations of service/user/etc... though]
            message_type, packet = self.transport.receive_message ((SSH_MSG_USERAUTH_REQUEST,))
            msg, username, service, method = unpack_payload (PAYLOAD_MSG_USERAUTH_REQUEST, packet)
            if method == 'none':
                self.send_failure()
            elif method == 'publickey':
                mprobe = self.by_name.get ('publickey')
                if not mprobe:
                    self.send_failure()
                else:
                    (_, _, _, _, btest, alg, blob) = unpack_payload (PAYLOAD_MSG_USERAUTH_REQUEST_PK_TEST, packet)
                    if not btest:
                        # XXX: ask method if it's ok with serv+user+alg+blob
                        self.send (PAYLOAD_MSG_USERAUTH_PK_OK, (SSH_MSG_USERAUTH_PK_OK, alg, blob))
                    else:
                        (_, _, _, _, _, _, key, sig) = unpack_payload (PAYLOAD_MSG_USERAUTH_REQUEST_PK, packet)
                        self.transport.debug.write (
                            ssh_debug.DEBUG_1, 'Trying Public Key Authentication: %r' % ((service, username, alg),))
                        if mprobe.authenticate (session_id, service, username, alg, key, sig):
                            self.send (PAYLOAD_MSG_USERAUTH_SUCCESS, (SSH_MSG_USERAUTH_SUCCESS,))
                            return True
                        else:
                            tries -= 1
                            coro.sleep_relative (self.sleep_time)
                            self.send_failure()
            elif method == 'password':
                mprobe = self.by_name.get ('password')
                if not mprobe:
                    self.send_failure()
                else:
                    (_, _, _, _, btest, password) = unpack_payload (PAYLOAD_MSG_USERAUTH_REQUEST_PASSWORD, packet)
                    self.transport.debug.write (
                        ssh_debug.DEBUG_1, 'Trying Password Authentication: %r' % ((service, username,),))
                    if btest:
                        self.transport.debug.write (
                            ssh_debug.DEBUG_1, 'Client side trying to change password: Not Yet Implemented')
                        return send_failure()
                    elif mprobe.authenticate (service, username, password):
                        self.send (PAYLOAD_MSG_USERAUTH_SUCCESS, (SSH_MSG_USERAUTH_SUCCESS,))
                        return True
                    else:
                        tries -= 1
                        coro.sleep_relative (self.sleep_time)
                        self.send_failure()
            else:
                tries -= 1
                coro.sleep_relative (self.sleep_time)
                self.send_failure()

class Public_Key_Authenticator:

    name = 'publickey'

    # { <user> : { <service>: [key0, key1, ...], ...}, ... }

    def __init__ (self, keys):
        self.keys = keys

    def authenticate (self, session_id, serv, user, alg, blob, sig):
        # build the signable data
        to_sign = pack_payload (
            PAYLOAD_USERAUTH_REQUEST_PK_SIGNATURE, (
                session_id, SSH_MSG_USERAUTH_REQUEST, user, serv, 'publickey', 1, alg, blob
            )
        )
        try:
            keys = self.keys[user][serv]
            for key in keys:
                if key.name == alg and key.get_public_key_blob() == blob and key.verify (to_sign, sig):
                    return True
            return False
        except KeyError:
            return False

class Password_Authenticator:

    name = 'password'

    # { <user> : { <service>: <pwd>, ...}, ... }

    def __init__ (self, pwds):
        self.pwds = pwds

    def authenticate (self, service, username, password):
        try:
            return self.pwds[username][service] == password
        except KeyError:
            return False

# ----------------------------------------------------------------------------------------------------

SSH_MSG_USERAUTH_REQUEST    = 50
SSH_MSG_USERAUTH_FAILURE    = 51
SSH_MSG_USERAUTH_SUCCESS    = 52
SSH_MSG_USERAUTH_BANNER     = 53

SSH_MSG_USERAUTH_PK_OK      = 60
SSH_MSG_USERAUTH_PASSWD_CHANGEREQ = 60

# this is the 'generic header' of all auth requests
PAYLOAD_MSG_USERAUTH_REQUEST = (
    BYTE,    # SSH_MSG_USERAUTH_REQUEST
    STRING,  # username
    STRING,  # service
    STRING,  # method
)

PAYLOAD_MSG_USERAUTH_FAILURE = (BYTE,      # SSH_MSG_USERAUTH_FAILURE
                                NAME_LIST,  # authentications that can continue
                                BOOLEAN)   # partial success

PAYLOAD_MSG_USERAUTH_SUCCESS = (BYTE,)   # SSH_MSG_USERAUTH_SUCCESS

PAYLOAD_MSG_USERAUTH_BANNER = (BYTE,     # SSH_MSG_USERAUTH_BANNER
                               STRING,   # message
                               STRING)   # language tag

PAYLOAD_MSG_USERAUTH_REQUEST_PK_TEST = (BYTE,    # SSH_MSG_USERAUTH_REQUEST
                                        STRING,  # username
                                        STRING,  # service
                                        STRING,  # "publickey"
                                        BOOLEAN,  # FALSE
                                        STRING,  # public key algorithm name
                                        STRING)  # public key blob

PAYLOAD_MSG_USERAUTH_REQUEST_PK = (BYTE,    # SSH_MSG_USERAUTH_REQUEST
                                   STRING,  # username
                                   STRING,  # service
                                   STRING,  # "publickey"
                                   BOOLEAN,  # TRUE
                                   STRING,  # public key algorithm name
                                   STRING,  # public key blob
                                   STRING)  # signature

PAYLOAD_USERAUTH_REQUEST_PK_SIGNATURE = (STRING,  # session identifier
                                         BYTE,    # SSH_MSG_USERAUTH_REQUEST
                                         STRING,  # username
                                         STRING,  # service
                                         STRING,  # "publickey"
                                         BOOLEAN,  # TRUE
                                         STRING,  # public key algorithm name
                                         STRING)  # public key to be used for authentication

PAYLOAD_MSG_USERAUTH_PK_OK = (BYTE,      # SSH_MSG_USERAUTH_PK_OK
                              STRING,    # public key algorithm name from the request
                              STRING)    # public key blob from the request

PAYLOAD_MSG_USERAUTH_REQUEST_PASSWORD = (BYTE,   # SSH_MSG_USERAUTH_REQUEST
                                         STRING,  # username
                                         STRING,  # service
                                         STRING,  # "password"
                                         BOOLEAN,  # FALSE
                                         STRING)  # plaintext password

PAYLOAD_MSG_USERAUTH_PASSWD_CHANGEREQ = (BYTE,   # SSH_MSG_USERAUTH_PASSWD_CHANGEREQ
                                         STRING,  # prompt
                                         STRING)  # language tag

PAYLOAD_MSG_USERAUTH_REQUEST_CHANGE_PASSWD = (BYTE,      # SSH_MSG_USERAUTH_REQUEST
                                              STRING,    # username
                                              STRING,    # service
                                              STRING,    # "password"
                                              BOOLEAN,   # TRUE
                                              STRING,    # plaintext old password
                                              STRING)    # plaintext new password

PAYLOAD_MSG_USERAUTH_REQUEST_HOSTBASED = (BYTE,      # SSH_MSG_USERAUTH_REQUEST
                                          STRING,    # username
                                          STRING,    # service
                                          STRING,    # "hostbased"
                                          STRING,    # public key algorithm for host key
                                          STRING,    # public host key and certificates for client host
                                          STRING,    # client host name
                                          STRING,    # username on the client host
                                          STRING)    # signature

PAYLOAD_USERAUTH_REQUEST_HOSTBASED_SIGNATURE = (STRING,  # session identifier
                                                BYTE,    # SSH_MSG_USERAUTH_REQUEST
                                                STRING,  # username
                                                STRING,  # service
                                                STRING,  # "hostbased"
                                                STRING,  # public key algorithm for host key
                                                STRING,  # public host key and certificates for client host
                                                STRING,  # client host name
                                                STRING)  # username on the client host
