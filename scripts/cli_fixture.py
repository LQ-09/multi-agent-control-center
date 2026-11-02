"""Controlled app-server peer for integration tests; never calls a model."""
import textwrap

def script(body):
    return '''import sys,json
if '--version' in sys.argv:
    print('ACC simulated Codex');raise SystemExit
def answer(prompt):
'''+textwrap.indent(body,'    ')+'''
def emit(value):print(json.dumps(value),flush=True)
for line in sys.stdin:
    req=json.loads(line);method=req.get('method');params=req.get('params',{})
    if method=='initialize':emit({'id':req['id'],'result':{}})
    elif method in ('thread/start','thread/resume'):
        emit({'id':req['id'],'result':{'thread':{'id':'test-session'}}})
    elif method=='turn/start':
        emit({'id':req['id'],'result':{'turn':{'id':'turn'}}})
        result=answer(params['input'][0]['text'])
        emit({'method':'item/completed','params':{'threadId':'test-session','item':{'type':'agentMessage','text':result}}})
        emit({'method':'turn/completed','params':{'threadId':'test-session','turn':{'id':'turn','status':'completed'}}})
'''
