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

import channel
from coro.ssh.util import packet as ssh_packet
from connect import *

from coro import write_stderr as W

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

    def handle_request(self, request_type, want_reply, type_specific_packet_data):
        # W ('interactive_session_client: handle_request %r %r %r\n' %
        #    (request_type, want_reply, type_specific_packet_data))
        if request_type in self.request_handlers:
            self.request_handlers[request_type] (self, want_reply, type_specific_packet_data)
        elif want_reply:
            packet = ssh_packet.pack_payload(SSH_MSG_CHANNEL_FAILURE_PAYLOAD, (self.remote_channel.channel_id,))
            self.transport.send_packet(packet)

    exit_status = None

    def handle_exit_status(self, want_reply, type_specific_packet_data):
        self.exit_status = ssh_packet.unpack_payload(EXIT_STATUS_PAYLOAD, type_specific_packet_data)

    exit_signal = None

    def handle_exit_signal(self, want_reply, type_specific_packet_data):
        self.exit_signal = ssh_packet.unpack_payload(EXIT_SIGNAL_PAYLOAD, type_specific_packet_data)

    request_handlers = {
        'exit-status': handle_exit_status,
        'exit-signal': handle_exit_signal,
    }


# I think to do anything useful here we'll need full terminal emulation like
# http://liftoff.github.io/GateOne/Developer/terminal.html from RFC4254 section 8
pty_modes = {
    0: ('TTY_OP_END', "Indicates end of options."),
    1: ('VINTR', ("Interrupt character; 255 if none.  Similarly for the other characters."
                  " Not all of these characters are supported on all systems.")),
    2: ('VQUIT', "The quit character (sends SIGQUIT signal on POSIX systems)."),
    3: ('VERASE', "Erase the character to left of the cursor."),
    4: ('VKILL', "Kill the current input line."),
    5: ('VEOF', "End-of-file character (sends EOF from the terminal)."),
    6: ('VEOL', "End-of-line character in addition to carriage return and/or linefeed."),
    7: ('VEOL2', "Additional end-of-line character."),
    8: ('VSTART', "Continues paused output (normally control-Q)."),
    9: ('VSTOP', "Pauses output (normally control-S)."),
    10: ('VSUSP', "Suspends the current program."),
    11: ('VDSUSP', "Another suspend character."),
    12: ('VREPRINT', "Reprints the current input line."),
    13: ('VWERASE', "Erases a word left of cursor."),
    14: ('VLNEXT', "Enter the next character typed literally, even if it is a special character"),
    15: ('VFLUSH', "Character to flush output."),
    16: ('VSWTCH', "Switch to a different shell layer."),
    17: ('VSTATUS', "Prints system status line (load, command, pid, etc)."),
    18: ('VDISCARD', "Toggles the flushing of terminal output."),
    30: ('IGNPAR', "The ignore parity flag.  The parameter SHOULD be 0 if this flag is FALSE, and 1 if it is TRUE."),
    31: ('PARMRK', "Mark parity and framing errors."),
    32: ('INPCK', "Enable checking of parity errors."),
    33: ('ISTRIP', "Strip 8th bit off characters."),
    34: ('INLCR', "Map NL into CR on input."),
    35: ('IGNCR', "Ignore CR on input."),
    36: ('ICRNL', "Map CR to NL on input."),
    37: ('IUCLC', "Translate uppercase characters to lowercase."),
    38: ('IXON', "Enable output flow control."),
    39: ('IXANY', "Any char will restart after stop."),
    40: ('IXOFF', "Enable input flow control."),
    41: ('IMAXBEL', "Ring bell on input queue full."),
    50: ('ISIG', "Enable signals INTR, QUIT, [D]SUSP."),
    51: ('ICANON', "Canonicalize input lines."),
    52: ('XCASE', "Enable input and output of uppercase characters by preceding their lowercase equivalents '\'."),
    53: ('ECHO', "Enable echoing."),
    54: ('ECHOE', "Visually erase chars."),
    55: ('ECHOK', "Kill character discards current line."),
    56: ('ECHONL', "Echo NL even if ECHO is off."),
    57: ('NOFLSH', "Don't flush after interrupt."),
    58: ('TOSTOP', "Stop background jobs from output."),
    59: ('IEXTEN', "Enable extensions."),
    60: ('ECHOCTL', "Echo control characters as ^(Char)."),
    61: ('ECHOKE', "Visual erase for line kill."),
    62: ('PENDIN', "Retype pending input."),
    70: ('OPOST', "Enable output processing."),
    71: ('OLCUC', "Convert lowercase to uppercase."),
    72: ('ONLCR', "Map NL to CR-NL."),
    73: ('OCRNL', "Translate carriage return to newline (output)."),
    74: ('ONOCR', "Translate newline to carriage return-newline (output)."),
    75: ('ONLRET', "Newline performs a carriage return (output)."),
    90: ('CS7', "7 bit mode."),
    91: ('CS8', "8 bit mode."),
    92: ('PARENB', "Parity enable."),
    93: ('PARODD', "Odd parity, else even."),
    128: ('TTY_OP_ISPEED', "Specifies the input baud rate in bits per second."),
    129: ('TTY_OP_OSPEED', "Specifies the output baud rate in bits per second."),
}

