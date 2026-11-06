import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core import Store
from adaptive import plan_steps
from task_graph import browser_key
from browser_tools import browser_server


def result(status='succeeded',**extra):
    return '<acc_result>'+json.dumps(dict(status=status,summary='Evidence',details='Test evidence',**extra))+'</acc_result>'

def node(key,deps=(),role='Execute',**kw):
    return dict(id=key,depends_on=list(deps),role=role,slot=0,instruction='Research '+key,**kw)

def plan(rows):return '<acc_plan>'+json.dumps(dict(steps=rows))+'</acc_plan>'

class GraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name,host='local');self.addCleanup(self.store.close)
        self.ident=self.store.create(dict(key='graph',workflow='adaptive',prompt='Compare cities',workspace=self.tmp.name,acceptance='Verified sources',agents=['codex']*3))['id']
        self.store.control(self.ident,'run',1)
    def finish(self,s,text=None,**kw):return self.store.finish(s['id'],s['attempt'],text or result(),**kw)
    def start(self,rows):self.finish(self.store.claim('local'),result()+plan(rows))
    def claim(self):return self.store.claim('local')
    def control(self,action):return self.store.control(self.ident,action,self.store.get_task(self.ident)['revision'])
    def test_parallel_branches_and_join_starts_before_unrelated_branch_finishes(self):
        self.start([node('a'),node('b'),node('a_review',['a'],'Review'),node('deliver',['a_review','b'],'Deliver')])
        a,b=self.claim(),self.claim();self.assertEqual({a['node_key'],b['node_key']},{'a','b'})
        self.assertIsNone(self.claim());self.finish(a)
        review=self.claim();self.assertEqual(review['node_key'],'a_review')
        self.assertFalse(any('Node b:' in c['output'] for c in review['context']))
        self.finish(review);self.assertIsNone(self.claim());self.finish(b)
        deliver=self.claim();self.assertEqual(deliver['role'],'Deliver')
        self.assertEqual(self.finish(deliver,result(accepted=True))['status'],'Completed')
    def test_concurrency_limit_and_atomic_claims_across_connections(self):
        self.start([node(x) for x in 'abcd']+[node('end',list('abcd'),'Deliver')])
        other=Store(self.tmp.name,host='local');self.addCleanup(other.close)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            claimed=list(pool.map(lambda i:(self.store if i%2 else other).claim('local'),range(4)))
        self.assertEqual(len([x for x in claimed if x]),3)
        self.assertEqual(len({x['id'] for x in claimed if x}),3)
    def test_success_cannot_erase_sibling_failure_and_retry_preserves_other_branch(self):
        self.start([node('a'),node('b'),node('end',['a','b'],'Deliver')])
        a,b=self.claim(),self.claim();self.finish(a,result('failed'));self.finish(b)
        self.assertEqual(self.store.get_task(self.ident)['status'],'Failed')
        self.assertIsNone(self.claim());self.control('retry');retry=self.claim()
        self.assertEqual(retry['id'],a['id']);self.finish(retry)
        self.assertEqual(self.claim()['role'],'Deliver')
    def test_pause_signals_all_branches_and_cannot_resume_while_stopping(self):
        self.start([node('a'),node('b'),node('end',['a','b'],'Deliver')])
        a,b=self.claim(),self.claim();self.control('pause')
        for s in (a,b):self.assertEqual(self.store.pulse(s['id'],s['attempt'])['stop'],'pause requested')
        self.finish(a);self.assertEqual(self.store.get_task(self.ident)['status'],'Blocked')
        with self.assertRaises(ValueError):self.control('run')
        self.finish(b);self.assertEqual(self.store.get_task(self.ident)['status'],'Paused')
        self.control('run');self.assertIsNotNone(self.claim());self.assertIsNotNone(self.claim())
    def test_cancel_waits_for_all_acknowledgments(self):
        self.start([node('a'),node('b'),node('end',['a','b'],'Deliver')])
        a,b=self.claim(),self.claim();self.control('cancel');self.finish(a)
        self.assertEqual(self.store.get_task(self.ident)['status'],'Blocked');self.finish(b)
        self.assertEqual(self.store.get_task(self.ident)['status'],'Cancelled');self.assertIsNone(self.claim())
    def test_targeted_rework_waits_for_running_siblings_and_keeps_unrelated_result(self):
        self.start([node('a'),node('b'),node('review',['a'],'Review'),node('end',['review','b'],'Deliver')])
        a,b=self.claim(),self.claim();self.finish(a);review=self.claim()
        self.finish(review,result('failed',rework_ids=['a']));self.assertIsNone(self.claim())
        self.finish(b);retry=self.claim();self.assertEqual(retry['id'],a['id'])
        self.assertTrue(any(c['role']=='Review' for c in retry['context']))
        self.assertEqual(next(s for s in self.store.snapshot()['steps'] if s['id']==b['id'])['status'],'Succeeded')
    def test_delivery_can_append_parallel_followup_then_complete(self):
        self.start([node('end',role='Deliver')]);first=self.claim()
        rows=[node('a'),node('b'),node('end',['a','b'],'Deliver')]
        self.assertEqual(self.finish(first,result(accepted=False)+plan(rows))['status'],'Queued')
        a,b=self.claim(),self.claim();self.finish(a);self.finish(b)
        self.assertEqual(self.finish(self.claim(),result(accepted=True))['status'],'Completed')
        self.assertEqual(self.store.get_task(self.ident)['plan_rounds'],1)
    def test_expired_sibling_is_not_hidden_or_replayed(self):
        self.start([node('a'),node('b'),node('end',['a','b'],'Deliver')]);a,b=self.claim(),self.claim()
        self.store.db.execute('UPDATE steps SET lease=0 WHERE id=?',(a['id'],));self.store.db.commit();self.store.expire();self.finish(b)
        self.assertEqual(self.store.get_task(self.ident)['status'],'Blocked')
        with self.assertRaises(ValueError):self.control('retry')
    def test_writes_to_shared_workspace_serialize(self):
        self.store.db.execute("UPDATE tasks SET execution_mode='workspace-write'");self.store.db.commit()
        self.start([node('write',access='workspace-write'),node('read'),node('end',['write','read'],'Deliver')]);writer=self.claim()
        self.assertIsNone(self.claim());self.finish(writer);self.assertEqual(self.claim()['node_key'],'read')
    def test_shared_browser_is_serialized_and_isolated_browser_is_parallel(self):
        self.start([node('a',browser='shared'),node('b',browser='shared'),node('c'),node('end',['a','b','c'],'Deliver')])
        with patch('browser_tools.browser_server',return_value={'command':'node'}):
            a,c=self.claim(),self.claim();self.assertEqual(a['node_key'],'a');self.assertEqual(c['node_key'],'c')
            self.assertNotEqual(browser_key(a),browser_key(c));self.assertIsNone(self.claim())
    def test_graph_validation_rejects_cycles_unknown_dependencies_and_missing_join(self):
        pool=[dict(agent='codex')]
        cases=[[node('a',['b']),node('b',['a']),node('end',['a','b'],'Deliver')],
               [node('end',['missing'],'Deliver')],[node('a'),node('end',role='Deliver')],
               [node('a'),node('a'),node('end',['a'],'Deliver')]]
        for rows in cases:
            with self.subTest(rows=rows),self.assertRaises(ValueError):plan_steps(plan(rows),pool)

    def test_multiple_login_blocks_retry_the_profile_that_was_opened(self):
        self.start([node('a'),node('b'),node('end',['a','b'],'Deliver')])
        a,b=self.claim(),self.claim()
        self.finish(a,result('blocked',reason='login_required',login_url='https://a.example/login'))
        self.finish(b,result('blocked',reason='login_required',login_url='https://b.example/login'))
        chosen=self.store.get_task(self.ident)['login_step']
        self.store.db.execute("UPDATE tasks SET login_state='closed' WHERE id=?",(self.ident,));self.store.db.commit()
        self.control('login_continue');retried=self.claim();self.assertEqual(retried['id'],chosen)
        self.finish(retried)
        task=self.store.get_task(self.ident)
        self.assertEqual(task['status'],'Waiting for Login');self.assertNotEqual(task['login_step'],chosen)
    def test_followup_round_limit_does_not_create_an_unbounded_graph(self):
        self.start([node('end',role='Deliver')]);step=self.claim()
        self.store.db.execute('UPDATE tasks SET plan_rounds=3');self.store.db.commit()
        self.assertEqual(self.finish(step,result(accepted=False)+plan([node('end',role='Deliver')]))['status'],'Failed')
        self.assertEqual(len(self.store.snapshot()['steps']),2)
