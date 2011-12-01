# -*- Mode: Python -*-

# simple ftp client

import dnsqr
import dns_exceptions
import read_stream
import coro
import re
import socket

send_timeout = 800
recv_timeout = 800
connect_timeout = 800

class ftp_error (Exception):
    pass

class ftp_client:

    pasv_mode = 1
    ftp_port = 21
    debug = 0

    def __init__ (self, local_ip=None):
        """__init__(local_ip=None) -> ftp_client
        Creates a new ftp_client.  Binds to the local_ip if it is given.
        NOTE: You MUST del the stream object when you are done, or this will leak.
        """
        self.local_ip = local_ip
        self.s = coro.make_socket (socket.AF_INET, socket.SOCK_STREAM)
        if local_ip:
            self.s.bind((local_ip,0))
        self.stream = read_stream.stream_reader (self.recv)

    def recv (self, size):
        global recv_timeout
        return coro.with_timeout (recv_timeout, self.s.recv, size)

    def send (self, data):
        global send_timeout
        return coro.with_timeout (send_timeout, self.s.send, data)

    def debug_line (self, line):
        coro.print_stderr (line + '\n')

    ip_re = re.compile ('[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}')

    def connect (self, host):
        global connect_timeout
        if not self.ip_re.match (host):
            ip = dnsqr.query(host,'A')
            if ip:
                # pull out the ip of the first entry
                ip = ip[0][1]
            else:
                # no results found for this entry
                raise dns_exceptions.DNS_Hard_Error
        else:
            ip = host
        coro.with_timeout (connect_timeout, self.s.connect, (ip, self.ftp_port))
        self.read_response ('2')

    def _read_response (self):
        multiline = 0
        response = []
        while 1:
            line, eof = self.stream.read_line()
            if eof:
                raise EOFError
            if self.debug:
                self.debug_line ('<= %s' % line)
            cont = line[3:4]
            if multiline and line[0:4] == '    ':
                response.append (line[4:])
            elif cont == ' ':
                response.append (line[4:])
                return line[0:3], response
            elif cont == '-':
                response.append (line[4:])
                multiline = 1
            else:
                raise ftp_error, line

    def read_response (self, expect):
        code, response = self._read_response()
        if code[0] != expect:
            raise ftp_error, (code, response)
        else:
            return response

    def command (self, command, expect):
        "send a synchronous FTP command; expecting to receive reply code <expect>"
        if self.debug:
            self.debug_line ('=> %s' % command)
        self.send (command + '\r\n')
        return self.read_response (expect)

    def cmd_user (self, username):
        self.command ('USER %s' % username, '3')

    def cmd_pass (self, password):
        self.command ('PASS %s' % password, '2')

    pasv_re = re.compile ('.*\(([0-9]{1,3},[0-9]{1,3},[0-9]{1,3},[0-9]{1,3},[0-9]{1,3},[0-9]{1,3})\)')

    def parse_pasv_reply (self, reply):
        m = self.pasv_re.match (reply[-1])
        if not m:
            raise ftp_error, "unable to parse PASV reply: %r" % reply
        else:
            nums = m.groups()[0].split (',')
            ip = nums[:4]
            ip = '.'.join (nums[:4])
            port = map (int, nums[4:6])
            port = port[0]<< 8 | port[1]
            return ip, port

    def make_data_channel (self):
        global connect_timeout
        if self.pasv_mode:
            reply = self.command ('PASV', '2')
            ip, port = self.parse_pasv_reply (reply)
            dc = coro.make_socket (socket.AF_INET, socket.SOCK_STREAM)
            if self.local_ip:
                dc.bind((self.local_ip, 0))
            if self.debug:
                coro.print_stderr ('connecting to %s:%s\n' % (ip, port))
            coro.with_timeout (connect_timeout, dc.connect, (ip, port))
            return dc
        else:
            raise ftp_error, "non-pasv transfers not yet implemented"

    def read_from_data_channel (self, dc, block_reader):
        global recv_timeout
        while 1:
            block = coro.with_timeout (recv_timeout, dc.recv, 8192)
            if not block:
                break
            else:
                block_reader (block)

    def write_to_data_channel (self, dc, block_writer):
        global send_timeout
        try:
            while 1:
                block = block_writer()
                if not block:
                    break
                else:
                    coro.with_timeout (send_timeout, dc.send, block)
        finally:
            dc.close()

    def cmd_retr (self, filename, block_reader):
        conn = self.make_data_channel()
        self.command ('RETR %s' % filename, '1')
        self.read_from_data_channel (conn, block_reader)
        self.read_response ('2')

    def cmd_list (self, block_reader):
        conn = self.make_data_channel()
        self.command ('LIST', '1')
        self.read_from_data_channel (conn, block_reader)
        self.read_response ('2')

    def cmd_stor (self, filename, block_writer):
        conn = self.make_data_channel()
        self.command ('STOR %s' % filename, '1')
        self.write_to_data_channel (conn, block_writer)
        self.read_response ('2')

    def cmd_quit (self):
        self.command ('QUIT', '2')
        self.s.close()

    def cmd_cwd (self, dir):
        self.command ('CWD %s' % dir, '2')

    def cmd_pwd (self):
        return self.command ('PWD', '2')

    def cmd_type (self, type='I'):
        return self.command ('TYPE %s' % type, '2')

def test1():
    coro.print_stderr ("waiting 5 seconds...\n")
    coro.sleep_relative (5)
    f = ftp_client()
    coro.print_stderr ("connecting...\n")
    f.connect ('squirl.nightmare.com')
    coro.print_stderr ("logging in...\n")
    f.cmd_user ('anonymous')
    f.cmd_pass ('rushing@')
    blocks = []
    coro.print_stderr ("retrieving directory listing...\n")
    f.cmd_list (blocks.append)
    coro.print_stderr ("done.\n")
    f.cmd_quit()
    coro.print_stderr ('-'*20 + '\n')
    coro.print_stderr (''.join (blocks))
    coro.print_stderr ('-'*20 + '\n')

def test2():
    coro.sleep_relative (5)
    f = ftp_client()
    coro.print_stderr ("connecting...\n")
    f.connect ('10.1.1.209')
    coro.print_stderr ("logging in...\n")
    f.cmd_user ('ftpguy')
    f.cmd_pass ('ftpguy')
    f.cmd_type ('I')
    coro.print_stderr ("sending file...\n")
    file = open ('ftp_client.py', 'rb')
    thunk = (lambda f=file: f.read (8192))
    f.cmd_stor ('a_file.txt', thunk)
    coro.print_stderr ("done.\n")
    f.cmd_quit()

if __name__ == '__main__':
    import backdoor
    coro.spawn (backdoor.serve)
    coro.spawn (test2)
    coro.event_loop (30.0)
