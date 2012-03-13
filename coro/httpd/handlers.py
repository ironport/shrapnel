# -*- Mode: Python -*-

import coro
import os
import re
import sys
import time
import zlib

from coro.httpd.http_date import build_http_date

W = sys.stderr.write

# these two aren't real handlers, they're more like templates
#  to give you an idea how to write one.
class post_handler:

    def match (self, request):
        # override to do a better job of matching
        return request._method == 'post'

    def handle_request (self, request):
        data = request.file.read()
        W ('post handler, data=%r\n' % (data,))
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
                W ('line: DONE!\n')
                break
            else:
                W ('line: %r\n' % (line,))
        request.done()

class coro_status_handler:

    def match (self, request):
        return request.path.split ('/')[1] == 'status'

    def clean (self, s):
        s = s.replace ('<','&lt;')
        s = s.replace ('>','&gt;')
        return s

    def handle_request (self, request):
        request['Content-Type'] = 'text/html'
        request.set_deflate()
        request.push ('<p>Listening on\r\n')
        request.push (repr (request.server.addr))
        request.push ('</p>\r\n')
        request.push ('<ul>\r\n')
        all_threads = ( (x, coro.where(x)) for x in coro.all_threads.values() )
        for thread, traceback in all_threads:
            request.push ('<li>%s\r\n' % self.clean (repr(thread)))
            request.push ('<pre>\r\n')
            # traceback format seems to have changed
            for level in traceback[1:-1].split ('] ['):
                [file, fun] = level.split (' ')
                fun, line = fun.split ('|')
                request.push ('<b>%20s</b>:%3d %s\r\n' % (fun, int(line), file))
            request.push ('</pre>')
        request.push ('</ul>\r\n')
        request.push ('<a href="status">Update</a>')
        request.done()

class file_handler:

    block_size = 16000

    def __init__ (self, doc_root):
        self.doc_root = doc_root

    def match (self, request):
        path = request.path
        filename = os.path.join (self.doc_root, path[1:])
        return os.path.exists (filename)

    crack_if_modified_since = re.compile ('([^;]+)(; length=([0-9]+))?$', re.IGNORECASE)

    def handle_request (self, request):
        path = request.path
        filename = os.path.join (self.doc_root, path[1:])

        if request.method not in ('get', 'head'):
            request.error (405)
            return

        if os.path.isdir (filename):
            filename = os.path.join (filename, 'index.html')

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

                ims_date = http_date.parse_http_date (m.group(1))

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
                    request.error (204) # no content
                else:
                    while 1:
                        request.push (block)
                        block = f.read (self.block_size)
                        if not block:
                            break
            elif request.method == 'head':
                pass
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
