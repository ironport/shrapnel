# -*- Mode: Python -*-

import coro.ssh.transport.server
import coro.ssh.connection.connect
import coro.ssh.l4_transport.coro_socket_transport
import coro.ssh.auth.userauth
import coro.ssh.connection.interactive_session

import coro
import coro.backdoor

import getopt
import socket
import sys


from coro.ssh.keys.openssh_key_storage import OpenSSH_Key_Storage

server_key_pri = """-----BEGIN DSA PRIVATE KEY-----
MIIBuwIBAAKBgQDTfwvvQo0WnUmZpnUFmqF/TXSXFaJ1NKbBLQXPh8dhHgTN1uFO
ZibFXMKpDHLCGCdGRm5eHansB9hu2+nNoaFf3oLDHc8ctuE7xRHT8x174D2AxcnX
r0Fw3BnZHj58lLlhayDJ4S6W77yefGEOuo/wKUEPjAUBCrvxKq3bKAeVUQIVAPpR
bJO1QQZPlj4w+MXmRTgW7wGfAoGAVUkBIX+RLrh9guyiAadi9xGk8S7n5w2PbcsP
KTG8x/ttCDEuaBp6El6qt86cA+M2GPvXjuMGR5BQT8IOaWS7Aw2+J1IamLCsrPfq
oiQvz3cqxOAutuIuorzbIAgVo0hiAyovZE4u2zzKeci7OtfD8pRThSby4Dgbkeix
FQFhW08CgYBSxcduHDSqJTCjFK4hwTlNck4h2hC1E4xuMfxYsUZkLrBAsD3nzU2W
jNoZppTz3W8XC7YnTxonncXNWxCWsDWpvs0b2zGj7uUvGRtlyxtQpybyN3LZ0flo
DssTygy7t0KlS7T2a1IhqiVDbrSUoGXz+Wp/z66lCpSLTlPsGpLeLwIVAMQldwwH
OekNfzzIBr6QkMvmIOuL
-----END DSA PRIVATE KEY-----
"""

ks = OpenSSH_Key_Storage()
server_key_ob = ks.parse_private_key (server_key_pri)

# will authentication user 'foo' with password 'bar' for the 'ssh-connection' service [the only service currently supported]
pwd_auth = coro.ssh.auth.userauth.Password_Authenticator ({'foo' : { 'ssh-connection' : 'bar' } })

# how to add public-key authentication:
#
#   user_key_pub = """ssh-dss AAAAB...Stc= username@hostname.domain\n"""
#   user_key_ob = ks.parse_public_key (user_key_pub)
#   pubkey_auth = coro.ssh.auth.userauth.Public_Key_Authenticator ({'luser': { 'ssh-connection' : [user_key_ob]}})
#
# add/replace <pubkey_auth> to the list "[pwd_auth]" below...

def usage():
    print 'backdoor.py [-p port]'

def main():

    login_username = None
    ip = None
    port = 8022

    try:
        optlist, args = getopt.getopt(sys.argv[1:], 'p:')
    except getopt.GetoptError, why:
        print str(why)
        usage()
        sys.exit(1)

    for option, value in optlist:
        if option=='-p':
            port = int (value)

    coro.spawn (coro.backdoor.ssh_server, port, '', server_key_ob, [pwd_auth])
    coro.event_loop()

if __name__=='__main__':
    main()
