import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from core import Store
from interactive_worker import heartbeat, fresh, tick, guarded_call, session_id

class InteractiveWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.controller = Store(self.tmp.name)
        self.worker = Store(self.tmp.name)
    def tearDown(self):
        self.worker.close(); self.controller.close(); self.tmp.cleanup()
    def test_heartbeat_shared_only_on_same_host_db(self):
        heartbeat(self.worker, 'worker', {'time': time.time(), 'profile': 'split', 'session_id': 1})
        self.assertEqual(tick(self.controller, 'split')['executor']['session_id'], 1)
        self.assertTrue(fresh(heartbeat(self.worker, 'controller')))
    def test_missing_stale_or_wrong_profile_executor_fails_closed(self):
        for value in ({}, {'time': time.time()-20, 'profile':'split'}, {'time':time.time(), 'profile':'single'}):
            heartbeat(self.worker, 'worker', value)
            with self.assertRaisesRegex(RuntimeError, 'offline or profile'):
                tick(self.controller, 'split')
    def test_disconnect_stops_claim_and_pulse(self):
        for op in ('claim', 'pulse'):
            with self.assertRaisesRegex(RuntimeError, 'heartbeat lost'):
                guarded_call(self.worker, 'split', op, {})
    def test_transactions_prevent_duplicate_claims(self):
        task = self.controller.create({'key':'test','prompt':'test','workspace':'C:/','agents':['codex']*3})
        self.controller.control(task['id'], 'run', 1)
        heartbeat(self.controller, 'controller', {'time':time.time(), 'profile':'split'})
        step = guarded_call(self.worker, 'split', 'claim', {'host':'mac'})
        self.assertIsNotNone(step)
        self.assertIsNone(self.controller.claim('mac'))
    def test_session_zero_rejected(self):
        with patch('interactive_worker.os.name', 'nt'), patch('interactive_worker.ctypes.windll', create=True) as dll:
            dll.kernel32.ProcessIdToSessionId.return_value = 1
            with self.assertRaisesRegex(RuntimeError, 'not SSH'):
                session_id()
    def test_future_heartbeat_not_valid(self):
        self.assertFalse(fresh({'time':time.time()+60}))

class InstallerTests(unittest.TestCase):
    def test_task_uses_interactive_limited_identity_and_no_password(self):
        from install_interactive_worker import script
        text = script('C:/Python/python.exe', Path("C:/ACC's/backend/interactive_worker.py"), Path('D:/ACC state'), 'split')
        self.assertIn('-LogonType Interactive -RunLevel Limited', text)
        self.assertIn('-MultipleInstances IgnoreNew', text)
        self.assertNotIn('-Password', text)
        self.assertNotIn('-Force', text)
        self.assertIn("ACC''s", text)
