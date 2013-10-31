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
# ssh.connection.channel
#
# This is the base class for developing channels
# used by the ssh_connect service.
#

import coro

from coro.ssh.connection.data_buffer import Buffer
from coro.ssh.connection.constants import *
from coro.ssh.util import packet, debug

class Channel_Request_Failure(Exception):
    pass

class Channel_Open_Error(Exception):
    def __init__(self, channel_id, reason_code, reason_text, language):
        Exception.__init__(self, channel_id, reason_code, reason_text, language)
        self.channel_id = channel_id
        self.reason_code = reason_code
        self.reason_text = reason_text
        self.language = language

    def __str__(self):
        if channel_open_error_strings.has_key(self.reason_code):
            reason_code_str = ' (%s)' % channel_open_error_strings[self.reason_code]
        else:
            reason_code_str = ''
        return 'Channel ID %i Open Error: %i%s: %r' % (self.channel_id, self.reason_code, reason_code_str, self.reason_text)

class Channel_Closed_Error(Exception):
    pass

# List of channel open error codes.
SSH_OPEN_ADMINISTRATIVELY_PROHIBITED    = 1
SSH_OPEN_CONNECT_FAILED                 = 2
SSH_OPEN_UNKNOWN_CHANNEL_TYPE           = 3
SSH_OPEN_RESOURCE_SHORTAGE              = 4

channel_open_error_strings = {
    SSH_OPEN_ADMINISTRATIVELY_PROHIBITED:   'administratively prohibited',
    SSH_OPEN_CONNECT_FAILED:                'connect failed',
    SSH_OPEN_UNKNOWN_CHANNEL_TYPE:          'unknown channel type',
    SSH_OPEN_RESOURCE_SHORTAGE:             'resource shortage',
}

