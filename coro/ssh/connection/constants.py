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
# ssh.connect.constants
#
# Constants used in the connect protocol.

from coro.ssh.util import packet

SSH_MSG_GLOBAL_REQUEST                 = 80
SSH_MSG_GLOBAL_REQUEST_SUCCESS         = 81
SSH_MSG_GLOBAL_REQUEST_FAILURE         = 82
SSH_MSG_CHANNEL_OPEN                   = 90
SSH_MSG_CHANNEL_OPEN_CONFIRMATION      = 91
SSH_MSG_CHANNEL_OPEN_FAILURE           = 92
SSH_MSG_CHANNEL_WINDOW_ADJUST          = 93
SSH_MSG_CHANNEL_DATA                   = 94
SSH_MSG_CHANNEL_EXTENDED_DATA          = 95
SSH_MSG_CHANNEL_EOF                    = 96
SSH_MSG_CHANNEL_CLOSE                  = 97
SSH_MSG_CHANNEL_REQUEST                = 98
SSH_MSG_CHANNEL_SUCCESS                = 99
SSH_MSG_CHANNEL_FAILURE                = 100

# This is the basic open payload.  Different session types may add
# additional information to this.
SSH_MSG_CHANNEL_OPEN_PAYLOAD = (packet.BYTE,        # SSH_MSG_CHANNEL_OPEN
                                packet.STRING,      # channel type
                                packet.UINT32,      # sender channel
                                packet.UINT32,      # initial window size
                                packet.UINT32)      # maximum packet size

# This is the basic confirmation payload.  Different session types may add
# addition information to this.
SSH_MSG_CHANNEL_OPEN_CONFIRMATION_PAYLOAD = (packet.BYTE,   # SSH_MSG_CHANNEL_OPEN_CONFIRMATION,
                                             packet.UINT32, # recipient channel
                                             packet.UINT32, # sender channel
                                             packet.UINT32, # initial window size
                                             packet.UINT32) # maximum packet size

SSH_MSG_CHANNEL_OPEN_FAILURE_PAYLOAD = (packet.BYTE,    # SSH_MSG_CHANNEL_OPEN_FAILURE
                                        packet.UINT32,  # recipient channel
                                        packet.UINT32,  # reason_code
                                        packet.STRING,  # reason_text
                                        packet.STRING)  # language

SSH_MSG_CHANNEL_CLOSE_PAYLOAD = (packet.BYTE,       # SSH_MSG_CHANNEL_CLOSE
                                 packet.UINT32)     # recipient_channel


# This may contain additional request-specific data.
SSH_MSG_GLOBAL_REQUEST_PAYLOAD = (packet.BYTE,      # SSH_MSG_GLOBAL_REQUEST
                                  packet.STRING,    # request name
                                  packet.BOOLEAN)   # want reply

# This may contain additional request-specific data.
SSH_MSG_GLOBAL_REQUEST_SUCCESS_PAYLOAD = (packet.BYTE)     # SSH_MSG_GLOBAL_REQUEST_SUCCESS

SSH_MSG_GLOBAL_REQUEST_FAILURE_PAYLOAD = (packet.BYTE)     # SSH_MSG_GLOBAL_REQUEST_FAILURE

SSH_MSG_CHANNEL_WINDOW_ADJUST_PAYLOAD = (packet.BYTE,   # SSH_MSG_CHANNEL_WINDOW_ADJUST
                                         packet.UINT32, # recipient channel
                                         packet.UINT32) # bytes to add

SSH_MSG_CHANNEL_DATA_PAYLOAD = (packet.BYTE,        # SSH_MSG_CHANNEL_DATA
                                packet.UINT32,      # recipient channel
                                packet.STRING)      # data

SSH_MSG_CHANNEL_EXTENDED_DATA_PAYLOAD = (packet.BYTE,   # SSH_MSG_CHANNEL_EXTENDED_DATA
                                         packet.UINT32, # recipient channel
                                         packet.UINT32, # data_type_code
                                         packet.STRING) # data

SSH_EXTENDED_DATA_STDERR = 1

SSH_MSG_CHANNEL_EOF_PAYLOAD = (packet.BYTE,     # SSH_MSG_CHANNEL_EOF
                               packet.UINT32)   # recipient channel

# This may contain additional request-specific data.
SSH_MSG_CHANNEL_REQUEST_PAYLOAD = (packet.BYTE,     # SSH_MSG_CHANNEL_REQUEST
                                   packet.UINT32,   # recipient_channel
                                   packet.STRING,   # request type
                                   packet.BOOLEAN)  # want reply

SSH_MSG_CHANNEL_FAILURE_PAYLOAD = (packet.BYTE,     # SSH_MSG_CHANNEL_FAILURE
                                   packet.UINT32)   # recipient_channel

SSH_MSG_CHANNEL_SUCCESS_PAYLOAD = (packet.BYTE,     # SSH_MSG_CHANNEL_SUCCESS
                                   packet.UINT32)   # recipient_channel
