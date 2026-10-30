import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from providers import Providers, NoRedirect
from bridge import Bridge, remote_command
from core import Store
from agents import run

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Providers(self.tmp.name)
        self.config={'id':'test','name':'Test model','base_url':'https://example.com/v1','model':'test-model','key_env':'ACC_TEST_KEY'}
        self.p.save(self.config)
    def tearDown(self):self.tmp.cleanup()
    def test_session_key_never_persists_or_returns_in_settings(self):
        self.p.set_key('test','dummy-session-secret')
        self.assertNotIn('dummy-session-secret',self.p.path.read_text())
        self.assertNotIn('dummy-session-secret',json.dumps(self.p.list()))
        self.assertFalse(Providers(self.tmp.name).list()[0]['key_ready'])
        self.assertTrue(self.p.list()[0]['key_ready'])
    def test_endpoint_change_clears_session_key(self):
        self.p.set_key('test','dummy-key');self.p.save({**self.config,'base_url':'https://other.example/v1'})
        self.assertFalse(self.p.list()[0]['key_ready'])
    def test_http_only_on_loopback_and_no_url_credentials(self):
        for url in ['http://example.com','https://user:pass@example.com','https://example.com?key=secret','file:///tmp/a','https://example.com/v1/chat/completions']:
            with self.subTest(url=url),self.assertRaises(ValueError):self.p.save({**self.config,'base_url':url})
        self.p.save({**self.config,'base_url':'http://127.0.0.1:11434/v1'})
    def test_redirect_does_not_forward_authorization(self):
        with self.assertRaises(ValueError):NoRedirect().redirect_request(None,None,302,'',{},'https://other.example')
    def test_chat_payload_and_response_contract(self):
        self.p.set_key('test','dummy-key')
        response=io.BytesIO(json.dumps({'choices':[{'message':{'content':'Result dummy-key'},'finish_reason':'stop'}]}).encode())
        opener=MagicMock();opener.open.return_value=response
        with patch('providers.urllib.request.build_opener',return_value=opener):
            self.assertEqual(self.p.complete('test','A task'),'Result [REDACTED]')
        request=opener.open.call_args.args[0];body=json.loads(request.data)
        self.assertEqual(request.full_url,'https://example.com/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'),'Bearer dummy-key')
        self.assertEqual(body['messages'],[{'role':'user','content':'A task'}])
        self.assertNotIn('tools',body);self.assertFalse(body['stream'])
    def test_truncated_response_is_not_success(self):
        self.p.set_key('test','dummy-key')
        opener=MagicMock();opener.open.return_value=io.BytesIO(b'{"choices":[{"message":{"content":"partial"},"finish_reason":"length"}]}')
        with patch('providers.urllib.request.build_opener',return_value=opener),self.assertRaises(ValueError):self.p.complete('test','Task')

