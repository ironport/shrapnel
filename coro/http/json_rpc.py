# -*- Mode: Python -*-

import json
import urlparse
import coro
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
            rd = {'jsonrpc':'2.0', 'result':result, 'id':qd['id']}
        else:
            rd = {'result':result, 'error':None, 'id':qd['id']}
        request.push (json.dumps (rd))
        request.done()

class json_rpc_remote:

    def __init__ (self, url):
        self.url = url
        self.url_ob = urlparse.urlparse (url)
        assert (self.url_ob.scheme == 'http')
        self.counter = 0

    def invoke (self, name, *args):
        c = http_client (self.url_ob.hostname, self.url_ob.port)
        jreq = json.dumps ({'method': name, 'params':list(args), 'id':self.counter})
        self.counter += 1
        req = c.POST (self.url_ob.path, jreq)
        jrep = json.loads (req.content)
        return jrep['result']
        
        
