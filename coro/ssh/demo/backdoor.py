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

server_key_pri = """
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACDYaUFlkTs33hn1vYPaIOAoBaFhETM1WblgNIEehS6RwwAAAJDPpxNBz6cT
QQAAAAtzc2gtZWQyNTUxOQAAACDYaUFlkTs33hn1vYPaIOAoBaFhETM1WblgNIEehS6Rww
AAAEAmllCCIf5nt6CnNjHL2p7zJ6FmJMxDwkZa2neJEmEEANhpQWWROzfeGfW9g9og4CgF
oWERMzVZuWA0gR6FLpHDAAAADXJ1c2hpbmdAcnl6ZW4=
-----END OPENSSH PRIVATE KEY-----
"""

ks = OpenSSH_Key_Storage()
server_key_ob = ks.parse_private_key (server_key_pri)

# will authenticate user 'foo' with password 'bar' for the
# 'ssh-connection' service [the only service currently supported]
pwd_auth = coro.ssh.auth.userauth.Password_Authenticator ({b'foo': {b'ssh-connection': b'bar'}})

# how to add public-key authentication:
#
#   user_key_pub = """ssh-dss AAAAB...Stc= username@hostname.domain\n"""
#   user_key_ob = ks.parse_public_key (user_key_pub)
#   pubkey_auth = coro.ssh.auth.userauth.Public_Key_Authenticator ({'luser': { 'ssh-connection' : [user_key_ob]}})
#
# add/replace <pubkey_auth> to the list "[pwd_auth]" below...

def usage():
    print ('backdoor.py [-p port]')

def main():

    login_username = None
    ip = None
    port = 8022
    #from coro.ssh.util.debug import Debug
    #Debug.level = 5

    try:
        optlist, args = getopt.getopt(sys.argv[1:], 'p:')
    except getopt.GetoptError as why:
        print (str(why))
        usage()
        sys.exit(1)

    for option, value in optlist:
        if option == '-p':
            port = int (value)

    coro.spawn (coro.backdoor.ssh_server, port, '', server_key_ob, [pwd_auth])
    coro.event_loop()

if __name__ == '__main__':
    main()