class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        with patch('bridge.threading.Thread.start'),patch('bridge.version',return_value={}):self.b=Bridge(self.tmp.name)
    def tearDown(self):self.b.local.close();self.b.demo.close();self.tmp.cleanup()
    def task(self):return self.b.dispatch({'op':'create','args':{'key':'one','title':'Task','prompt':'Review','acceptance':'Evidence','workspace':self.tmp.name,'agents':['codex']*3}})['id']
    def test_update_locks_mutations_and_failure_unlocks(self):
        ident=self.task()
        self.assertTrue(self.b.dispatch({'op':'prepare_update'})['ready'])
        with self.assertRaises(ValueError):self.b.dispatch({'op':'control','args':{'id':ident,'action':'run','revision':1}})
        self.assertEqual(self.b.dispatch({'op':'snapshot'})['tasks'][0]['id'],ident)
        self.b.dispatch({'op':'abort_update'})
        self.b.dispatch({'op':'control','args':{'id':ident,'action':'run','revision':1}})
        with self.assertRaises(ValueError):self.b.dispatch({'op':'prepare_update'})
        self.assertFalse(self.b.update_pending)
    def test_update_refuses_unknown_remote_and_active_worker(self):
        self.b.active=True
        with self.assertRaises(ValueError):self.b.dispatch({'op':'prepare_update'})
        self.b.active=False;self.b.config['mode']='live';self.b.connected=False
        with self.assertRaises(ValueError):self.b.dispatch({'op':'prepare_update'})
        self.assertFalse(self.b.update_pending)
    def test_fresh_install_is_local_and_never_opens_ssh(self):
        with patch('bridge.Remote') as remote:
            state=self.b.dispatch({'op':'snapshot'})
            self.assertEqual(state['mode'],'local');self.assertTrue(state['connected']);remote.assert_not_called()
    def test_single_host_runs_all_roles_without_windows(self):
        ident=self.task();self.b.local.control(ident,'run',1)
        for role in ['Plan','Execute','Review']:
            step=self.b.local.claim('local');self.assertEqual(step['role'],role)
            self.assertEqual(step['host'],'local');self.b.local.finish(step['id'],step['attempt'],'Evidence')
        self.assertEqual(self.b.local.get_task(ident)['status'],'Verifying')
        with self.assertRaises(ValueError):self.b.local.claim('windows')
    def test_saved_profile_and_authorities_remain_isolated(self):
        ident=self.task()
        self.b.dispatch({'op':'save_environment','args':{'id':'demo-profile','name':'Demo profile','config':{**self.b.config,'mode':'demo'}}})
        self.b.dispatch({'op':'activate_environment','args':{'id':'demo-profile'}})
        self.assertEqual(self.b.dispatch({'op':'snapshot'})['tasks'],[])
        self.b.dispatch({'op':'configure','args':{'mode':'local'}})
        self.assertEqual(self.b.dispatch({'op':'snapshot'})['tasks'][0]['id'],ident)
    def test_switch_rejected_with_queued_task(self):
        ident=self.task();self.b.local.control(ident,'run',1)
        with self.assertRaises(ValueError):self.b.dispatch({'op':'configure','args':{'mode':'demo'}})
        self.assertEqual(self.b.config['mode'],'local')
    def test_unknown_provider_rejected_before_task_creation(self):
        with self.assertRaises(ValueError):self.b.dispatch({'op':'create','args':{'agents':['api:missing']*3}})
    def test_posix_command_quotes_paths_and_does_not_inject(self):
        import shlex
        cfg={**self.b.config,'windows_service':"/tmp/worker's folder/service.py",'windows_root':'/tmp/state; touch BAD'}
        argv=shlex.split(remote_command(cfg))
        self.assertEqual(argv[0],'exec');self.assertIn(cfg['windows_service'],argv);self.assertIn(cfg['windows_root'],argv)
    def test_api_cancellation_discards_late_result(self):
        store=self.b.local
        ident=store.create({'key':'api','title':'API task','prompt':'Task','workspace':self.tmp.name,'acceptance':'Evidence','agents':['api:test']*3})['id']
        store.control(ident,'run',1);step=store.claim('local')
        providers=MagicMock();providers.get.return_value={'name':'Test','model':'mock'}
        entered=threading.Event();finish=threading.Event()
        def complete(*args):entered.set();finish.wait(3);return 'Late answer'
        providers.complete.side_effect=complete
        def call(op,args):return store.dispatch({'op':op,'args':args})
        worker=threading.Thread(target=run,args=(step,call),kwargs={'providers':providers});worker.start();self.assertTrue(entered.wait(2))
        store.control(ident,'cancel',store.get_task(ident)['revision']);finish.set();worker.join(5)
        self.assertFalse(worker.is_alive());self.assertEqual(store.get_task(ident)['status'],'Cancelled')
        self.assertEqual(store.snapshot()['artifacts'],[])
    def test_three_api_roles_require_final_acceptance(self):
        store=self.b.local
        ident=store.create({'key':'api-flow','title':'API workflow','prompt':'Analyze supplied text','workspace':self.tmp.name,'acceptance':'Three handoffs','agents':['api:test']*3})['id']
        store.control(ident,'run',1)
        providers=MagicMock();providers.get.return_value={'name':'Test','model':'mock'}
        providers.complete.return_value='Mock provider evidence'
        def call(op,args):return store.dispatch({'op':op,'args':args})
        for _ in range(3):run(store.claim('local'),call,providers=providers)
        self.assertEqual(providers.complete.call_count,3)
        self.assertEqual(store.get_task(ident)['status'],'Verifying')
        self.assertEqual(len(store.snapshot()['artifacts']),3)
    def test_posix_remote_service_handshake_without_public_listener(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,str(root/'backend/service.py'),'--root',str(Path(self.tmp.name)/'remote'),'--profile','single'],input='{"op":"hello"}\n{"op":"snapshot"}\n',capture_output=True,text=True,timeout=25)
        self.assertEqual(result.returncode,0,result.stderr)
        hello,snapshot=[json.loads(x) for x in result.stdout.splitlines()]
        self.assertEqual(hello['data']['protocol'],2);self.assertEqual(hello['data']['profile'],'single')
        self.assertEqual(snapshot['data']['tasks'],[])
