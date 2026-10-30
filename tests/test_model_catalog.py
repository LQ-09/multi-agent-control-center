import sys,unittest,tempfile,io,json,time
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from agent_settings import validate_catalog
from agent_monitor import AgentMonitor,claude_models
from providers import Providers
class CatalogTests(unittest.TestCase):
    @patch('agent_monitor.claude_usage',side_effect=TimeoutError('usage timeout'))
    @patch('agent_monitor.claude_models',return_value=[{'id':'opus','name':'Opus','efforts':['high']}])
    def test_usage_failure_keeps_successful_claude_models(self,models,usage):
        from agent_monitor import probe_claude
        row=probe_claude('/mock/claude')
        self.assertEqual(row['models'][0]['id'],'opus');self.assertTrue(row['models_checked_at'])
        self.assertEqual(row['status'],'unavailable')
    @patch('agent_monitor.threading.Thread.start')
    def test_recent_usage_does_not_make_old_catalog_fresh(self,_):
        m=AgentMonitor();m.rows={'codex':{'checked_at':'2099-01-01T00:00:00Z','models_checked_at':'2000-01-01T00:00:00Z','models':[{'id':'m','efforts':[]}]}}
        with self.assertRaises(ValueError):m.validate_selection('codex',{'model':'m','effort':''})
    def test_wrong_agent_model_and_effort_rejected(self):
        models=[{'id':'codex-example','efforts':['low','high']}]
        for value in [{'model':'opus-5.5','effort':''},{'model':'codex-example','effort':'ultra'},{'model':'','effort':'high'}]:
            with self.assertRaises(ValueError):validate_catalog('codex',value,models)
        validate_catalog('codex',{'model':'codex-example','effort':'high'},models)
        validate_catalog('codex',{'model':'','effort':''},[])
    def test_invalid_model_fails_step_without_starting_inference_process(self):
        from core import Store
        from agents import run
        with tempfile.TemporaryDirectory() as root:
            store=Store(root,host='local')
            ident=store.create({'key':'bad-model','prompt':'Review files','workspace':root,'acceptance':'Evidence','agent_options':[{'model':'opus-5.5','effort':''}]*3})['id']
            store.control(ident,'run',1);step=store.claim('local')
            with patch('agents.shutil.which',return_value='/fake/codex'),patch('agent_monitor.probe_codex',return_value={'models':[{'id':'codex-example','efforts':['high']}]}),patch('agents.subprocess.Popen') as launch:
                run(step,lambda op,args:store.dispatch({'op':op,'args':args}))
                launch.assert_not_called()
            self.assertEqual(store.get_task(ident)['status'],'Failed')
            self.assertIn('not in the current codex model list',store.snapshot()['steps'][0]['error']);store.close()
    def test_old_model_with_no_effort_and_extended_context(self):
        validate_catalog('claude',{'model':'opus[1m]','effort':''},[{'id':'opus[1m]','efforts':[]}])
        with self.assertRaises(ValueError):validate_catalog('claude',{'model':'haiku-old','effort':'high'},[{'id':'haiku-old','efforts':[]}])
    @patch('agent_monitor.threading.Thread.start')
    def test_unavailable_or_stale_catalog_does_not_accept_override(self,_):
        m=AgentMonitor()
        with self.assertRaises(ValueError):m.validate_selection('codex',{'model':'fake','effort':''})
        m.rows={'codex':{'checked_at':'2000-01-01T00:00:00Z','models':[{'id':'fake','efforts':[]}]}}
        with self.assertRaises(ValueError):m.validate_selection('codex',{'model':'fake','effort':''})
        m.validate_selection('codex',{'model':'','effort':''})
    @patch('agent_monitor.JsonProcess')
    def test_claude_initialize_never_sends_inference(self,process):
        p=process.return_value;p.next.return_value={'type':'control_response','response':{'request_id':'acc-models','subtype':'success','response':{'models':[{'value':'opus','displayName':'Opus','supportsEffort':True,'supportedEffortLevels':['low','max']},{'value':'haiku-old','supportsEffort':False}]}}}
        rows=claude_models('/fake/claude')
        self.assertEqual(rows[0]['efforts'],['low','max']);self.assertEqual(rows[1]['efforts'],[])
        self.assertEqual(p.send.call_args.args[0]['type'],'control_request');self.assertEqual(p.send.call_count,1);p.close.assert_called_once()
    def test_provider_catalog_validates_selection_and_does_not_save_key(self):
        with tempfile.TemporaryDirectory() as root:
            p=Providers(root);c={'id':'deepseek','name':'DeepSeek','base_url':'https://api.deepseek.com','model':'deepseek-flash','key_env':'DEEPSEEK_API_KEY','effort':'high'}
            opener=MagicMock();opener.open.return_value=io.BytesIO(json.dumps({'data':[{'id':'deepseek-flash','effort':{'supported_levels':['low','high','max']}}]}).encode())
            with patch('providers.urllib.request.build_opener',return_value=opener):rows=p.discover_models(c,'dummy-key')
            self.assertEqual(rows['models'][0]['efforts'],['low','high','max']);self.assertNotIn('dummy-key',json.dumps(rows))
            self.assertEqual(opener.open.call_args.args[0].get_method(),'GET')
            p.save_checked(c);self.assertNotIn('dummy-key',p.path.read_text())
            for bad in [{**c,'model':'opus-5.5'},{**c,'effort':'medium'}]:
                with self.assertRaises(ValueError):p.save_checked(bad)
            with self.assertRaises(ValueError):p.save_checked({**c,'base_url':'https://other.example'})
    def test_generic_metadata_does_not_invent_effort_mapping(self):
        with tempfile.TemporaryDirectory() as root:
            p=Providers(root);c={'id':'custom','name':'Custom','base_url':'http://127.0.0.1:1234/v1','model':'m','key_env':''}
            opener=MagicMock();opener.open.return_value=io.BytesIO(b'{"data":[{"id":"m","effort":{"supported_levels":["high"]}}]}')
            with patch('providers.urllib.request.build_opener',return_value=opener):rows=p.discover_models(c)
            self.assertEqual(rows['models'][0]['efforts'],[])
