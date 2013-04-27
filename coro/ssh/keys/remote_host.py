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
# remote_host
#
# This module is the class that abstracts the ID of a host.
# Typically the ID is based on the IP or hostname of the remote host, but this
# allows you to use non-IP configurations.
#

class Remote_Host_ID:
    pass

class IPv4_Remote_Host_ID(Remote_Host_ID):

    """IPv4_Remote_Host_ID

    Represents the ID of the remote host.

    <ip> is required.
    <hostname> is optional.
    """

    ip = ''
    hostname = None

    def __init__(self, ip, hostname):
        self.ip = ip
        self.hostname = hostname

    def __repr__(self):
        return '<IPv4_Remote_Host_ID instance ip=%r hostname=%r>' % (self.ip, self.hostname)
