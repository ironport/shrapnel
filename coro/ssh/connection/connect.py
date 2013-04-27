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
# ssh.connection.connect
#
# This implements the SSH Connect service.  This service can run interactive
# login sessions, remote execution of comments, forwarded TCP/IP connections,
# and forwarded X11 connections.  These channels can be multiplexed into a
# single encrypted tunnel.
#

__version__ = '$Revision: #1 $'

import ssh.transport
import ssh.util.packet
import ssh.util.debug
from constants import *

class Connection_Service(ssh.transport.SSH_Service):
    name = 'ssh-connection'

    # This is a counter used to assign local channel ID's.
    next_channel_id = 0

    # This is a dictionary of channels.
    # The key is the channel ID, the value is the Channel object.
    local_channels = None
    # This is a dictionary of remote channels.
    # The key is the remote channel ID, the value is a Remote_Channel object.
    remote_channels = None

    def __init__(self, transport):
        self.transport = transport
        self.local_channels = {}
        self.remote_channels = {}

        callbacks = {SSH_MSG_GLOBAL_REQUEST: self.msg_global_request,
                     SSH_MSG_CHANNEL_WINDOW_ADJUST: self.msg_channel_window_adjust,
                     SSH_MSG_CHANNEL_DATA: self.msg_channel_data,
                     SSH_MSG_CHANNEL_EXTENDED_DATA: self.msg_channel_extended_data,
                     SSH_MSG_CHANNEL_EOF: self.msg_channel_eof,
                     SSH_MSG_CHANNEL_CLOSE: self.msg_channel_close,
                     SSH_MSG_CHANNEL_REQUEST: self.msg_channel_request,
                     SSH_MSG_CHANNEL_SUCCESS: self.msg_channel_success,
                     SSH_MSG_CHANNEL_FAILURE: self.msg_channel_failure,
                     SSH_MSG_CHANNEL_OPEN_CONFIRMATION: self.msg_channel_open_confirmation,
                     SSH_MSG_CHANNEL_OPEN_FAILURE: self.msg_channel_open_failure,
                    }
        self.transport.register_callbacks('ssh-connection', callbacks)

    def register_channel(self, channel):
        """register_channel(self, channel) -> None
        When opening a channel, this function is called to add it to the
        local_channels dictionary and to set the channel id.
        """
        channel.channel_id = self.next_channel_id
        assert not self.local_channels.has_key(channel.channel_id)
        self.next_channel_id += 1               # XXX: Overflow?
        self.local_channels[channel.channel_id] = channel

    def msg_global_request(self, packet):
        # XXX: finish this (it's a server thing)
        data, offset = ssh.util.packet.unpack_payload_get_offset(SSH_MSG_GLOBAL_REQUEST_PAYLOAD, packet)
        msg, request_name, want_reply = data
        raise NotImplementedError

    def msg_channel_window_adjust(self, packet):
        msg, channel_id, bytes_to_add = ssh.util.packet.unpack_payload(SSH_MSG_CHANNEL_WINDOW_ADJUST_PAYLOAD, packet)
        channel = self.local_channels[channel_id]
        channel.remote_channel.window_data_left += bytes_to_add
        self.transport.debug.write(ssh.util.debug.DEBUG_3, 'channel %i window increased by %i to %i', (channel.remote_channel.channel_id, bytes_to_add, channel.remote_channel.window_data_left))
        channel.window_data_added_cv.wake_all()

    def msg_channel_data(self, packet):
        msg, channel_id, data = ssh.util.packet.unpack_payload(SSH_MSG_CHANNEL_DATA_PAYLOAD, packet)
        channel = self.local_channels[channel_id]
        # XXX: In theory, we should verify that len(data) <= channel.max_packet_size
        if len(data) > channel.window_data_left:
            self.transport.debug.write(ssh.util.debug.WARNING, 'channel %i %i bytes overflowed window of %i', (channel.channel_id, len(data), channel.remote_channel.window_data_left))
            # Data is ignored.
        else:
            channel.window_data_left -= len(data)
            channel.append_data_received(data)

    def msg_channel_extended_data(self, packet):
        msg, channel_id, data_type_code, data = ssh.util.packet.unpack_payload(SSH_MSG_CHANNEL_EXTENDED_DATA_PAYLOAD, packet)
        channel = self.local_channels[channel_id]
        if len(data) > channel.window_data_left:
            self.transport.debug.write(ssh.util.debug.WARNING, 'channel %i %i bytes overflowed window of %i', (channel.channel_id, len(data), channel.remote_channel.window_data_left))
            # Data is ignored.
        else:
            channel.window_data_left -= len(data)
            channel.append_extended_data_received(data_type_code, data)

    def msg_channel_eof(self, packet):
        msg, channel_id = ssh.util.packet.unpack_payload(SSH_MSG_CHANNEL_EOF_PAYLOAD, packet)
        channel = self.local_channels[channel_id]
        # assert it is not already closed?
        channel.set_eof()

    def msg_channel_close(self, packet):
        msg, channel_id = ssh.util.packet.unpack_payload(SSH_MSG_CHANNEL_CLOSE_PAYLOAD, packet)
        channel = self.local_channels[channel_id]
        del self.local_channels[channel_id]
        del self.remote_channels[channel.remote_channel.channel_id]
        # assert it is not already closed?
        channel.closed = 1
        if not channel.remote_channel.closed:
            # Close the other side.
            channel.close()
        channel.set_eof()

    def msg_channel_request(self, packet):
        data, offset = ssh.util.packet.unpack_payload_get_offset(SSH_MSG_CHANNEL_REQUEST_PAYLOAD, packet)
        msg, channel_id, request_type, want_reply = data
        channel = self.local_channels[channel_id]
        channel.handle_request(request_type, want_reply, packet[offset:])

    def msg_channel_success(self, packet):
        msg, channel_id = ssh.util.packet.unpack_payload(SSH_MSG_CHANNEL_SUCCESS_PAYLOAD, packet)
        channel = self.local_channels[channel_id]
        channel.channel_request_success()

    def msg_channel_failure(self, packet):
        msg, channel_id = ssh.util.packet.unpack_payload(SSH_MSG_CHANNEL_FAILURE_PAYLOAD, packet)
        channel = self.local_channels[channel_id]
        channel.channel_request_failure()

    def msg_channel_open_confirmation(self, packet):
        data, offset = ssh.util.packet.unpack_payload_get_offset(SSH_MSG_CHANNEL_OPEN_CONFIRMATION_PAYLOAD, packet)
        msg, recipient_channel, sender_channel, window_size, max_packet_size = data
        self.transport.debug.write(ssh.util.debug.DEBUG_1, 'channel %i open confirmation sender_channel=%i window_size=%i max_packet_size=%i', (recipient_channel, sender_channel, window_size, max_packet_size))
        channel = self.local_channels[recipient_channel]
        # XXX: Assert that the channel is not already open?
        channel.closed = 0
        channel.eof = 0
        channel.remote_channel.closed = 0
        channel.remote_channel.channel_id = sender_channel
        assert not self.remote_channels.has_key(sender_channel)
        self.remote_channels[sender_channel] = channel.remote_channel
        channel.remote_channel.window_size = window_size
        channel.remote_channel.window_data_left = window_size
        channel.remote_channel.max_packet_size = max_packet_size
        additional_data = ssh.util.packet.unpack_payload(channel.additional_packet_data_types, packet, offset)
        channel.channel_open_success(additional_data)

    def msg_channel_open_failure(self, packet):
        msg, channel_id, reason_code, reason_text, language = ssh.util.packet.unpack_payload(SSH_MSG_CHANNEL_OPEN_FAILURE_PAYLOAD, packet)
        channel = self.local_channels[channel_id]
        # XXX: Assert that the channel is not already open?
        channel.channel_open_failure(reason_code, reason_text, language)
