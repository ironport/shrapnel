# -*- Mode: Python -*-

import json

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
