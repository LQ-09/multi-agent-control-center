import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from bridge import Bridge

class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        Path(self.tmp.name,'connection.json').write_text(json.dumps({'mode':'live'}))
        with patch('bridge.threading.Thread.start'), patch('bridge.version',return_value={}):
            self.bridge=Bridge(self.tmp.name)
    def tearDown(self):
        self.bridge.demo.close()
        self.tmp.cleanup()
    def test_startup_connects_saved_live_settings_once(self):
        remote=MagicMock()
        remote.call.side_effect=lambda op,args=None: ({'os':'Windows','protocol':1} if op=='hello' else {'tasks':[]})
        with patch('bridge.Remote',return_value=remote) as factory:
            self.assertTrue(self.bridge.dispatch({'op':'snapshot'})['connected'])
            self.bridge.dispatch({'op':'snapshot'})
            factory.assert_called_once()
            self.assertEqual([c.args[0] for c in remote.call.call_args_list],['hello','snapshot','snapshot'])
    def test_error_survives_polling_and_reconnect_clears_it(self):
        remote=MagicMock()
        remote.call.side_effect=RuntimeError('Permission denied (publickey).')
        with patch('bridge.Remote',return_value=remote) as factory:
            first=self.bridge.dispatch({'op':'snapshot'})
            second=self.bridge.dispatch({'op':'snapshot'})
            self.assertEqual(first['error'],second['error'])
            self.assertIn('publickey',second['error'])
            self.assertTrue(second['stale'])
            factory.assert_called_once()
            remote.close.assert_called_once()
            remote.call.side_effect=lambda op,args=None: ({'os':'Windows','protocol':1} if op=='hello' else {'tasks':[]})
            self.bridge.dispatch({'op':'connect'})
            state=self.bridge.dispatch({'op':'snapshot'})
            self.assertTrue(state['connected'])
            self.assertIsNone(state['error'])
            self.assertFalse(state['stale'])
