# -*- Mode: Python -*-

import coro
import mimetypes
import os
import re
import stat
import sys
import time
import zlib

from coro.http.http_date import build_http_date, parse_http_date

from coro.log import Facility
from urllib import unquote

LOG = Facility ('http handlers')

# these two aren't real handlers, they're more like templates
#  to give you an idea how to write one.
class post_handler:

    def match (self, request):
        # override to do a better job of matching
        return request._method == 'post'

    def handle_request (self, request):
        data = request.file.read()
        request.done()

class put_handler:

    def match (self, request):
        # override to do a better job of matching
        return request.method == 'put'

    def handle_request (self, request):
        fp = request.file
        while 1:
            line = fp.readline()
            if not line:
                LOG ('line done')
                break
            else:
                LOG ('line', line)
        request.done()

class coro_status_handler:

    def match (self, request):
        return request.path.split ('/')[1] == 'status'

    def clean (self, s):
        s = s.replace ('<', '&lt;')
        s = s.replace ('>', '&gt;')
        return s

    def handle_request (self, request):
        request['content-type'] = 'text/html; charset=utf-8'
        request.set_deflate()
        request.push (
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" '
            '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'
            '<html xmlns="http://www.w3.org/1999/xhtml">\r\n'
        )
        request.push ('<head><title>status</title></head><body>\r\n')
        request.push ('<p>Listening on\r\n')
        request.push (repr (request.server.addr))
        request.push ('</p>\r\n')
        request.push ('<table border="1">\r\n')
        all_threads = ((x, coro.where(x)) for x in coro.all_threads.values())
        for thread, traceback in all_threads:
            request.push ('<tr><td>%s\r\n' % self.clean (repr(thread)))
            request.push ('<pre>\r\n')
            # traceback format seems to have changed
            for level in traceback[1:-1].split ('] ['):
                [file, fun] = level.split (' ')
                fun, line = fun.split ('|')
                request.push ('<b>%20s</b>:%3d %s\r\n' % (self.clean (fun), int(line), self.clean (file)))
            request.push ('</pre></td></tr>')
        request.push ('</table>\r\n')
        request.push ('<p><a href="status">Update</a></p>')
        request.push ('</body></html>')
        request.done()

class file_handler:

    block_size = 16000

    def __init__ (self, doc_root):
        self.doc_root = doc_root

    def match (self, request):
        path = request.path
        filename = os.path.join (self.doc_root, path[1:])
        return os.path.exists (filename)

    def handle_directory_listing (self, request, path):
        return request.error (404)

    crack_if_modified_since = re.compile ('([^;]+)(; length=([0-9]+))?$', re.IGNORECASE)

    def handle_request (self, request):
        path = unquote (request.path)
        filename = os.path.join (self.doc_root, path[1:])

        if request.method not in ('get', 'head'):
            request.error (405)
            return

        if os.path.isdir (filename):
            index_html = os.path.join (filename, 'index.html')
            if os.path.isfile (index_html):
                filename = index_html
            else:
                return self.handle_directory_listing (request, filename)

        if not os.path.isfile (filename):
            request.error (404)
        else:
            stat_info = os.stat (filename)
            mtime = stat_info[stat.ST_MTIME]
            file_length = stat_info[stat.ST_SIZE]

            ims = request['if-modified-since']
            if ims:
                length_match = 1
                m = self.crack_if_modified_since.match (ims)
                if m:
                    length = m.group (3)
                    if length:
                        if int(length) != file_length:
                            length_match = 0

                ims_date = parse_http_date (m.group(1))

                if length_match and ims_date:
                    if mtime <= ims_date:
                        request.error (304)
                        return

            ftype, fencoding = mimetypes.guess_type (filename)
            request['Content-Type'] = ftype or 'text/plain'
            request['Last-Modified'] = build_http_date (mtime)

            # Note: these are blocking file operations.
            if request.method == 'get':
                f = open (filename, 'rb')
                block = f.read (self.block_size)
                if not block:
                    request.error (204)  # no content
                else:
                    while 1:
                        request.push (block)
                        block = f.read (self.block_size)
                        if not block:
                            break
                    request.done()
            elif request.method == 'head':
                pass
                request.done()
            else:
                # should be impossible
                request.error (405)

