"""Explicit, incremental read-only scan. No auth/config content is read."""
import hashlib
import json
import os
from pathlib import Path
from core import clean, now, digest

def scan(call, host):
    roots=[('codex',Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'sessions'),
           ('codex',Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'archived_sessions'),
           ('claude',Path(os.environ.get('CLAUDE_CONFIG_DIR',Path.home()/'.claude'))/'projects')]
    count=0; used=0; files=0
    for agent,root in roots:
        if not root.is_dir(): continue
        for path in root.rglob('*.jsonl'):
            if files>=100 or used>=4_000_000: return {'records':count,'files':files,'bounded':True}
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()): continue
            files+=1; source=f'{host}:{path}'; st=path.stat()
            fingerprint=f'{st.st_dev}:{st.st_ino}'
            cursor=call('cursor',{'source':source}); offset=0
            if cursor and cursor['fingerprint']==fingerprint and cursor['offset']<=st.st_size: offset=cursor['offset']
            records=[]
            with path.open('rb') as f:
                f.seek(offset); start=offset; session=path.stem; read=0
                while read<256_000 and used<4_000_000:
                    line=f.readline(65537)
                    if not line or not line.endswith(b'\n') or len(line)>65536: break
                    pos=f.tell(); read+=len(line); used+=len(line)
                    try:
                        obj=json.loads(line); payload=obj.get('payload',{})
                        if not isinstance(payload,dict): payload={}
                        session=obj.get('sessionId') or payload.get('session_id') or session
                        typ=str(obj.get('type','unknown'))
                        # Only text summaries, never raw instructions/config metadata.
                        text=payload.get('message') or (obj.get('message',{}).get('content') if isinstance(obj.get('message'),dict) else '')
                        if isinstance(text,list): text=' '.join(str(x.get('text','')) for x in text if isinstance(x,dict) and x.get('type')=='text')
                        summary=clean(text or f'[{typ}] native event',2000)
                        h=hashlib.sha256(line).hexdigest()
                        records.append({'id':digest(source+fingerprint+str(offset)+h),'host':host,'agent':agent,'session':str(session)[:160],
                            'timestamp':str(obj.get('timestamp') or now()),'summary':summary,'offset':offset,'hash':h})
                    except (ValueError,TypeError): pass
                    offset=pos
            if offset!=start:
                call('import_batch',{'source':source,'fingerprint':fingerprint,'offset':offset,'records':records}); count+=len(records)
    return {'records':count,'files':files,'bounded':False}
