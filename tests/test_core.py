import sys
import tempfile
import unittest
import time
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core import Store,redact
from agents import run,prompt_for
from history import scan
from unittest.mock import patch

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name,demo=True)
    def tearDown(self): self.store.close();self.tmp.cleanup()
    def create(self):
        return self.store.create({'key':'one','title':'Test mission','prompt':'Inspect and summarize','workspace':'C:\\project','acceptance':'Evidence is explicit','agents':['codex','codex','claude']})['id']
    def control(self,id,action): return self.store.control(id,action,self.store.get_task(id)['revision'])
    def call(self,op,args=None): return self.store.dispatch({'op':op,'args':args or {}})
    def test_end_to_end_requires_acceptance(self):
        id=self.create();self.control(id,'run')
        for host in ('mac','windows','mac'):
            s=self.store.claim(host);self.assertIsNotNone(s)
            self.assertIsNone(self.store.claim(host))
            self.store.finish(s['id'],s['attempt'],'Verified handoff text')
        self.assertEqual(self.store.get_task(id)['status'],'Verifying')
        self.control(id,'accept');self.assertEqual(self.store.get_task(id)['status'],'Completed')
        self.assertEqual(len(self.store.snapshot()['artifacts']),3)
    def test_dependency_and_windows_restriction(self):
        id=self.create();self.control(id,'run');self.assertIsNone(self.store.claim('windows'))
        s=self.store.claim('mac');self.store.finish(s['id'],s['attempt'],'Plan')
        self.assertIsNone(self.store.claim('mac'));self.assertEqual(self.store.claim('windows')['host'],'windows')
    def test_idempotency(self):
        self.assertEqual(self.create(),self.create())
        self.assertEqual(len(self.store.snapshot()['tasks']),1)
    def test_stale_revision(self):
        id=self.create();self.control(id,'run')
        with self.assertRaisesRegex(ValueError,'changed'):self.store.control(id,'cancel',1)
    def test_stale_attempt_cannot_publish(self):
        id=self.create();self.control(id,'run');s=self.store.claim('mac')
        with self.assertRaisesRegex(ValueError,'Stale'):self.store.finish(s['id'],'wrong','bad')
        self.assertEqual(len(self.store.snapshot()['artifacts']),0)
    def test_cancel_pending_then_ack(self):
        id=self.create();self.control(id,'run');s=self.store.claim('mac');self.control(id,'cancel')
        self.assertEqual(self.store.get_task(id)['status'],'Blocked')
        self.assertEqual(self.store.pulse(s['id'],s['attempt'])['stop'],'cancel requested')
        self.store.finish(s['id'],s['attempt'],'',stopped='cancel')
        self.assertEqual(self.store.get_task(id)['status'],'Cancelled')
    def test_pause_then_resume(self):
        id=self.create();self.control(id,'run');s=self.store.claim('mac');self.control(id,'pause')
        self.store.finish(s['id'],s['attempt'],'partial',stopped='pause');self.control(id,'run')
        resumed=self.store.claim('mac');self.assertNotEqual(s['attempt'],resumed['attempt'])
    def test_expired_lease_blocks_no_retry(self):
        id=self.create();self.control(id,'run');s=self.store.claim('mac')
        self.store.db.execute('UPDATE steps SET lease=? WHERE id=?',(time.time()-1,s['id']));self.store.db.commit()
        self.store.expire();self.assertEqual(self.store.get_task(id)['status'],'Blocked');self.assertIsNone(self.store.claim('mac'))
    def test_failed_cli_never_completes(self):
        id=self.create();self.control(id,'run');s=self.store.claim('mac');self.store.finish(s['id'],s['attempt'],'',error='Auth failed')
        self.assertEqual(self.store.get_task(id)['status'],'Failed')
        with self.assertRaises(ValueError):self.control(id,'accept')
    def test_log_dedup_and_redaction(self):
        id=self.create();self.control(id,'run');s=self.store.claim('mac')
        for _ in range(2):self.store.record(s['id'],s['attempt'],'password=abc123 Bearer abcd','stable-key')
        ev=[e for e in self.store.snapshot()['events'] if e['event_type']=='agent.output']
        self.assertEqual(len(ev),1);self.assertNotIn('abc123',ev[0]['output_summary']);self.assertNotIn('abcd',ev[0]['output_summary'])
    def test_quota_stops_new_work(self):
        with patch('core.MAX_DB',1):
            with self.assertRaisesRegex(ValueError,'quota'):self.create()
    def test_crash_reopen_retains_events(self):
        id=self.create();self.store.close();self.store=Store(self.tmp.name,True)
        self.assertEqual(self.store.get_task(id)['title'],'Test mission');self.assertEqual(len(self.store.snapshot()['events']),1)
    def test_import_is_read_only_incremental(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home)/'sessions';root.mkdir();p=root/'sample.jsonl'
            line=json.dumps({'type':'event_msg','timestamp':'2026-10-29T22:00:00Z','payload':{'message':'api_key=secretvalue'}})+'\n'
            p.write_text(line+'{"partial":');original=p.read_bytes()
            with patch.dict('os.environ',{'CODEX_HOME':home,'CLAUDE_CONFIG_DIR':home}):
                first=scan(self.call,'mac');second=scan(self.call,'mac')
            self.assertEqual(first['records'],1);self.assertEqual(second['records'],0)
            self.assertEqual(p.read_bytes(),original)
            self.assertNotIn('secretvalue',self.store.snapshot()['history'][0]['summary'])
    def test_empty_final_output_rejected(self):
        id=self.create();self.control(id,'run');s=self.store.claim('mac')
        with self.assertRaisesRegex(ValueError,'Empty'):self.store.finish(s['id'],s['attempt'],'')
    def test_role_configuration(self):
        id=self.create();self.control(id,'run');s=self.store.claim('mac');self.assertIn('Plan agent',prompt_for(s))