sample = (
    'AAABAAEAICAQAAEABADoAgAAFgAAACgAAAAgAAAAQAAAAAEABAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAD/+K///8AH//+iI///QAH//r4g//x3AH//Z6J//UABP/ovgD/458Ef+u+wv/Tn'
    '0R/+79if9OXZH/6gCJ/2BwAf/u/8n/h33R/7Z7kf/ReQH/+qu7//BUW//7vrv//RR3//7r///80d'
    '///pq///8EP//+rH///d9///6j///9Af/w=='
).decode ('base64')

zsample = zlib.compress (sample, 9)

last_modified = build_http_date (time.time())

class favicon_handler:

    def __init__ (self, data=None):
        if data is None:
            self.data = zsample
        else:
            self.data = data

    def match (self, request):
        return request.path == '/favicon.ico'

    def handle_request (self, request):
        if request['if-modified-since']:
            # if we cared, we could check that timestamp.
            request.error (304)
        else:
            request['content-type'] = 'image/x-icon'
            request['last-modified'] = last_modified
            # are there browsers that don't accept deflate?
            request['content-encoding'] = 'deflate'
            request.push (self.data)
            request.done()

# [based on ancient medusa code]
# This is a 'handler' that wraps an authorization method
# around access to the resources normally served up by
# another handler.

# does anyone support digest authentication? (rfc2069)

import hashlib

class auth_handler:

    def __init__ (self, dict, handler, realm='default'):
        self.dict = dict
        self.handler = handler
        self.realm = realm
        self.pass_count = 0
        self.fail_count = 0

    def match (self, request):
        # by default, use the given handler's matcher
        return self.handler.match (request)

    def parse_authorization (self, h):
        parts = h.split()
        kind = parts[0].lower()
        if kind != 'digest':
            return {}
        else:
            # split on comma
            parts = h.split (',')
            # strip off 'digest '
            parts[0] = parts[0][7:]
            # trim extra whitespace
            parts = [x.strip() for x in parts]
            d = {}
            for part in parts:
                i = part.find ('=')
                if i == -1:
                    return {}
                else:
                    key = part[:i]
                    val = part[i + 1:]
                    # strip quotes
                    val = val.replace ('"', ' ').strip()
                    d[key.lower()] = val
            return d

    def check_response (self, request, d):
        username = d['username']
        passwd = self.dict.get (username, None)
        if passwd is None:
            return False
        else:
            hash = lambda x: hashlib.md5(x).hexdigest()
            s1 = ':'.join ((username, d['realm'], passwd))
            s2 = ':'.join ((request.method.upper(), request.uri))
            ha1 = hash (s1)
            ha2 = hash (s2)
            s3 = ':'.join ((ha1, d['nonce'], ha2))
            ha3 = hash (s3)
            if ha3 == d['response']:
                return True
            else:
                return False

    def handle_request (self, request):
        # authorize a request before handling it...
        h = request['authorization']
        if h:
            d = self.parse_authorization (request['authorization'])
            if d and self.check_response (request, d):
                return self.handler.handle_request (request)
            else:
                self.handle_unauthorized (request)
        else:
            self.handle_unauthorized (request)

    def get_nonce (self):
        return hashlib.sha1 (os.urandom(16)).hexdigest()[:16]

    def handle_unauthorized (self, request):
        # We are now going to receive data that we want to ignore.
        # to ignore the file data we're not interested in.
        self.fail_count += 1
        nonce = self.get_nonce()
        request['WWW-Authenticate'] = ','.join ([
            'Digest realm="%s"' % self.realm,
            'nonce="%s"' % (nonce,),
        ])
        request.error (401)
