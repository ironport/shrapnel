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
# ssh.keys.openssh_known_hosts
#
# This module handles the known_hosts file.
#

# The known_hosts file has the following format:
# Each line contains a key with the following fields (space separated):
# SSH2:
# list_of_hosts, keytype, key, comment
# SSH1:
# list_of_hosts, number_of_bits, exponent, modulus, comment
#
# hosts is a comma-separated list of hosts.
# '*' and '?' are allowed wildcards.
# A hostname starting with '!' means negation.  If a hostname matches a
# negated pattern, it is not accepted (by that line) even if it matched
# another pattern on the line.
#
# Lines starting with '#' are comments.

# The known_hosts file is found in $HOME/.ssh/known_hosts or
# in $SSHDIR/ssh_known_hosts.
#
# As a historical note, OpenSSH used to have files called known_hosts2
# (or ssh_known_hosts2 for the system-wide version).  This implementation
# does not try to load these copies, since that technique is quite antiquated.

import base64
import binascii
import errno
import os
import re

from coro.ssh.keys import dss, rsa
from coro.ssh.keys import openssh_key_formats
from coro.ssh.keys.key_storage import Host_Key_Changed_Error
from coro.ssh.keys.remote_host import IPv4_Remote_Host_ID

class OpenSSH_Known_Hosts:

    def __init__(self):
        pass

    def get_known_hosts_filenames(self, username):
        # XXX: Support system-wide copy.
        return [self.get_users_known_hosts_filename(username)]

    def get_users_known_hosts_filename(self, username):
        if username is None:
            username = os.getlogin()
        home_dir = os.path.expanduser('~' + username)
        user_known_hosts_filename = os.path.join(home_dir, '.ssh', 'known_hosts')
        return user_known_hosts_filename

    def check_for_host(self, host_id, key, username=None, port=22):
        """check_for_host(self, host_id, key, username=None) -> boolean
        Checks if the given key is in the known_hosts file.
        Returns true if it is, otherwise returns false.
        If the host was found, but the key did not match, it raises a
        Host_Key_Changed_Error exception.

        <username> - May be None to use the current user.

        <host_id> - A IPv4_Remote_Host_ID instance.

        <key> - A SSH_Public_Private_Key instance.
        """

        if not isinstance(host_id, IPv4_Remote_Host_ID):
            raise TypeError(host_id)

        if host_id.hostname is not None:
            hosts = [host_id.ip, host_id.hostname]
        else:
            hosts = [host_id.ip]

        # Changed is a variable to detect a Host_Key_Changed_Error.
        # We store away that the error has occurred so that we can allow
        # other files to potentially have a correct copy.
        changed = None
        for filename in self.get_known_hosts_filenames(username):
            for host in hosts:
                try:
                    if self._check_for_host(filename, host_id, host, port, key):
                        return 1
                except Host_Key_Changed_Error, e:
                    changed = e

        if changed is None:
            return 0
        else:
            raise changed

    def _check_for_host(self, filename, host_id, host, port, key):
        try:
            f = open(filename)
        except IOError:
            return 0

        changed = None
        line_number = 0
        for line in f.readlines():
            line_number += 1
            line = line.strip()
            if len(line) == 0 or line[0] == '#':
                continue
            m = openssh_key_formats.ssh2_known_hosts_entry.match(line)
            if m:
                if key.name == m.group('keytype'):
                    if self._match_host(host, port, m.group('list_of_hosts')):
                        if self._match_key(key, m.group('base64_key')):
                            return 1
                        else:
                            # Found a conflicting key.
                            changed = Host_Key_Changed_Error(host_id, '%s:%i' % (filename, line_number))
            else:
                # Currently not supporting SSH1 style.
                # m = openssh_key_formats.ssh1_key.match(line)
                continue

        if changed is None:
            return 0
        else:
            raise changed

    def _match_host(self, host, port, pattern):
        patterns = pattern.split(',')
        # Negated_Pattern is used to terminate the checks.
        try:
            for p in patterns:
                if self._match_pattern(host, port, p):
                    return 1
        except OpenSSH_Known_Hosts.Negated_Pattern:
            return 0
        return 0

    class Negated_Pattern(Exception):
        pass

    host_with_port = re.compile ('^\\[([^\\]]+)\\]:([0-9]+)')

    def _match_pattern(self, host, port, pattern):
        # XXX: OpenSSH does not do any special work to check IP addresses.
        # It just assumes that it will match character-for-character.
        # Thus, 001.002.003.004 != 1.2.3.4 even though those are technically
        # the same IP.
        if pattern and pattern[0] == '!':
            negate = 1
            pattern = pattern[1:]
        else:
            negate = 0
        if host == pattern:
            if negate:
                raise OpenSSH_Known_Hosts.Negated_Pattern
            else:
                return 1
        # check for host port
        port_probe = self.host_with_port.match (pattern)
        if port_probe:
            # host with port
            host0, port0 = port_probe.groups()
            port0 = int (port0)
            if host == host0 and port == port0:
                if negate:
                    raise OpenSSH_Known_Hosts.Negated_Pattern
                else:
                    return 1
        # Check for wildcards.
        # XXX: Lazy
        # XXX: We could potentially escape other RE-special characters.
        pattern = pattern.replace('.', '[.]')
        # Convert * and ? wildcards into RE wildcards.
        pattern = pattern.replace('*', '.*')
        pattern = pattern.replace('?', '.')
        pattern = pattern + '$'
        r = re.compile(pattern, re.IGNORECASE)
        if r.match(host):
            if negate:
                raise OpenSSH_Known_Hosts.Negated_Pattern
            else:
                return 1
        else:
            return 0

    def _match_key(self, key_obj, base64_key):
        key = key_obj.name + ' ' + base64_key
        # XXX: static or class method would make this instantiation not necessary.
        #      Too bad the syntax sucks.
        from coro.ssh.keys.openssh_key_storage import OpenSSH_Key_Storage
        x = OpenSSH_Key_Storage()
        parsed_key = x.parse_public_key(key)
        if parsed_key.public_key == key_obj.public_key:
            return 1
        else:
            return 0

    def update_known_hosts(self, host, public_host_key, username=None):
        # XXX: Locking
        filename = self.get_users_known_hosts_filename(username)
        tmp_filename = filename + '.tmp'
        try:
            f = open(filename)
        except IOError, why:
            if why.errno == errno.ENOENT:
                f = None
            else:
                raise
        f_tmp = open(tmp_filename, 'w')

        # This is a flag used to indicate that we made the update.
        # If, after parsing through the original known_hosts file, and we
        # have not done the update, then we will just append the new key to
        # the file.
        updated = 0
        if f:
            for line in f.readlines():
                line = line.strip()
                new_line = line
                if len(line) != 0 and line[0] != '#':
                    m = openssh_key_formats.ssh2_known_hosts_entry.match(line)
                    if m:
                        if public_host_key.name == m.group('keytype'):
                            # Same keytype..See if we need to update.
                            # If the key is the same, then just update the host list.
                            # XXX: This code needs to be refactored.
                            base64_key = m.group('base64_key')
                            binary_key = binascii.a2b_base64(base64_key)
                            if public_host_key.name == 'ssh-dss':
                                key_obj = dss.SSH_DSS()
                            elif public_host_key.name == 'ssh-rsa':
                                key_obj = dss.SSH_RSA()
                            else:
                                # This should never happen.
                                raise ValueError(public_host_key.name)
                            host_list = m.group('list_of_hosts')
                            host_list = host_list.split(',')
                            key_obj.set_public_key(binary_key)
                            if key_obj.get_public_key_blob() == public_host_key.get_public_key_blob():
                                # Same key.
                                # Add this host to the list if it is not already there.
                                tmp_host_list = [x.lower() for x in host_list]
                                if host.lower() not in tmp_host_list:
                                    host_list.append(host)
                                comment = m.group('comment')
                                if comment is None:
                                    comment = ''
                                new_line = ','.join(host_list) + ' ' + m.group('keytype') + \
                                    ' ' + m.group('base64_key') + comment
                                updated = 1
                            else:
                                # Keys differ...Remove this host from the list if it was in there.
                                new_host_list = filter(lambda x, y=host.lower(): x.lower() != y, host_list)
                                comment = m.group('comment')
                                if comment is None:
                                    comment = ''
                                new_line = ','.join(new_host_list) + ' ' + m.group('keytype') + \
                                    ' ' + m.group('base64_key') + comment
                    else:
                        # XXX: Support SSH1 keys.
                        pass
                f_tmp.write(new_line + '\n')

        if not updated:
            # Append to the end.
            base64_key = base64.encodestring(public_host_key.get_public_key_blob())
            # Strip the newlines that the base64 module inserts.
            base64_key = base64_key.replace('\n', '')
            f_tmp.write(host + ' ' + public_host_key.name + ' ' + base64_key + '\n')

        if f:
            f.close()
        f_tmp.close()
        # XXX: Permissions??
        os.rename(tmp_filename, filename)


