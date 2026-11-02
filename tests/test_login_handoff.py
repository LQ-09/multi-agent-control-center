import io
import json
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core import Store
from login_handoff import LoginWindow, login_origin
from browser_tools import browser_lease

class LoginHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name,host='local'); self.addCleanup(self.store.close)
        self.ident=self.store.create({'key':'login','prompt':'Research','acceptance':'Source evidence','workspace':self.temp.name})['id']
        self.store.control(self.ident,'run',1)
        plan=self.store.claim('local'); self.store.finish(plan['id'],plan['attempt'],'Plan ready')
        step=self.store.claim('local')
        self.progress='<acc_result>'+json.dumps({'status':'blocked','reason':'login_required','login_url':'https://example.com/login?code=private','summary':'Login needed','details':'Saved finding; remaining price check.'})+'</acc_result>'
        self.store.finish(step['id'],step['attempt'],self.progress)

    def control(self,action):
        self.store.control(self.ident,action,self.store.get_task(self.ident)['revision'])

    def test_wait_has_no_lease_and_retries_only_current_stage_with_progress(self):
        task=self.store.get_task(self.ident)
        self.assertEqual(task['status'],'Waiting for Login')
        self.assertEqual(task['login_url'],'https://example.com/')
        self.assertTrue(all(s['lease'] is None for s in self.store.snapshot()['steps']))
        self.assertIsNone(self.store.claim('local'))
        self.control('retry')
        step=self.store.claim('local')
        self.assertEqual(step['role'],'Execute')
        self.assertIn(self.progress,[x['output'] for x in step['context']])

    def test_handoff_closes_before_resuming_and_does_not_assume_login_success(self):
        window=LoginWindow(self.store,'local')
        process=Mock(); process.stdin=io.BytesIO(); process.poll.return_value=None
        self.control('login_open')
        with patch('login_handoff.browser_server',return_value={'command':'node','args':['cli','--browser','msedge']}), patch('login_handoff.browser_lease',return_value=nullcontext()), patch('login_handoff.subprocess.Popen',return_value=process):
            self.assertTrue(window.tick())
        self.assertIsNone(self.store.claim('local'))
        self.control('login_continue'); window.tick()
        self.assertEqual(process.stdin.getvalue(),b'close\n')
        self.assertIsNone(self.store.claim('local'))
        process.poll.return_value=0; window.tick()
        self.assertEqual(self.store.get_task(self.ident)['status'],'Queued')
        step=self.store.claim('local')
        self.assertEqual(step['role'],'Execute')
        self.assertIn('Saved finding',step['context'][-1]['output'])

    def test_manual_close_requires_explicit_continue(self):
        window=LoginWindow(self.store,'local'); self.control('login_open')
        process=Mock(); process.stdin=io.BytesIO(); process.poll.return_value=0
        window.ident=self.ident; window.process=process
        with self.store.transaction(): self.store.db.execute("UPDATE tasks SET login_state='open' WHERE id=?",(self.ident,))
        window.tick()
        self.assertEqual(self.store.get_task(self.ident)['status'],'Waiting for Login')
        self.control('login_continue')
        self.assertEqual(self.store.get_task(self.ident)['status'],'Queued')

    def test_browser_profile_exclusive_and_login_url_restricted(self):
        with patch('browser_tools.runtime_root',return_value=Path(self.temp.name)):
            with browser_lease():
                with self.assertRaises(RuntimeError):
                    with browser_lease(): pass
            with browser_lease(): pass
        for url in ['file:///tmp/a','http://example.com','https://user:secret@example.com']:
            with self.assertRaises(ValueError):login_origin(url)
