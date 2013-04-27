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
# ssh.auth
#
# This handles the various types of authentication systems.
#

from coro.ssh import transport

class Authentication_System(transport.SSH_Service):

    def authenticate(self, service_name):
        """authenticate(self, service_name) -> None
        Attempts to authenticate with the remote side.
        Assumes you have already confirmed that this authentication service
        is OK to use by sending a SSH_MSG_SERVICE_REQUEST packet.

        <service_name>: The name of the service that you want to use after
                        authenticating.  Typically 'ssh-connection'.
        """
        # XXX: userauth is currently the only defined authentication
        #      mechanism that I know if.  userauth requires to know
        #      what the service is you are trying to authenticate for.
        #      This means that this generic API is specialized to include
        #      service_name only because Userauth is kinda designed weird.
        #      It is possible that other auth types don't care what service
        #      you want to run.
        raise NotImplementedError

class Authentication_Error(Exception):
    pass
