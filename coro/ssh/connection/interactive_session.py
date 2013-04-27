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
# ssh.connect.interactive_session
#
# This implements the "session" channel of the ssh_connect service.
#

__version__ = '$Revision: #1 $'

import channel
import ssh.util.packet
from connect import *

class Interactive_Session(channel.Channel):
    name = 'session'

    def send_environment_variable(self, name, value):
        self.send_channel_request('env', ENV_CHANNEL_REQUEST_PAYLOAD,
                                            (name,
                                             value))

class Interactive_Session_Client(Interactive_Session):

    def open_pty(self, term='', width_char=0, height_char=0, width_pixels=0, height_pixels=0, modes=''):
        self.send_channel_request('pty-req', PTY_CHANNEL_REQUEST_PAYLOAD,
                                                (term,
                                                 width_char,
                                                 height_char,
                                                 width_pixels,
                                                 height_pixels,
                                                 modes))

    def open_shell(self):
        self.send_channel_request('shell', (), ())

    def exec_command(self, command):
        self.send_channel_request('exec', EXEC_CHANNEL_REQUEST_PAYLOAD, (command,))

class Interactive_Session_Server(Interactive_Session):

    def handle_request(self, request_type, want_reply, type_specific_packet_data):
        if self.request_handlers.has_key(request_type):
            f = self.request_handlers[request_type]
            f(want_reply, type_specific_packet_data)
        else:
            if want_reply:
                packet = ssh.util.packet.pack_payload(SSH_MSG_CHANNEL_FAILURE_PAYLOAD, (self.remote_channel.channel_id,))
                self.transport.send_packet(packet)


    def handle_pty_request(self, want_reply, type_specific_packet_data):
        term, width_char, height_char, width_pixels, height_pixels, modes = ssh.util.packet.unpack_payload(PTY_CHANNEL_REQUEST_PAYLOAD, type_specific_packet_data)
        # XXX: NOT FINISHED

    def handle_x11_request(self, want_reply, type_specific_packet_data):
        single_connection, auth_protocol, auth_cookie, screen_number = ssh.util.packet.unpack_payload(X11_CHANNEL_REQUEST_PAYLOAD, type_specific_packet_data)
        # XXX: NOT FINISHED

    request_handlers = {'pty-req':  handle_pty_request,
                        'x11-req':  handle_x11_request,
                       }

PTY_CHANNEL_REQUEST_PAYLOAD = (ssh.util.packet.STRING,   # TERM environment variable value (e.g., vt100)
                               ssh.util.packet.UINT32,   # terminal width, characters (e.g., 80)
                               ssh.util.packet.UINT32,   # terminal height, rows (e.g., 24)
                               ssh.util.packet.UINT32,   # terminal width, pixels (e.g., 640)
                               ssh.util.packet.UINT32,   # terminal height, pixels (e.g., 480)
                               ssh.util.packet.STRING)   # encoded terminal modes

X11_CHANNEL_REQUEST_PAYLOAD = (ssh.util.packet.BOOLEAN,  # single connection
                               ssh.util.packet.STRING,   # x11 authentication protocol
                               ssh.util.packet.STRING,   # x11 authentication cookie
                               ssh.util.packet.UINT32)   # x11 screen number

ENV_CHANNEL_REQUEST_PAYLOAD = (ssh.util.packet.STRING,   # variable name
                               ssh.util.packet.STRING)   # variable value

EXEC_CHANNEL_REQUEST_PAYLOAD = (ssh.util.packet.STRING,) # command