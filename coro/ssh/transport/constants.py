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
# ssh.transport.constants
#
# Constants used in the transport modules.
#

SSH_MSG_DISCONNECT      = 1
SSH_MSG_IGNORE          = 2
SSH_MSG_UNIMPLEMENTED   = 3
SSH_MSG_DEBUG           = 4
SSH_MSG_SERVICE_REQUEST = 5
SSH_MSG_SERVICE_ACCEPT  = 6
SSH_MSG_KEXINIT         = 20
SSH_MSG_NEWKEYS         = 21

SSH_DISCONNECT_HOST_NOT_ALLOWED_TO_CONNECT    = 1
SSH_DISCONNECT_PROTOCOL_ERROR                 = 2
SSH_DISCONNECT_KEY_EXCHANGE_FAILED            = 3
SSH_DISCONNECT_RESERVED                       = 4
SSH_DISCONNECT_MAC_ERROR                      = 5
SSH_DISCONNECT_COMPRESSION_ERROR              = 6
SSH_DISCONNECT_SERVICE_NOT_AVAILABLE          = 7
SSH_DISCONNECT_PROTOCOL_VERSION_NOT_SUPPORTED = 8
SSH_DISCONNECT_HOST_KEY_NOT_VERIFIABLE        = 9
SSH_DISCONNECT_CONNECTION_LOST                = 10
SSH_DISCONNECT_BY_APPLICATION                 = 11
SSH_DISCONNECT_TOO_MANY_CONNECTIONS           = 12
SSH_DISCONNECT_AUTH_CANCELLED_BY_USER         = 13
SSH_DISCONNECT_NO_MORE_AUTH_METHODS_AVAILABLE = 14
SSH_DISCONNECT_ILLEGAL_USER_NAME              = 15
