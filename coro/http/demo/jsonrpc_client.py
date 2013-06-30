import coro
from coro.http.json_rpc import json_rpc_remote as JR 

def go():
    r = JR ('http://127.0.0.1:9001/jsonrpc')
    print r.invoke ('sum', 1,2,3)
    
coro.spawn (go)
coro.event_loop()

