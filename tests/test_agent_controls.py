import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core import Store
from agents import argv
from agent_settings import selection
from agent_monitor import codex_meters,claude_meters,AgentMonitor,JsonProcess
import time
from agents import CHILDREN
from bridge import Bridge

class AgentControlsTests(unittest.TestCase):
    def test_planner_generates_criteria_before_execution(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root,host='local')
            ident=store.create({'key':'automatic','prompt':'Review my project','workspace':root})['id']
            self.assertEqual(store.get_task(ident)['title'],'Review my project')
            store.control(ident,'run',1);step=store.claim('local')
            with self.assertRaises(ValueError):store.finish(step['id'],step['attempt'],'Plan without criteria')
            self.assertEqual(store.get_task(ident)['acceptance'],'')
            self.assertIsNone(store.claim('local'))
            store.finish(step['id'],step['attempt'],'Plan\n<acceptance_criteria>List findings with file references.</acceptance_criteria>')
            execute=store.claim('local')
            self.assertEqual(execute['task']['acceptance'],'List findings with file references.')
            self.assertEqual(execute['role'],'Execute')
            self.assertNotEqual(store.get_task(ident)['status'],'Completed');store.close()

    def test_query_subprocess_is_bounded_and_owned(self):
        with tempfile.TemporaryDirectory() as root:
            script=Path(root)/'fake.py'
            script.write_text('import sys,json,time\nfor line in sys.stdin:\n r=json.loads(line);print(json.dumps({"id":r["id"],"result":{"ready":True}}),flush=True)\n')
            process=JsonProcess([sys.executable,str(script)],root)
            self.assertIn(process.p,CHILDREN)
            try:self.assertEqual(process.request(1,'account/read',{},time.monotonic()+5),{'ready':True})
            finally:process.close()
            self.assertNotIn(process.p,CHILDREN);self.assertIsNotNone(process.p.poll())

    def test_defaults_persist_but_do_not_rewrite_existing_steps(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root,host='local')
            settings={'roles':['claude','codex','claude'],'codex':{'model':'example-codex','effort':'high'},'claude':{'model':'sonnet','effort':'medium'}}
            store.save_agent_defaults(settings)
            task={'key':'one','title':'Task','prompt':'Analyze','workspace':root,'acceptance':'Evidence'}
            ident=store.create(task)['id'];original=store.snapshot()['steps']
            self.assertEqual([s['agent'] for s in original],settings['roles']);self.assertEqual(original[1]['model'],'example-codex')
            store.save_agent_defaults({**settings,'codex':{'model':'different','effort':'low'}})
            self.assertEqual(store.create(task)['id'],ident)
            self.assertEqual(store.snapshot()['steps'],original)
            store.close();store=Store(root,host='local')
            self.assertEqual(store.agent_defaults()['codex']['model'],'different');store.close()
    def test_override_is_bound_to_created_task(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root,host='local')
            store.create({'key':'override','title':'Task','prompt':'Analyze','workspace':root,'acceptance':'Evidence','agents':['codex']*3,'agent_options':[{'model':'my-model','effort':'high'}]*3})
            self.assertEqual(store.snapshot()['steps'][0]['model'],'my-model');store.close()
    @patch('agents.shutil.which',return_value='/bin/agent')
    def test_cli_options_are_actually_passed(self,find):
        c=argv('codex','test-model','xhigh');self.assertIn('--model',c);self.assertIn('test-model',c);self.assertIn('model_reasoning_effort="xhigh"',c)
        self.assertIn('read-only',c);self.assertIn('never',c)
        c=argv('claude','sonnet','high');self.assertIn('--effort',c);self.assertIn('high',c);self.assertEqual(c[c.index('--tools')+1],'')
    def test_invalid_shell_arguments_and_api_effort_rejected(self):
        for model in ['x & whoami','%USERPROFILE%','$(id)','x\ny','--help']:
            with self.assertRaises(ValueError):selection('codex',{'model':model,'effort':''})
        with self.assertRaises(ValueError):selection('api:myapi',{'model':'','effort':'high'})
    def test_codex_windows_and_unknown_data(self):
        rows=codex_meters({'rateLimits':{'primary':{'usedPercent':25,'windowDurationMins':300,'resetsAt':1900000000},'secondary':{'usedPercent':100,'windowDurationMins':10080}}})
        self.assertEqual([r['remaining_percent'] for r in rows],[75,0]);self.assertIsNone(rows[1]['resets_at'])
        self.assertEqual(codex_meters({'rateLimits':{'primary':{'resetsAt':1900000000}}}),[])
        self.assertEqual(codex_meters({'rateLimits':{'primary':{'usedPercent':float('nan')}}}),[])
        rows=codex_meters({'rateLimitsByLimitId':{'shared':{'primary':{'usedPercent':10}},'model-a':{'primary':{'usedPercent':30}}}})
        self.assertEqual(len(rows),2)
    def test_claude_scoped_usage_is_not_context_or_cost(self):
        report={'session':{'total_cost_usd':99},'rate_limits':{'limits':[{'kind':'weekly_scoped','percent':40,'resets_at':'2030-01-01T00:00:00Z','scope':{'model':{'display_name':'Opus'}}}]}}
        row=claude_meters(report)[0];self.assertEqual(row['remaining_percent'],60);self.assertEqual(row['scope'],'Opus')
        self.assertEqual(claude_meters({'session':{'total_cost_usd':99},'rate_limits':None}),[])
    def test_failed_refresh_removes_old_quota(self):
        monitor=AgentMonitor();monitor.rows={'codex':{'status':'ok','meters':[{'remaining_percent':100}]}}
        with patch('agent_monitor.shutil.which',return_value=None):monitor._refresh()
        self.assertEqual(monitor.rows['codex']['status'],'unavailable');self.assertEqual(monitor.rows['codex']['meters'],[])
    def test_old_worker_rejects_explicit_model_instead_of_ignoring_it(self):
        with tempfile.TemporaryDirectory() as root,patch('bridge.threading.Thread.start'),patch('bridge.version',return_value={}):
            bridge=Bridge(root);bridge.config['mode']='live';bridge.info={'protocol':2}
            with self.assertRaisesRegex(ValueError,'v0.6'):bridge.dispatch({'op':'create','args':{'acceptance':'Evidence','agent_options':[{'model':'test','effort':'high'}]*3}})
            bridge.local.close();bridge.demo.close()
    def test_existing_database_adds_columns_without_losing_history(self):
        with tempfile.TemporaryDirectory() as root:
            db=sqlite3.connect(Path(root)/'control.sqlite')
            db.execute('CREATE TABLE steps(id TEXT PRIMARY KEY, task_id TEXT, position INTEGER, role TEXT, agent TEXT, host TEXT, status TEXT, output TEXT, attempt TEXT, session TEXT, lease REAL, error TEXT)')
            db.execute("INSERT INTO steps VALUES('old','task',0,'Plan','codex','local','Pending','','','','',NULL)");db.commit();db.close()
            store=Store(root,host='local');row=store.snapshot()['steps'][0]
            self.assertEqual(row['id'],'old');self.assertEqual(row['model'],'');self.assertEqual(row['effort'],'');store.close()
