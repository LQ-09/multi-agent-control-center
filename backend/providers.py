"""Bounded OpenAI-compatible chat adapter. Settings persist; keys are memory-only."""
import json
import os
import re
import threading
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PRESETS = [
    {'id':'deepseek','name':'DeepSeek','base_url':'https://api.deepseek.com','model':'deepseek-flash','key_env':'DEEPSEEK_API_KEY'},
    {'id':'openai','name':'OpenAI-compatible','base_url':'https://api.openai.com/v1','model':'','key_env':'OPENAI_API_KEY'},
    {'id':'ollama','name':'Ollama (local)','base_url':'http://127.0.0.1:11434/v1','model':'','key_env':''},
]

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Provider redirects are disabled; configure its final API base URL.')

class Providers:
    def __init__(self, root):
        self.path=Path(root)/'providers.json'; self.keys={}; self.lock=threading.RLock()
        self.items=json.loads(self.path.read_text()) if self.path.exists() else []
    @staticmethod
    def validate(item):
        fields=('id','name','base_url','model','key_env')
        if set(item)!=set(fields): raise ValueError('Provider settings contain unknown or missing fields')
        if any(not isinstance(item[k],str) or len(item[k])>500 or any(c in item[k] for c in '\r\n\x00') for k in fields):
            raise ValueError('Invalid provider setting')
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}',item['id']): raise ValueError('Use a lowercase provider ID')
        if not item['name'].strip() or not item['model'].strip(): raise ValueError('Provider name and exact model ID are required')
        if item['key_env'] and not re.fullmatch(r'[A-Z_][A-Z0-9_]*',item['key_env']): raise ValueError('Invalid API key environment variable name')
        u=urllib.parse.urlsplit(item['base_url'])
        if not u.hostname or u.username or u.password or u.query or u.fragment: raise ValueError('Base URL must not contain credentials, query parameters or fragments')
        if u.scheme!='https' and not (u.scheme=='http' and u.hostname in ('localhost','127.0.0.1','::1')):
            raise ValueError('Use HTTPS; HTTP is allowed only for a loopback model server')
        if u.path.rstrip('/').endswith('/chat/completions'): raise ValueError('Enter the API base URL, without /chat/completions')
        return dict(item,base_url=item['base_url'].rstrip('/'))
    def get(self, ident):
        with self.lock:
            for item in self.items:
                if item['id']==ident: return dict(item)
        raise ValueError('Configure the selected API provider on this environment first')
    def list(self):
        with self.lock:
            return [{**x,'key_ready':bool(self.keys.get(x['id']) or os.environ.get(x['key_env'],'')) or not x['key_env']} for x in self.items]
    def save(self, item):
        item=self.validate(item)
        with self.lock:
            previous=next((x for x in self.items if x['id']==item['id']),None)
            if previous and previous['base_url']!=item['base_url']: self.keys.pop(item['id'],None)
            items=[x for x in self.items if x['id']!=item['id']]+[item]
            if len(items)>20: raise ValueError('At most 20 provider profiles are supported')
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(items,indent=2));temp.replace(self.path)
            self.items=items
        return self.list()
    def set_key(self, ident, key):
        self.get(ident)
        if not isinstance(key,str) or len(key)>4096 or any(c in key for c in '\r\n\x00'): raise ValueError('Invalid API key')
        with self.lock:
            if key: self.keys[ident]=key
            else: self.keys.pop(ident,None)
        return {'saved_for_session':bool(key)}
    def complete(self, ident, prompt):
        config=self.get(ident)
        with self.lock: key=self.keys.get(ident) or os.environ.get(config['key_env'],'')
        if config['key_env'] and not key: raise ValueError('API key missing: enter a session key in Providers or set '+config['key_env']+' on the execution host')
        headers={'Content-Type':'application/json','Accept':'application/json'}
        if key: headers['Authorization']='Bearer '+key
        body={'model':config['model'],'messages':[{'role':'user','content':prompt[:40000]}],'stream':False,'max_tokens':4096}
        req=urllib.request.Request(config['base_url']+'/chat/completions',data=json.dumps(body).encode(),headers=headers,method='POST')
        try:
            try:
                import certifi
                context=ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                context=ssl.create_default_context()
            with urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=context)).open(req,timeout=60) as response:
                raw=response.read(2_000_001)
            if len(raw)>2_000_000: raise ValueError('Provider response exceeded the 2 MB limit')
            result=json.loads(raw); choice=result['choices'][0]
            if choice.get('finish_reason') not in ('stop',None): raise ValueError('Provider response is incomplete or requests unsupported tools')
            content=choice['message']['content']
            if not isinstance(content,str) or not content.strip(): raise ValueError('Provider returned no text answer')
            return content[:24000].replace(key,'[REDACTED]') if key else content[:24000]
        except urllib.error.HTTPError as e:
            raise ValueError(f'Provider HTTP {e.code}. Check endpoint, model, API key and quota; no automatic retry.') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ValueError('Provider network/TLS error or timeout. No automatic retry; the request may have been billed.') from None
        except (KeyError,IndexError,TypeError,json.JSONDecodeError):
            raise ValueError('Unsupported provider response; expected choices[0].message.content text') from None