class Channel:
    name = ''
    channel_id = 0
    window_size = 131072 # 128k
    max_packet_size = 131072 # 128k
    # Additional ssh.util.packet data types used in the CHANNEL_OPEN message.
    additional_packet_data_types = ()

    # This is a flag you can change if you want to handle extended data
    # differently.
    treat_extended_data_as_regular = 1

    # This is how many bytes the remote side can send.
    # Once it hits zero, I start ignoring data.
    # The current algorithm is to increase the window size back to the
    # initial size whenever this number drops below one half.
    window_data_left = window_size

    # Condition variable triggered whenever the window is updated.
    window_data_added_cv = None

    closed = 1
    eof = 1

    # This is the instance that is created for data flowing in from the other
    # side.
    remote_channel = None

    # This is a buffer of data received.  It is a Buffer instance.
    # A value of '' in the buffer indicates EOF.
    recv_buffer = None
    # This is a buffer of extended data received.
    # The key is the data_type_code, and the value is a Buffer instance.
    extended_recv_buffer = None

    # This is a condition variable triggered when channel request responses
    # are received.  The thread is awoken with a boolean value that indicates
    # whether or not the request succeeded.
    # XXX: There is a problem that this doesn't handle concurrent requests.
    channel_request_cv = None

    # This is a condition variable triggered when open success or failure
    # is received.
    channel_open_cv = None

    def __init__(self, connection_service):
        self.connection_service = connection_service
        # Local reference for convenience.
        self.transport = connection_service.transport
        self.recv_buffer = Buffer()
        self.extended_recv_buffer = {}
        self.remote_channel = Remote_Channel()
        self.window_data_added_cv = coro.condition_variable()
        self.channel_request_cv = coro.condition_variable()
        self.channel_open_cv = coro.condition_variable()

    def __str__(self):
        return '<Channel %s ID:%i>' % (self.name, self.channel_id)

    def get_additional_open_data(self):
        """get_additional_open_data(self) -> data
        Returns the additional information used for opening a channel.
        <data> is a tuple of the actual data that is appended to the packet.
        """
        # No additional data by default.
        return ()

    def set_additional_open_data(self, data):
        """set_additional_open_data(self, data) -> None
        Sets the additional data information.
        <data> is a tuple of the data elements specific to this channel type.
        """
        # By default ignore any open data.
        return None

    def send_channel_request(self, request_type, payload, data, want_reply=1, default_reply_handler=True):
        """send_channel_request(self, request_type, payload, data, want_reply=1, default_reply_handler=True) -> None
        This is a generic mechanism for sending a channel request packet.

        <request_type>: Request type to send.
        <payload>: The ssh_packet format definition.
        <data>: The data to go with the payload.
        <want_reply>: The want_reply flag.
        <default_reply_handler>: If true and want_reply is True, then the
                default reply handler will be used.  The default reply
                handler is pretty simple.  Will just return if
                CHANNEL_REQUEST_SUCCESS is received.  Will raise
                Channel_Request_Failure if FAILURE is received.
        """
        # XXX: There is a problem with the spec.  It does not indicate how to
        #      match requests with responses.  IIRC, they talked about it on
        #      the mailing list and updated the spec.  Need to investigate if
        #      they have clarified the spec on how to handle this.
        # XXX: Or maybe concurrent channel requests on the same channel are
        #      not allowed?
        if self.remote_channel.closed:
            raise Channel_Closed_Error
        pkt = packet.pack_payload(SSH_MSG_CHANNEL_REQUEST_PAYLOAD,
                                            (SSH_MSG_CHANNEL_REQUEST,
                                             self.remote_channel.channel_id,
                                             request_type,
                                             int(want_reply)))
        pkt_data = packet.pack_payload(payload, data)
        self.transport.send_packet(pkt + pkt_data)
        if want_reply and default_reply_handler:
            # Wait for response.
            assert len(self.channel_request_cv)==0, 'Concurrent channel requests not supported!'
            if not self.channel_request_cv.wait():
                raise Channel_Request_Failure

    def append_data_received(self, data):
        """append_data_received(self, data) -> None
        Indicates that the given data was received.
        """
        if data:
            self.recv_buffer.write(data)

    def append_extended_data_received(self, data_type_code, data):
        """append_extended_data_received(self, data_type_code, data) -> None
        Indicates that the given extended data was received.
        """
        if data:
            if self.treat_extended_data_as_regular:
                self.append_data_received(data)
            else:
                if self.extended_recv_buffer.has_key(data_type_code):
                    self.extended_recv_buffer[data_type_code].write(data)
                else:
                    b = Buffer()
                    b.write(data)
                    self.extended_recv_buffer[data_type_code] = b

    def set_eof(self):
        """set_eof(self) -> None
        Indicate that there is no more data on this channel.
        """
        self.eof = 1
        self.recv_buffer.write('')
        for b in self.extended_recv_buffer.values():
            b.write('')

    def handle_request(self, request_type, want_reply, type_specific_packet_data):
        # Default is always to fail.  Specific channel types override this method.
        if want_reply:
            pkt = packet.pack_payload(SSH_MSG_CHANNEL_FAILURE_PAYLOAD,
                                                        (SSH_MSG_CHANNEL_FAILURE,
                                                         self.remote_channel.channel_id,))
            self.transport.send_packet(pkt)

    def open(self):
        """open(self) -> None
        Opens the channel to the remote side.
        """
        assert self.closed
        self.connection_service.register_channel(self)
        self.transport.debug.write(debug.DEBUG_2, 'sending channel open request channel ID %i', (self.channel_id,))

        # Send the open request.
        additional_data = self.get_additional_open_data()
        packet_payload = SSH_MSG_CHANNEL_OPEN_PAYLOAD + self.additional_packet_data_types
        packet_data = (SSH_MSG_CHANNEL_OPEN,
                             self.name,
                             self.channel_id,
                             self.window_size,
                             self.max_packet_size) + additional_data
        pkt = packet.pack_payload(packet_payload, packet_data)
        self.transport.send_packet(pkt)
        success, data = self.channel_open_cv.wait()
        if success:
            self.set_additional_open_data(data)
        else:
            reason_code, reason_text, language = data
            raise Channel_Open_Error(self.channel_id, reason_code, reason_text, language)

    def close(self):
        """close(self) -> None
        Tell remote side to close its channel.
        Our side is not considered "closed" until after we receive
        SSH_MSG_CHANNEL_CLOSE from the remote side.
        """
        if not self.remote_channel.closed:
            self.remote_channel.closed = 1
            pkt = packet.pack_payload(SSH_MSG_CHANNEL_CLOSE_PAYLOAD,
                                                (SSH_MSG_CHANNEL_CLOSE,
                                                 self.remote_channel.channel_id))
            self.transport.send_packet(pkt)

            # We need to cause any threads that were trying to write on
            # this channel to stop trying to write. If they were asleep
            # waiting for one of the three condition variables, we need to
            # wake them up. They will notice that self.remote_channel.closed
            # is now true, and will do the right thing.
            self.window_data_added_cv.wake_all()
            self.channel_request_cv.wake_all(False)
            self.channel_open_cv.wake_all((False, (SSH_OPEN_CONNECT_FAILED,
                                                   'Channel has been closed',
                                                   None)))

    def send_window_adjustment(self, bytes_to_add):
        self.transport.debug.write(debug.DEBUG_2, 'sending window adjustment to add %i bytes', (bytes_to_add,))
        pkt = packet.pack_payload(SSH_MSG_CHANNEL_WINDOW_ADJUST_PAYLOAD,
                                                (SSH_MSG_CHANNEL_WINDOW_ADJUST,
                                                 self.remote_channel.channel_id,
                                                 bytes_to_add))
        self.transport.send_packet(pkt)
        self.window_data_left += bytes_to_add

    def has_data_to_read(self, extended=None):
        """has_data_to_read(self, extended=None) -> boolean
        Returns whether or not there is data available to read.

        <extended>: data_type_code of extended data type to read.
                    Set to None for normal data.
        """
        if extended is None:
            b = self.recv_buffer
        else:
            if self.extended_recv_buffer.has_key(extended):
                b = self.extended_recv_buffer[extended]
            else:
                return False
        if b and b.fifo.peek() != '':
            return True
        else:
            return False

    def _check_window_adjust(self):
        if self.window_data_left < self.window_size/2:
            # Increase the window so that the other side may send more data.
            self.send_window_adjustment(self.window_size - self.window_data_left)

    def read(self, bytes, extended=None):
        """read(self, bytes, extended=None) -> data
        Read data off the channel.
        Reads at most <bytes> bytes.  It may return less than <bytes> even
        if there is more data in the buffer.

        <bytes>: Number of bytes to read.
        <extended>: data_type_code of extended data type to read.
                    Set to None to read normal data.
        """
        if extended is not None:
            if not self.extended_recv_buffer.has_key(extended):
                self.extended_recv_buffer[extended] = Buffer()
            b = self.extended_recv_buffer[extended]
        else:
            b = self.recv_buffer
        result = b.read_at_most(bytes)
        # Only adjust the window when the buffer is clear.
        if not b:
            self._check_window_adjust()
        return result

    def read_exact(self, bytes, extended=None):
        """read_exact(self, bytes, extended=None) -> data
        Read exactly <bytes> number of bytes off the channel.
        May return less than <bytes> bytes if EOF is reached.

        <bytes>: Number of bytes to read.  Blocks until enough data is
                 available.
        <extended>: data_type_code of extended data type to read.
                    Set to None to read normal data.
        """
        if extended is not None:
            if not self.extended_recv_buffer.has_key(extended):
                self.extended_recv_buffer[extended] = Buffer()
            b = self.extended_recv_buffer[extended]
        else:
            b = self.recv_buffer

        result = []
        bytes_left = bytes
        while bytes_left > 0:
            data = b.read_at_most(bytes_left)
            if not data:
                if result:
                    return ''.join(result)
                else:
                    raise EOFError
            result.append(data)
            bytes_left -= len(data)
            # Only adjust the window when the buffer is clear.
            if not b:
                self._check_window_adjust()
        return ''.join(result)

    # Make an alias for convenience.
    recv = read

    def send(self, data):
        """send(self, data) -> None
        Send the given data string.
        """
        data_start = 0
        while data_start < len(data):
            if self.remote_channel.closed:
                raise Channel_Closed_Error
            while self.remote_channel.window_data_left==0:
                # Currently waiting for window update.
                self.window_data_added_cv.wait()
                # check again inside loop since if we're closed, the window
                # might never update
                if self.remote_channel.closed:
                    raise Channel_Closed_Error
            # Send what we can.
            max_size = min(self.remote_channel.window_data_left, self.remote_channel.max_packet_size)
            data_to_send = data[data_start:data_start+max_size]
            data_start += max_size

            pkt = packet.pack_payload(SSH_MSG_CHANNEL_DATA_PAYLOAD,
                                                (SSH_MSG_CHANNEL_DATA,
                                                 self.remote_channel.channel_id,
                                                 data_to_send))
            self.transport.debug.write(debug.DEBUG_3, 'channel %i window lowered by %i to %i', (self.remote_channel.channel_id, len(data_to_send), self.remote_channel.window_data_left))
            self.remote_channel.window_data_left -= len(data_to_send)
            self.transport.send_packet(pkt)

    def send_extended(self, data, data_type_code):
        """send_extended(self, data, data_type_code) -> None
        Send the given data string as extended data with the given data_type_code.
        """
        data_start = 0

        while data_start < len(data):
            if self.remote_channel.closed:
                raise Channel_Closed_Error
            while self.remote_channel.window_data_left==0:
                # Currently waiting for window update.
                self.window_data_added_cv.wait()
                # check again inside loop since if we're closed, the window
                # might never update
                if self.remote_channel.closed:
                    raise Channel_Closed_Error

            # Send what we can.
            max_size = min(self.remote_channel.window_data_left, self.remote_channel.max_packet_size)
            data_to_send = data[data_start:data_start+max_size]
            data_start += max_size

            pkt = packet.pack_payload(SSH_MSG_CHANNEL_EXTENDED_DATA_PAYLOAD,
                                                (SSH_MSG_CHANNEL_EXTENDED_DATA,
                                                 self.remote_channel.channel_id,
                                                 data_type_code,
                                                 data_to_send))
            self.remote_channel.window_data_left -= len(data_to_send)
            self.transport.send_packet(pkt)

    def channel_request_success(self):
        """channel_request_success(self) -> None
        This is called whenever a CHANNEL_SUCCESS message is received.
        """
        self.channel_request_cv.wake_one(args=True)

    def send_channel_request_success (self):
        self.transport.send (SSH_MSG_CHANNEL_SUCCESS_PAYLOAD, (SSH_MSG_CHANNEL_SUCCESS, self.remote_channel.channel_id))

    def channel_request_failure(self):
        """channel_request_success(self) -> None
        This is called whenever a CHANNEL_FAILURE message is received.
        """
        self.channel_request_cv.wake_one(args=False)

    def send_channel_request_failure (self):
        self.transport.send (SSH_MSG_CHANNEL_FAILURE_PAYLOAD, (SSH_MSG_CHANNEL_FAILURE, self.remote_channel.channel_id))

    def channel_open_success(self, data):
        """channel_open_success(self, data) -> None
        Indicates the channel is opened.

        <data> is a tuple of the data elements specific to this channel type.
        """
        # Default is to ignore any extra data.
        assert len(self.channel_open_cv)==1
        self.channel_open_cv.wake_one((True, data))

    def channel_open_failure(self, reason_code, reason_text, language):
        """channel_open_failure(self, reason_code, reason_text, language) -> None
        This is called when opening a channel fails.
        """
        assert len(self.channel_open_cv)==1
        self.channel_open_cv.wake_one((False, (reason_code, reason_text, language)))

class Remote_Channel:
    channel_id = 0
    window_size = 131072 # 128k
    max_packet_size = 131072 # 128k

    # This is how many bytes I can send to the remote side.
    # Once it hits zero, I start buffering data.
    window_data_left = window_size

    closed = 1
    eof = 1
