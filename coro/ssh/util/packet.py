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
# ssh_packet
#
# This module implements features to pack and unpack SSH packets.

# Format Codes
BYTE = 'byte'
BOOLEAN = 'boolean'
UINT32 = 'uint32'
UINT64 = 'uint64'
STRING = 'string'
MPINT = 'mpint'
NAME_LIST = 'name-list'
FIXED_STRING = 'fixed-string'

import struct
import mpint
import types

def unpack_payload(format, payload, offset=0):
    """unpack_payload(format, payload, offset=0) -> items
    Unpacks an SSH payload.

    <format> is a list of Format Codes.
    <payload> is the SSH payload.
    <offset> is the character offset into <payload> to start.
    """
    return unpack_payload_get_offset(format, payload, offset)[0]

def unpack_payload_get_offset(format, payload, offset=0):
    """unpack_payload_get_offset(format, payload, offset=0) -> items, index_where_scanning_stopped
    Unpacks an SSH payload.

    <format> is a list of Format Codes.
    <payload> is the SSH payload.
    <offset> is the character offset into <payload> to start.
    """
    i = offset   # Index into payload
    result = []
    for value_type in format:
        if value_type is BYTE:
            result.append(payload[i])
            i += 1
        elif value_type is BOOLEAN:
            result.append(ord(payload[i]) and 1 or 0)
            i += 1
        elif value_type is UINT32:
            result.append(struct.unpack('>I', payload[i:i+4])[0])
            i += 4
        elif value_type is UINT64:
            result.append(struct.unpack('>Q', payload[i:i+8])[0])
            i += 8
        elif value_type is STRING:
            str_len = struct.unpack('>I', payload[i:i+4])[0]
            i += 4
            result.append(payload[i:i+str_len])
            i += str_len
        elif value_type is MPINT:
            mpint_len = struct.unpack('>I', payload[i:i+4])[0]
            i += 4
            value = payload[i:i+mpint_len]
            i += mpint_len
            result.append(mpint.unpack_mpint(value))
        elif value_type is NAME_LIST:
            list_len = struct.unpack('>I', payload[i:i+4])[0]
            i += 4
            result.append(payload[i:i+list_len].split(','))
            i += list_len
        elif type(value_type) is types.TupleType:
            if value_type[0] is FIXED_STRING:
                str_len = value_type[1]
                result.append(payload[i:i+str_len])
                i += str_len
        else:
            raise ValueError, value_type
    return result, i

def pack_payload(format, values):
    """pack_payload(format, values) -> packet_str
    Creates an SSH payload.

    <format> is a list Format Codes.
    <values> is a tuple of values to use.
    """
    packet = [''] * len(format)
    if __debug__:
        assert(len(values) == len(format))
    i = 0
    for value_type in format:
        if value_type is BYTE:
            if type(values[i]) is types.StringType:
                if __debug__:
                    assert(len(values[i]) == 1)
                packet[i] = values[i]
            else:
                packet[i] = chr(values[i])
        elif value_type is BOOLEAN:
            packet[i] = chr(values[i] and 1 or 0)
        elif value_type is UINT32:
            packet[i] = struct.pack('>I', values[i])
        elif value_type is UINT64:
            packet[i] = struct.pack('>Q', values[i])
        elif value_type is STRING:
            packet[i] = struct.pack('>I', len(values[i])) + values[i]
        elif value_type is MPINT:
            n = mpint.pack_mpint(values[i])
            packet[i] = struct.pack('>I', len(n)) + n
        elif value_type is NAME_LIST:
            # We could potentially check for validity here.
            # Names should be at least 1 byte long and should not
            # contain commas.
            s = ','.join(values[i])
            packet[i] = struct.pack('>I', len(s)) + s
        elif type(value_type) is types.TupleType and value_type[0] is FIXED_STRING:
            packet[i] = values[i]
        else:
            raise ValueError, value_type
        i += 1
    return ''.join(packet)

# Packet format definitions.
PAYLOAD_MSG_DISCONNECT = (
    BYTE,
    UINT32,   # reason code
    STRING,   # description
    STRING    # language tag
    )

PAYLOAD_MSG_IGNORE = (
    BYTE,
    STRING    # data
    )

PAYLOAD_MSG_UNIMPLEMENTED = (
    BYTE,
    UINT32     # packet sequence number of rejected message
    )

PAYLOAD_MSG_DEBUG = (
    BYTE,
    BOOLEAN,   # always_display
    STRING,    # message
    STRING     # language tag
    )

PAYLOAD_MSG_KEXINIT = (
    BYTE,
    (FIXED_STRING, 16),# cookie
    NAME_LIST,        # kex_algorithms
    NAME_LIST,        # server_host_key_algorithms
    NAME_LIST,        # encryption_algorithms_client_to_server
    NAME_LIST,        # encryption_algorithms_server_to_client
    NAME_LIST,        # mac_algorithms_client_to_server
    NAME_LIST,        # mac_algorithms_server_to_client
    NAME_LIST,        # compression_algorithms_client_to_server
    NAME_LIST,        # compression_algorithms_server_to_client
    NAME_LIST,        # languages_client_to_server
    NAME_LIST,        # languages_server_to_client
    BOOLEAN,          # first_kex_packet_follows
    UINT32            # 0 (reserved for future extension)
    )

PAYLOAD_MSG_NEWKEYS = (BYTE,)
PAYLOAD_MSG_SERVICE_REQUEST = (BYTE, STRING)     # service name
PAYLOAD_MSG_SERVICE_ACCEPT = (BYTE, STRING)     # service_name

import unittest

class ssh_packet_test_case(unittest.TestCase):
    pass

class unpack_test_case(ssh_packet_test_case):

    def runTest(self):
        # KEXINIT packet grabbed from my OpenSSH server.
        sample_packet = '\024\212a\330\261\300}.\252b%~\006j\242\356\367\000\000\000=diffie-hellman-group-exchange-sha1,diffie-hellman-group1-sha1\000\000\000\007ssh-dss\000\000\000\207aes128-cbc,3des-cbc,blowfish-cbc,cast128-cbc,arcfour,aes192-cbc,aes256-cbc,rijndael-cbc@lysator.liu.se,aes128-ctr,aes192-ctr,aes256-ctr\000\000\000\207aes128-cbc,3des-cbc,blowfish-cbc,cast128-cbc,arcfour,aes192-cbc,aes256-cbc,rijndael-cbc@lysator.liu.se,aes128-ctr,aes192-ctr,aes256-ctr\000\000\000Uhmac-md5,hmac-sha1,hmac-ripemd160,hmac-ripemd160@openssh.com,hmac-sha1-96,hmac-md5-96\000\000\000Uhmac-md5,hmac-sha1,hmac-ripemd160,hmac-ripemd160@openssh.com,hmac-sha1-96,hmac-md5-96\000\000\000\011none,zlib\000\000\000\011none,zlib\000\000\000\000\000\000\000\000\000\000\000\000\000'
        msg, cookie, kex_algorithms, server_host_key_algorithms, encryption_algorithms_c2s, \
            encryption_algorithms_s2c, mac_algorithms_c2s, mac_algorithms_s2c, \
            compression_algorithms_c2s, compression_algorithms_s2c, \
            languages_c2s, languages_s2c, first_kex_packet_follows, reserved = unpack_payload(
                PAYLOAD_MSG_KEXINIT, sample_packet)

def suite():
    suite = unittest.TestSuite()
    suite.addTest(unpack_test_case())
    return suite

if __name__ == '__main__':
    unittest.main(module='ssh_packet', defaultTest='suite')