import unittest

class openssh_known_hosts_test_case(unittest.TestCase):
    pass

class check_for_host_test_case(openssh_known_hosts_test_case):

    def runTest(self):
        # Build a sample known_hosts test file.
        tmp_filename = os.tempnam()
        f = open(tmp_filename, 'w')
        f.write("""# Example known hosts file.
10.1.1.108 ssh-dss AAAAB3NzaC1kc3MAAACBAOdTJwlIDyxIKAaCoGr/XsySV8AzJDU2fAePcO7CBURUYyUHS9uKsgsjZw7qBkdnkWT/Yx2Z8k9j+HuJ2L3mI6y9+cknen9ycze6g/UwmYa2+forEz7NXiEWi3lTHXnAXjEpmCWZAB6++HPM9rq+wQluOcN8cks57sttzxzqQG6RAAAAFQCgQ/edsYFn4jEBiJhoj97GElWM0QAAAIAz5hffnGq9zK5rtrNpKVdz6KIEyeXlGd16f6NwotVwpNd2zEXBC3+z13TyMiX35H9m7fWYQen7O7RNekJl5Gz7V6UA7lipNFrhmg/eO6rnXetrrgjdiHF5mSx3O8uBQOU5tK+IyAINtBhDqM6GNEqEkFa9yT6POYjGA8ihSaUUOQAAAIEAvvDYfg+KrBZUlJGMK/g1muBbBu5o+UbppgRTOsEfAMKRovV0vsZc4AIaeh/uGVKS+zXqQHh7btHgTMQ47hxF3tPVFWIgO6vDtsQX90e9xaCfmKQY2EV0Wrq1XUKxOycTNRZ5kCxYkq4qRhs5QnqB/Ov71g7HHxsJ8pnjSDusiNo=
172.16.1.11 ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAIEAvUNY7kd1sDujt9HhdT6VWtf8yVRAw2Ib+M6ptWTuWWnPGR6TP/ZwumSs/rAguyxWrNRbw7Eainr/BTEFATpJRYKUDPZKGHLT3ixtOy7scUVRyaJD7F3L7BujkhHLWOyFJGtoZmJEdQmddGDwq+16gLD06GA8/N8kkQFRR6vwlRs=
64.70.20.70,64.70.44.3 1024 35 162807158017859311401243513535320968370503503816817576276599779420791975206320054411137858395244854129122865069311130487158120563446636918588974972115213166463069362091898230386572857193095086738994217228848073927343769936543295334648942676920084374567042307974866766193585693129128286570059425685457486987781
lists.ironport.com,10.1.1.109 ssh-dss AAAAB3NzaC1kc3MAAACBAOfO0s6KFDk8lU7hJyLWevjEIi9drfn8wJYFvYAc+apN4+Qlq4DtFXMDH8U5pQWpZsj705ywi5cex8aEaeepfeQBe6NQCmJci47cTTnaiy/IR7d2hZkB0LmJJX6JxYWWtk2kFyL4xbPEfXbBpNprTfNzgi32YeeIKak3T3amYo8dAAAAFQDInSP36WJZ7WnH13qBXZM+5USftwAAAIAQ7CHz/hwxpmYNind6Zm7vmFC8JkRdkTjNIfyuHszfgHI3+imhSJJxjaSwdvLNi+2P2cdoTrL45ITPFT0+YSq1VIXclqa0k0kjETFbayGbq9DE3w7S6WBiiewTcllu7NzO9EvaNt3XJUQ7SpvNBoLhv+XAHkdhX0ouwwtyeElT6gAAAIAEcOOSQClq9CIcYEjwtfDBANaJ7o2WfYJMqto+ibjnl+1YFtGw9ofD5gi5gtEIGtSb6mO88ooX9sfmkaAY+1L/gTdb3Fxc3zuL2PymBt1ruNTgVzEjV35h94lgC3+F4mPz0jQpnpsbxhm/uDn/i1BeRBlzMhyWOAHfLknna9WCmg==
!outlaw.qa,*.qa,172.17.0.201 ssh-dss AAAAB3NzaC1kc3MAAACBAPaQAeia7kiuORu9425IyZRKlRPkom9mjEVERjN3Lw5R93rBZSwbl8wiT1PEeBN2047SZD7ucHaAUqAU39l//JVA0Q/RHXczad1niqC7Y7YKSpu3XfI7vpgMd91XIlxNhnhvNLtWfmwuWuX1FFiByKUY7fsHVeKTYwnvRPiv89IBAAAAFQCryy7v2z5Olv1Z0bSoQLDemiSzywAAAIEA3pmx1n0YRuw3hY4RfXbQCUxtu19bldG4XlNnmeIE8cb4tdGHBgLnLrMpSLsA4aMOWAzzDvB/Gk9AlgyNuYp2NaCFStE5yYiK9c+wTNpChCsDx/BqWMtPYTKQDZmhmSp94noIQd429OIJhQt1qL/7vHD1Tac/2V33TsADYW4aS+4AAACBANC4tVdIkB5vyLm2BrjK+P7uS8SaUSfKaAd83XahVz2q8cIeiFHrXvfLRFeks99vgxSPq6mqxC5zpcDGFWBm1UJY4PxyG+t6AhgYEPefD+ofXAvTHLPIRJbNv2BDP6vHOKRfAYtWGbQf6sXw4VwS9mAR6JHlGoHMLnRewMcq49jE
*.com,test04.god ssh-dss AAAAB3NzaC1kc3MAAACBAK3p8k1i9I/m0no3LAS4etFGsommDJcBQfsuP/nn42O0VyDXltcfjLvWxABZow6iKJHiHZ8FN/FxOX+jZUlIplrs6oRYbKeWegq3NcvelEderWhIyOKrDZHgO9HprwamSMWFxDG5kUSJ/em/G5N+rGv8K7dJfCus42ynh0+a/Q1dAAAAFQD1/X/izKQrZs//Q5HgVVOfEqK6+wAAAIBQw1TWAHQHiihsCbbMbGuzm/7Rq9YTvGNyzmBgAP/fbmv/Vi3lZwmTilKSkebEFvrWeAT1hI9KufzjeRhkUCZGzCmCt7A614/brJRIznOAvWaTRsy/wzw7kdARljdQRTcnSXnpc81jEzMyt2SzcifZOvyNfIhAtFXX6yXeFg1dpgAAAIBoJZa1MTGEWJ43BcFftRGbnf/EK5+SDlYgrSiJZeGAUURvrdJPPtCSRtQU7ldiGfKiPcD/6U0XcC9o09/sDSfFOEtTFnawe74pqcQVT3x2hQ5Zs1W82M2arNXaoYBo21RAE4oy1u010a4hjxPoSrAVyQXVwL2Sv8B5vDu99sIu1w==

""")  # noqa
        f.close()

        # Make a subclass so we can control which file it loads.
        class custom_known_hosts(OpenSSH_Known_Hosts):
            def __init__(self, tmp_filename):
                self.tmp_filename = tmp_filename

            def get_known_hosts_filenames(self, username):
                return [self.tmp_filename]

        try:
            from coro.ssh.keys.openssh_key_storage import OpenSSH_Key_Storage
            keystore = OpenSSH_Key_Storage()
            x = custom_known_hosts(tmp_filename)
            # Make some keys to test against.
            # 10.1.1.108
            k1 = keystore.parse_public_key(
                'ssh-dss AAAAB3NzaC1kc3MAAACBAOdTJwlIDyxIKAaCoGr/XsySV8AzJDU2fAePcO7CBURUYyUHS9uKsgsjZw7qBkdnkWT/Yx2Z8k9j+HuJ2L3mI6y9+cknen9ycze6g/UwmYa2+forEz7NXiEWi3lTHXnAXjEpmCWZAB6++HPM9rq+wQluOcN8cks57sttzxzqQG6RAAAAFQCgQ/edsYFn4jEBiJhoj97GElWM0QAAAIAz5hffnGq9zK5rtrNpKVdz6KIEyeXlGd16f6NwotVwpNd2zEXBC3+z13TyMiX35H9m7fWYQen7O7RNekJl5Gz7V6UA7lipNFrhmg/eO6rnXetrrgjdiHF5mSx3O8uBQOU5tK+IyAINtBhDqM6GNEqEkFa9yT6POYjGA8ihSaUUOQAAAIEAvvDYfg+KrBZUlJGMK/g1muBbBu5o+UbppgRTOsEfAMKRovV0vsZc4AIaeh/uGVKS+zXqQHh7btHgTMQ47hxF3tPVFWIgO6vDtsQX90e9xaCfmKQY2EV0Wrq1XUKxOycTNRZ5kCxYkq4qRhs5QnqB/Ov71g7HHxsJ8pnjSDusiNo=')  # noqa
            # lists.ironport.com
            k2 = keystore.parse_public_key(
                'ssh-dss AAAAB3NzaC1kc3MAAACBAOfO0s6KFDk8lU7hJyLWevjEIi9drfn8wJYFvYAc+apN4+Qlq4DtFXMDH8U5pQWpZsj705ywi5cex8aEaeepfeQBe6NQCmJci47cTTnaiy/IR7d2hZkB0LmJJX6JxYWWtk2kFyL4xbPEfXbBpNprTfNzgi32YeeIKak3T3amYo8dAAAAFQDInSP36WJZ7WnH13qBXZM+5USftwAAAIAQ7CHz/hwxpmYNind6Zm7vmFC8JkRdkTjNIfyuHszfgHI3+imhSJJxjaSwdvLNi+2P2cdoTrL45ITPFT0+YSq1VIXclqa0k0kjETFbayGbq9DE3w7S6WBiiewTcllu7NzO9EvaNt3XJUQ7SpvNBoLhv+XAHkdhX0ouwwtyeElT6gAAAIAEcOOSQClq9CIcYEjwtfDBANaJ7o2WfYJMqto+ibjnl+1YFtGw9ofD5gi5gtEIGtSb6mO88ooX9sfmkaAY+1L/gTdb3Fxc3zuL2PymBt1ruNTgVzEjV35h94lgC3+F4mPz0jQpnpsbxhm/uDn/i1BeRBlzMhyWOAHfLknna9WCmg==')  # noqa
            # 172.17.0.201
            k3 = keystore.parse_public_key(
                'ssh-dss AAAAB3NzaC1kc3MAAACBAPaQAeia7kiuORu9425IyZRKlRPkom9mjEVERjN3Lw5R93rBZSwbl8wiT1PEeBN2047SZD7ucHaAUqAU39l//JVA0Q/RHXczad1niqC7Y7YKSpu3XfI7vpgMd91XIlxNhnhvNLtWfmwuWuX1FFiByKUY7fsHVeKTYwnvRPiv89IBAAAAFQCryy7v2z5Olv1Z0bSoQLDemiSzywAAAIEA3pmx1n0YRuw3hY4RfXbQCUxtu19bldG4XlNnmeIE8cb4tdGHBgLnLrMpSLsA4aMOWAzzDvB/Gk9AlgyNuYp2NaCFStE5yYiK9c+wTNpChCsDx/BqWMtPYTKQDZmhmSp94noIQd429OIJhQt1qL/7vHD1Tac/2V33TsADYW4aS+4AAACBANC4tVdIkB5vyLm2BrjK+P7uS8SaUSfKaAd83XahVz2q8cIeiFHrXvfLRFeks99vgxSPq6mqxC5zpcDGFWBm1UJY4PxyG+t6AhgYEPefD+ofXAvTHLPIRJbNv2BDP6vHOKRfAYtWGbQf6sXw4VwS9mAR6JHlGoHMLnRewMcq49jE')  # noqa
            # test04.god
            k4 = keystore.parse_public_key(
                'ssh-dss AAAAB3NzaC1kc3MAAACBAK3p8k1i9I/m0no3LAS4etFGsommDJcBQfsuP/nn42O0VyDXltcfjLvWxABZow6iKJHiHZ8FN/FxOX+jZUlIplrs6oRYbKeWegq3NcvelEderWhIyOKrDZHgO9HprwamSMWFxDG5kUSJ/em/G5N+rGv8K7dJfCus42ynh0+a/Q1dAAAAFQD1/X/izKQrZs//Q5HgVVOfEqK6+wAAAIBQw1TWAHQHiihsCbbMbGuzm/7Rq9YTvGNyzmBgAP/fbmv/Vi3lZwmTilKSkebEFvrWeAT1hI9KufzjeRhkUCZGzCmCt7A614/brJRIznOAvWaTRsy/wzw7kdARljdQRTcnSXnpc81jEzMyt2SzcifZOvyNfIhAtFXX6yXeFg1dpgAAAIBoJZa1MTGEWJ43BcFftRGbnf/EK5+SDlYgrSiJZeGAUURvrdJPPtCSRtQU7ldiGfKiPcD/6U0XcC9o09/sDSfFOEtTFnawe74pqcQVT3x2hQ5Zs1W82M2arNXaoYBo21RAE4oy1u010a4hjxPoSrAVyQXVwL2Sv8B5vDu99sIu1w==')  # noqa
            # Make a key that doesn't exist in the known hosts file.
            unknown_key = keystore.parse_public_key(
                'ssh-dss AAAAB3NzaC1kc3MAAACBAJSc17NO4rxvhUfwjMzJMG9On9umzzlbwlN0wBv5riYetE1flTyySOUPa8YvpNYmMs5GSz0CzO/FI/EM/rgYvpvA+KKpV/9oL+XoT/O36t6Q8MZIGXwj75lxP8X9NSZxO0b5E7CRDyW5rsl6xfa3YaQrWqZRKhOeGASWRYtUZcpVAAAAFQCazkzFpIwqEpAbn0jZlkUHKbpwuQAAAIA4AGcL/OMIDtxC7T1smSPVk0VEr5i+IfL4xPLRSQCw6/Jr4OLzBH/TiTAjyp7NZszIu586J85t1nO3kOx/fKI8Ik2jDvJOmdUtDvMZnbZK1rvFiw3dCxEERGVW1LjyAnxtebl/pOJ6CpO4Pfh87mx+iH9m90oZSCDz602DXUz50wAAAIA0mmctzgavC8ApEsbKI69MhaYhkyxvEaucTarkGPAPvXPurfVJ8ZwtK3dYckLgn3a5WPHWqIZVfmtSbnkwld+t3BIl8IX6bKa2WaffUeU6k50ssUV6IvW+IHd0JJ/mwE6f9caNS7x0pC0+DQujp553IP5cr9NskQTK4j/Iwwlkrw==')  # noqa
            # 172.16.1.11
            k5 = keystore.parse_public_key(
                'ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAIEAvUNY7kd1sDujt9HhdT6VWtf8yVRAw2Ib+M6ptWTuWWnPGR6TP/ZwumSs/rAguyxWrNRbw7Eainr/BTEFATpJRYKUDPZKGHLT3ixtOy7scUVRyaJD7F3L7BujkhHLWOyFJGtoZmJEdQmddGDwq+16gLD06GA8/N8kkQFRR6vwlRs=')  # noqa

            # Do the tests.
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('10.1.1.108', ''), k1), 1)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('1.2.3.4', ''), k1), 0)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('0.0.0.0', 'lists.ironport.com'), k2), 1)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('lists.ironport.com', '10.1.1.109'), k2), 1)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('10.1.1.109', ''), k2), 1)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('0.0.0.0', 'outlaw.qa'), k3), 0)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('0.0.0.0', 'foo.qa'), k3), 1)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('172.17.0.201', ''), k3), 1)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('0.0.0.0', 'foo.com'), k4), 1)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('0.0.0.0', 'test04.god'), k4), 1)
            self.assertRaises(Host_Key_Changed_Error, x.check_for_host, IPv4_Remote_Host_ID('10.1.1.108', ''), k2)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('lists.ironport.com', '10.1.1.108'), k1), 1)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('0.0.0.0', 'unknown.dom'), k1), 0)
            self.assertRaises(
                Host_Key_Changed_Error, x.check_for_host, IPv4_Remote_Host_ID('10.1.1.108', ''), unknown_key)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('172.16.1.11', ''), unknown_key), 0)
            self.assertEqual(x.check_for_host(IPv4_Remote_Host_ID('172.16.1.11', ''), k5), 1)
        finally:
            os.unlink(tmp_filename)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(check_for_host_test_case())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite', module='openssh_known_hosts')
