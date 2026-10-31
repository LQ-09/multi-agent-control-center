import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core import Store
from bridge import Bridge

class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        with patch('bridge.threading.Thread.start'),patch('bridge.version',return_value={'available':True}): self.b=Bridge(self.tmp.name)
        self.b.config.update(mode='live',remote_os='windows',profile='split',mac_workspace=self.tmp.name)
        self.b.connected=False; self.b.next_reconnect=float('inf')
        self.data=dict(key='one',prompt='Inspect this project',workspace='D:/project',acceptance='Evidence',agents=['codex']*3)
    def tearDown(self):
        for store in (self.b.demo,self.b.local,self.b.fallback):store.close()
        self.tmp.cleanup()
    def create(self): return self.b.dispatch({'op':'create','args':self.data})['id']
    def remote(self):
        self.b.remote=MagicMock();self.b.connected=True
        self.b.info={'windows_first':1,'planned_acceptance':1}
        self.b.remote.call.side_effect=lambda op,args=None: {'id':'remote-task'} if op=='create' else {'tasks':[],'steps':[],'events':[],'artifacts':[]}
    def test_connected_submission_routes_every_role_to_windows(self):
        self.remote();self.create()
        sent=next(c.args[1] for c in self.b.remote.call.call_args_list if c.args[0]=='create')
        store=Store(Path(self.tmp.name)/'remote')
        try:
            store.create(sent)
            self.assertEqual([s['host'] for s in store.snapshot()['steps']],['windows']*3)
        finally:store.close()
    def test_offline_submission_runs_locally_and_remains_local_after_reconnect(self):
        ident=self.create();self.assertEqual(ident,self.create())
        self.remote()
        self.b.dispatch({'op':'control','args':dict(id=ident,action='run',revision=1)})
        step=self.b.fallback.claim('local'); self.assertEqual(step['task']['workspace'],str(Path(self.tmp.name).resolve()))
        self.assertFalse(any(c.args[0]=='control' for c in self.b.remote.call.call_args_list))
        self.assertEqual(self.create(),ident)
        snap=self.b.dispatch({'op':'snapshot'})
        self.assertEqual(snap['tasks'][0]['authority'],'local')
    def test_remote_uncertain_create_never_falls_back_on_retry(self):
        self.remote();self.b.remote.call.side_effect=TimeoutError('Unknown response')
        # First operation after pinning is remote snapshot, which can also time out.
        with self.assertRaises(TimeoutError):self.create()
        self.b.connected=False
        with self.assertRaises(ValueError):self.create()
        self.assertEqual(self.b.fallback.snapshot()['tasks'],[])
    def test_windows_only_and_missing_directory_never_fall_back(self):
        self.data['host_requirement']='windows'
        with self.assertRaisesRegex(ValueError,'requires Windows'):self.create()
        self.data['host_requirement']='portable';self.data['fallback_workspace']='/missing-acc-project'
        with self.assertRaisesRegex(ValueError,'existing absolute'):self.create()
        self.data['fallback_workspace']=str(Path.home())
        with self.assertRaises(ValueError):self.create()
        self.assertEqual(self.b.fallback.snapshot()['tasks'],[])
    def test_missing_local_cli_blocks_fallback(self):
        self.b.local_agents={}
        with self.assertRaisesRegex(ValueError,'CLI unavailable'):self.create()
    def test_route_survives_broker_restart(self):
        ident=self.create()
        with patch('bridge.threading.Thread.start'),patch('bridge.version',return_value={'available':True}): b2=Bridge(self.tmp.name)
        try:
            b2.config.update(self.b.config);b2.connected=True;b2.info={'windows_first':1};b2.remote=MagicMock()
            self.assertEqual(b2.dispatch({'op':'create','args':self.data})['id'],ident)
            b2.remote.call.assert_not_called()
        finally:
            for store in (b2.demo,b2.local,b2.fallback):store.close()
    def test_no_remote_inflight_task_is_copied(self):
        self.b.last_live={'tasks':[dict(id='old',status='Running')],'steps':[],'events':[],'artifacts':[]}
        self.create();snap=self.b.dispatch({'op':'snapshot'})
        self.assertTrue(snap['stale']);self.assertEqual(len(snap['tasks']),2)
        self.assertEqual(len(self.b.fallback.snapshot()['tasks']),1)
        with self.assertRaises(ValueError):self.b.dispatch({'op':'control','args':dict(id='old',action='retry',revision=1)})
    def test_old_worker_refuses_new_automatic_routing(self):
        self.remote();self.b.info={}
        with self.assertRaisesRegex(ValueError,'Update'):self.create()
    def test_reconnect_attempts_are_rate_limited(self):
        self.b.next_reconnect=0
        with patch('bridge.Remote',side_effect=OSError('offline')) as connect:
            self.b.dispatch({'op':'snapshot'});self.b.dispatch({'op':'snapshot'})
            connect.assert_called_once()

class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name,host='local')
        self.ident=self.s.create(dict(key='t',prompt='test',workspace=self.tmp.name,acceptance='Evidence'))['id']
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def control(self,action):return self.s.control(self.ident,action,self.s.get_task(self.ident)['revision'])
    def finish(self,status='succeeded'):
        s=self.s.claim('local')
        self.s.finish(s['id'],s['attempt'],'<acc_result>'+json.dumps(dict(status=status,summary='One short handoff.',details='Evidence'))+'</acc_result>')
        return s
    def test_restart_cancelled_preserves_history_and_rejects_old_attempt(self):
        self.control('run');old=self.finish();self.control('cancel');before=self.s.snapshot()
        self.control('restart');new=self.s.claim('local')
        self.assertEqual(new['role'],'Plan');self.assertNotEqual(new['attempt'],old['attempt'])
        self.assertEqual(self.s.snapshot()['artifacts'],before['artifacts'])
        with self.assertRaises(ValueError):self.s.finish(old['id'],old['attempt'],'late')
    def test_archive_restore_never_deletes_evidence(self):
        self.control('run');self.finish();self.control('pause');before=self.s.snapshot()
        self.control('archive')
        self.assertEqual(self.s.snapshot()['artifacts'],[]);self.assertIsNone(self.s.claim('local'))
        with self.assertRaises(ValueError):self.control('run')
        self.control('restore');self.assertEqual(self.s.snapshot()['artifacts'],before['artifacts'])
        self.control('run');self.assertEqual(self.s.claim('local')['role'],'Execute')
    def test_unknown_execution_blocks_restart_and_delete(self):
        self.control('run');step=self.s.claim('local')
        self.s.db.execute('UPDATE steps SET lease=0 WHERE id=?',(step['id'],));self.s.db.commit();self.s.expire()
        for action in ('restart','archive'):
            with self.assertRaises(ValueError):self.control(action)
    def test_latest_versions_are_grouped_by_task_step_name(self):
        self.control('run');self.finish('blocked');self.control('retry');self.finish()
        artifacts=self.s.snapshot()['artifacts'];self.assertEqual(len(artifacts),1)
        self.assertEqual(artifacts[0]['versions'],2);self.assertEqual(artifacts[0]['summary'],'One short handoff.')
        self.assertEqual(len(self.s.artifact_versions(artifacts[0]['id'])),2)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM artifacts').fetchone()[0],2)
