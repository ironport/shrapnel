# -*- Mode: Python -*-

import json
import urlparse
import coro
import base64
from coro.http.client import client as http_client
from coro.http.protocol import header_set

class json_rpc_handler:

    def __init__ (self, root):
        self.root = root

    def match (self, request):
        return request.method == 'post' and request.path == '/jsonrpc'

    def handle_request (self, request):
        data = request.file.read()
        qd = json.loads (data)
        v2 = qd.has_key ('jsonrpc')
        result = self.root.handle_json_rpc (qd['method'], qd['params'])
        request['content-type'] = 'application/json'
        if v2:
            rd = {'jsonrpc': '2.0', 'result': result, 'id': qd['id']}
        else:
            rd = {'result': result, 'error': None, 'id': qd['id']}
        request.push (json.dumps (rd))
        request.done()

class Error (Exception):
    pass

class proxy:

    def __init__ (self, remote, name):
        self.remote = remote
        self.name = name

    def __call__ (self, *args, **kwargs):
        return self.remote.invoke (self.name, args, kwargs)

class json_rpc_remote:

    def __init__ (self, url, auth_info=None):
        self.url = url
        self.url_ob = urlparse.urlparse (url)
        assert (self.url_ob.scheme == 'http')
        self.counter = 0
        if auth_info:
            # basic only
            self.auth = base64.b64encode ('%s:%s' % auth_info)
        else:
            self.auth = None
        self.conn = None

    def invoke (self, name, *args, **kwargs):
        if self.conn is None:
            self.conn = http_client (self.url_ob.hostname, self.url_ob.port)
        if kwargs:
            assert (not args)  # no way to mix positional & named args
            params = kwargs
        else:
            params = list (args)
        jreq = json.dumps ({'method': name, 'params': params, 'id': self.counter})
        self.counter += 1
        if self.auth:
            req = self.conn.POST (self.url_ob.path, jreq, Authorization='Basic %s' % (self.auth,))
        else:
            req = self.conn.POST (self.url_ob.path, jreq)
        if req.reply_code == '200':
            jrep = json.loads (req.content)
            return jrep['result']
        else:
            raise Error ((req.reply_code, req.content))

    def close (self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __getattr__ (self, name):
        return proxy (self, name)