if __name__=='__main__':unittest.main()

class AdapterTests(unittest.TestCase):
    def test_real_subprocess_protocol(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root,True)
            task=store.create({'key':'adapter','title':'Inspect','prompt':'Read only','workspace':root,'acceptance':'A result','agents':['codex','codex','claude']})['id']
            store.control(task,'run',1);step=store.claim('mac')
            fake=Path(root)/'fake_cli.py'
            fake.write_text('import sys,json\nprompt=sys.stdin.read()\nassert "Plan agent" in prompt\nprint(json.dumps({"type":"thread.started","thread_id":"test-session"}))\nprint(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":\'<acc_result>{"status":"succeeded","summary":"A bounded plan.","details":"Evidence references."}</acc_result>\'}}))\n')
            def call(op,args=None):return store.dispatch({'op':op,'args':args or {}})
            with patch('agents.argv',return_value=[sys.executable,str(fake)]):run(step,call,root)
            snap=store.snapshot();self.assertEqual(snap['steps'][0]['status'],'Succeeded');self.assertEqual(snap['steps'][0]['session'],'test-session')
            self.assertEqual(snap['tasks'][0]['status'],'Queued');store.close()
    def test_cross_connection_claim_fencing(self):
        import concurrent.futures
        with tempfile.TemporaryDirectory() as root:
            first=Store(root,True);second=Store(root,True)
            task=first.create({'key':'fence','title':'Inspect','prompt':'Read only','workspace':root,'acceptance':'A result'})['id'];first.control(task,'run',1)
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                results=list(pool.map(lambda st:st.claim('mac'),[first,second]))
            self.assertEqual(sum(r is not None for r in results),1)
            first.close();second.close()

class ImmutabilityTests(unittest.TestCase):
    def test_event_mutation_is_rejected(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as root:
            s=Store(root,True);s.create({'key':'immutable','title':'Test','prompt':'Test','workspace':root,'acceptance':'Test'})
            with self.assertRaises(sqlite3.IntegrityError):s.db.execute("UPDATE events SET output_summary='changed'")
            s.db.rollback()
            with self.assertRaises(sqlite3.IntegrityError):s.db.execute('DELETE FROM events')
            s.db.rollback();s.close()