class PTY:
    def __init__ (self, settings):
        self.term, self.width_char, self.height_char, self.width_pixels, self.height_pixels, self.modes = settings
        # self.unpack_modes()

    def unpack_modes (self):
        import struct
        i = 0
        modes = self.modes
        while i < len (modes):
            opcode = ord (modes[i])
            i += 1
            if opcode >= 160:
                break
            elif pty_modes.has_key (opcode):
                name, description = pty_modes[opcode]
                value, = struct.unpack ('>L', modes[i:i + 4])
                setattr (self, name, value)
                i += 4
                # W ('PTY setting: %r = %r\n' % (name, value))
            else:
                # W ('unknown PTY setting: %r = %r\n' % (opcode, struct.unpack ('>L', modes[i:i+4])))
                i += 4

class Interactive_Session_Server(Interactive_Session):

    def handle_request(self, request_type, want_reply, type_specific_packet_data):
        # W ('interactive_session_server: handle_request %r %r %r\n' %
        #    (request_type, want_reply, type_specific_packet_data))
        if request_type in self.request_handlers:
            self.request_handlers[request_type] (self, want_reply, type_specific_packet_data)
        elif want_reply:
            packet = ssh_packet.pack_payload(SSH_MSG_CHANNEL_FAILURE_PAYLOAD, (self.remote_channel.channel_id,))
            self.transport.send_packet(packet)

    # by default, refuse PTY requests, a lot of terminal smarts are needed to do it right.
    accept_pty = False

    def handle_pty_request(self, want_reply, type_specific_packet_data):
        self.pty = PTY (ssh_packet.unpack_payload(PTY_CHANNEL_REQUEST_PAYLOAD, type_specific_packet_data))
        if want_reply:
            if self.accept_pty:
                self.send_channel_request_success()
            else:
                self.send_channel_request_failure()

    def handle_x11_request(self, want_reply, type_specific_packet_data):
        single_connection, auth_protocol, auth_cookie, screen_number = ssh_packet.unpack_payload(
            X11_CHANNEL_REQUEST_PAYLOAD, type_specific_packet_data)
        # XXX fantasize about doing X11 forwarding here?  I think not.
        if want_reply:
            self.send_channel_request_failure()

    def handle_shell_request(self, want_reply, type_specific_packet_data):
        # XXX whatever, sure, it worked.
        if want_reply:
            self.send_channel_request_success()

    request_handlers = {
        'pty-req': handle_pty_request,
        'x11-req': handle_x11_request,
        'shell': handle_shell_request,
        # env :
        # exec :
        # subsystem :
    }

PTY_CHANNEL_REQUEST_PAYLOAD = (
    ssh_packet.STRING,         # TERM environment variable value (e.g., vt100)
    ssh_packet.UINT32,         # terminal width, characters (e.g., 80)
    ssh_packet.UINT32,         # terminal height, rows (e.g., 24)
    ssh_packet.UINT32,         # terminal width, pixels (e.g., 640)
    ssh_packet.UINT32,         # terminal height, pixels (e.g., 480)
    ssh_packet.STRING,         # encoded terminal modes
)

X11_CHANNEL_REQUEST_PAYLOAD = (
    ssh_packet.BOOLEAN,         # single connection
    ssh_packet.STRING,          # x11 authentication protocol
    ssh_packet.STRING,          # x11 authentication cookie
    ssh_packet.UINT32,          # x11 screen number
)

ENV_CHANNEL_REQUEST_PAYLOAD = (
    ssh_packet.STRING,          # variable name
    ssh_packet.STRING,          # variable value
)

EXEC_CHANNEL_REQUEST_PAYLOAD = (
    ssh_packet.STRING,          # command
)

EXIT_STATUS_PAYLOAD = (
    ssh_packet.UINT32,          # exit_status
)

EXIT_SIGNAL_PAYLOAD = (
    ssh_packet.STRING,          # signal name
    ssh_packet.BOOLEAN,         # core dumped
    ssh_packet.STRING,          # error message
    ssh_packet.STRING,          # language tag
)
