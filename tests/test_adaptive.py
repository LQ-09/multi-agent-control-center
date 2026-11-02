import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core import Store

def result(status='succeeded',**extra):
    return '<acc_result>'+json.dumps(dict(status=status,summary='Fixture evidence.',details='Controlled test evidence.',**extra))+'</acc_result>'

class AdaptiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name,host='local');self.addCleanup(self.store.close)
        self.id=self.store.create(dict(key='adaptive',workflow='adaptive',workspace=self.tmp.name,prompt='Solve task',acceptance='Evidence',agents=['codex','codex','claude']))['id']
        self.store.control(self.id,'run',1)
    def finish(self,s,text):return self.store.finish(s['id'],s['attempt'],text)
    def plan(self,roles):
        p=self.store.claim('local')
        return self.finish(p,result()+'<acc_plan>'+json.dumps({'steps':[dict(role=r,slot=i%3,instruction='Do assigned work') for i,r in enumerate(roles)]})+'</acc_plan>')
    def test_team_size_is_task_specific_and_delivery_requires_acceptance(self):
        self.plan(['Execute','Execute','Review','Deliver'])
        self.assertEqual(len(self.store.snapshot()['steps']),5)
        for _ in range(3):self.finish(self.store.claim('local'),result())
        final=self.store.claim('local')
        self.assertEqual(self.finish(final,result())['status'],'Failed')
        task=self.store.get_task(self.id);self.store.control(self.id,'retry',task['revision'])
        self.assertEqual(self.finish(self.store.claim('local'),result(accepted=True))['status'],'Completed')
    def test_single_agent_delivery_and_restart_replans(self):
        self.plan(['Deliver']);self.assertEqual(len(self.store.snapshot()['steps']),2)
        self.finish(self.store.claim('local'),result(accepted=True))
        task=self.store.get_task(self.id);self.store.control(self.id,'restart',task['revision'])
        self.assertEqual(len(self.store.snapshot()['steps']),1)
        self.assertEqual(self.store.claim('local')['role'],'Plan')
    def test_review_rejection_returns_to_executor_with_feedback(self):
        self.plan(['Execute','Review','Deliver'])
        self.finish(self.store.claim('local'),result())
        self.assertEqual(self.finish(self.store.claim('local'),result('failed'))['status'],'Queued')
        retry=self.store.claim('local')
        self.assertEqual(retry['role'],'Execute')
        self.assertTrue(any(c['role']=='Review' for c in retry['context']))
    def test_invalid_plan_does_not_create_assignments(self):
        step=self.store.claim('local')
        self.assertEqual(self.finish(step,result()+'<acc_plan>{"steps":[{"role":"Deliver","slot":9,"instruction":"work"}]}</acc_plan>')['status'],'Failed')
        self.assertEqual(len(self.store.snapshot()['steps']),1)
