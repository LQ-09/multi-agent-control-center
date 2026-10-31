import sys,tempfile,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core import Store

def result(status):
    return '<acc_result>'+json.dumps(dict(status=status,summary='Result.',details='Evidence'))+'</acc_result>'

class RetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name,host='local')
        self.id=self.s.create(dict(key='x',prompt='test',workspace=self.tmp.name,acceptance='Evidence'))['id']
        self.s.control(self.id,'run',1)
        self.plan=self.s.claim('local');self.s.finish(self.plan['id'],self.plan['attempt'],result('succeeded'))
        self.step=self.s.claim('local')
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def retry(self):return self.s.control(self.id,'retry',self.s.get_task(self.id)['revision'])
    def test_retry_keeps_plan_artifacts_events_and_changes_attempt(self):
        self.s.finish(self.step['id'],self.step['attempt'],result('blocked'))
        before=self.s.snapshot();revision=self.s.get_task(self.id)['revision']
        self.retry();step=self.s.claim('local')
        self.assertEqual(step['id'],self.step['id']);self.assertNotEqual(step['attempt'],self.step['attempt'])
        self.assertEqual(step['role'],'Execute');self.assertEqual(len(step['context']),1)
        self.assertEqual(self.s.snapshot()['artifacts'],before['artifacts'])
        self.assertEqual(self.s.snapshot()['events'][:len(before['events'])],before['events'])
        with self.assertRaises(ValueError):self.s.control(self.id,'retry',revision)
        with self.assertRaises(ValueError):self.s.finish(step['id'],self.step['attempt'],result('succeeded'))
    def test_live_and_unknown_execution_cannot_retry(self):
        with self.assertRaises(ValueError):self.retry()
        self.s.db.execute('UPDATE steps SET lease=0 WHERE id=?',(self.step['id'],));self.s.db.commit();self.s.expire()
        with self.assertRaisesRegex(ValueError,'unknown'):self.retry()
    def test_failed_and_multiple_explicit_retries(self):
        self.s.finish(self.step['id'],self.step['attempt'],'',error='CLI exited with code 1')
        self.retry();step=self.s.claim('local');self.s.finish(step['id'],step['attempt'],result('blocked'))
        self.retry();self.assertEqual(self.s.claim('local')['role'],'Execute')
    def test_unconfirmed_termination_cannot_retry(self):
        self.s.finish(self.step['id'],self.step['attempt'],'',error='Process termination unconfirmed')
        with self.assertRaisesRegex(ValueError,'unknown'):self.retry()
    def test_paused_failed_task_can_retry_without_losing_history(self):
        self.s.finish(self.step['id'],self.step['attempt'],result('blocked'))
        self.s.control(self.id,'pause',self.s.get_task(self.id)['revision'])
        self.retry();self.assertEqual(self.s.claim('local')['role'],'Execute')
