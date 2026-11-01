import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from core import Store
from workspaces import git, document
from agents import prompt_for


def make_repo(path, text='original'):
    path.mkdir()
    git(path, 'init')
    (path/'README.md').write_text(text)
    (path/'source.txt').write_text('initial source')
    git(path, 'add', '.')
    git(path, '-c', 'user.name=ACC tests', '-c', 'user.email=acc@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-m', 'Initial fixture')
    return path


def result(status='succeeded'):
    return '<acc_result>'+json.dumps(dict(status=status, summary='Verified fixture.', details='Local test evidence.'))+'</acc_result>'


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.repo = make_repo(self.root/'repo')
        self.store = Store(self.root/'state', host='local')
        self.project = self.store.workspaces.save(dict(name='Test project', repo_path=str(self.repo),
            documents=['README.md'], rules='Use outputs for reports.'))

    def tearDown(self):
        self.store.close(); self.tmp.cleanup()

    def create(self, key='one'):
        return self.store.create(dict(key=key, prompt='Change source', project_id=self.project['id'],
            acceptance='Source checked', execution_mode='workspace-write'))['id']

    def control(self, ident, action):
        return self.store.control(ident, action, self.store.get_task(ident)['revision'])

    def claim(self, ident):
        self.control(ident, 'run')
        return self.store.claim('local')

    def finish(self, step, status='succeeded'):
        return self.store.finish(step['id'], step['attempt'], result(status))

    def test_task_isolation_pinned_docs_and_original_uncommitted_files(self):
        first = self.create()
        (self.repo/'source.txt').write_text('user uncommitted work')
        one = self.claim(first)
        self.assertEqual((Path(one['task']['workspace'])/'source.txt').read_text(), 'initial source')
        self.control(first, 'pause')
        self.store.finish(one['id'], one['attempt'], '', stopped='pause')
        second = self.create('two'); two = self.claim(second)
        self.assertNotEqual(one['task']['workspace'], two['task']['workspace'])
        self.assertNotEqual(one['workspace_context']['branch'], two['workspace_context']['branch'])
        self.assertEqual(one['workspace_context']['shared_documents'], {'README.md':'original'})
        self.assertEqual((self.repo/'source.txt').read_text(), 'user uncommitted work')
        self.assertEqual(git(self.repo, 'branch', '--show-current'), git(self.repo, 'symbolic-ref', '--short', 'HEAD'))

    def test_all_roles_get_same_workspace_and_review_sees_executor_changes(self):
        ident = self.create(); plan = self.claim(ident); self.finish(plan)
        execute = self.store.claim('local')
        target = Path(execute['task']['workspace'])/'source.txt'; target.write_text('implemented')
        self.finish(execute); review = self.store.claim('local')
        self.assertEqual(plan['task']['workspace'], review['task']['workspace'])
        self.assertEqual(target.read_text(), 'implemented')
        self.assertNotEqual(plan['workspace_context']['context_hash'], review['workspace_context']['context_hash'])
        self.assertEqual(review['workspace_context']['shared_documents'], plan['workspace_context']['shared_documents'])
        for agent in ('codex','claude','api:example'):
            review['agent']=agent
            self.assertIn('Use outputs for reports.', prompt_for(review))
            self.assertIn('original', prompt_for(review))
        self.assertEqual(self.finish(review)['status'], 'Completed')
        self.assertEqual((self.repo/'source.txt').read_text(), 'initial source')

    def test_external_changes_between_roles_block_execution(self):
        ident=self.create(); plan=self.claim(ident);self.finish(plan)
        (Path(plan['task']['workspace'])/'source.txt').write_text('external modification')
        self.assertIsNone(self.store.claim('local'))
        self.assertEqual(self.store.get_task(ident)['status'],'Blocked')
        self.assertIn('changed since', self.store.snapshot()['steps'][1]['error'])

    def test_readonly_changes_fail_even_when_agent_claims_success(self):
        ident=self.create(); plan=self.claim(ident)
        (Path(plan['task']['workspace'])/'source.txt').write_text('unauthorized')
        self.assertEqual(self.finish(plan)['status'],'Failed')
        self.assertIsNone(self.store.claim('local'))

    def test_retry_preserves_partial_work_restart_allocates_new_workspace(self):
        ident=self.create(); plan=self.claim(ident); self.finish(plan)
        execute=self.store.claim('local');target=Path(execute['task']['workspace'])/'source.txt'
        target.write_text('partial work');self.finish(execute,'failed'); self.control(ident,'retry')
        retry=self.store.claim('local');self.assertEqual(retry['task']['workspace'],execute['task']['workspace'])
        self.assertEqual(target.read_text(),'partial work');self.finish(retry,'failed')
        self.control(ident,'restart'); fresh=self.store.claim('local')
        self.assertNotEqual(fresh['task']['workspace'],execute['task']['workspace'])
        self.assertEqual((Path(fresh['task']['workspace'])/'source.txt').read_text(),'initial source')
        self.assertTrue(target.exists())
        with self.assertRaises(ValueError):self.finish(execute)

    def test_cache_checks_identity_and_commit_without_changing_local_checkout(self):
        clone=self.root/'clone';git(self.root,'clone',str(self.repo),str(clone))
        other=make_repo(self.root/'other','different repository')
        config=self.store.workspaces.bind(self.project['id'])
        with self.assertRaisesRegex(ValueError,'does not match'):
            self.store.workspaces.cache(config,str(other),'remote:test:state')
        with self.assertRaises(ValueError):
            self.store.workspaces.cache(dict(config,base_commit='1'*40),str(clone),'remote:test:state')
        original=git(clone,'rev-parse','HEAD')
        cached=self.store.workspaces.cache(config,str(clone),'remote:test:state')
        self.assertEqual(cached['source_authority'],'remote:test:state')
        self.assertEqual(git(clone,'rev-parse','HEAD'),original)

    def test_documents_reject_traversal_links_and_oversize(self):
        for path in ('../README.md','/etc/passwd','.git/config','C:/test','dir\\test'):
            with self.assertRaises(ValueError):document(self.repo,self.project['base_commit'],path)
        (self.repo/'link.md').symlink_to('/etc/passwd')
        (self.repo/'big.md').write_text('x'*12001)
        git(self.repo,'add','link.md','big.md')
        git(self.repo,'-c','user.name=ACC tests','-c','user.email=acc@example.invalid','-c','commit.gpgsign=false','commit','-m','Link fixture')
        for path in ('link.md','big.md'):
            with self.assertRaises(ValueError):document(self.repo,git(self.repo,'rev-parse','HEAD'),path)

    def test_context_survives_restart_and_existing_tasks_keep_policy(self):
        ident=self.create()
        self.store.workspaces.save(dict(self.project,rules='Updated rules',documents=[]))
        step=self.claim(ident)
        self.assertEqual(step['workspace_context']['rules'],'Use outputs for reports.')
        expected=self.store.workspaces.context(ident)
        self.store.close();self.store=Store(self.root/'state',host='local')
        self.assertEqual(self.store.workspaces.context(ident),expected)

    def test_legacy_tasks_are_not_moved_or_assigned_worktrees(self):
        ident=self.store.create(dict(key='legacy',prompt='inspect',workspace=str(self.repo),acceptance='check'))['id']
        step=self.claim(ident)
        self.assertNotIn('workspace_context',step)
        self.assertEqual(step['task']['workspace'],str(self.repo))
        self.assertEqual(self.store.snapshot()['workspaces'],[])

    def test_raw_paths_do_not_trigger_implicit_offline_fallback(self):
        from routing import Routing
        route=Routing(self.store)
        config=dict(ssh_alias='test',windows_root='state',mac_workspace=str(self.repo))
        with self.assertRaisesRegex(ValueError,'registered project'):
            route.submission(dict(key='raw',workspace='D:/other'),config,False)

    def test_acceptance_rechecks_source_and_idempotent_create_does_not_rebind(self):
        ident=self.create(); plan=self.claim(ident);self.finish(plan)
        self.finish(self.store.claim('local')); review=self.store.claim('local')
        (Path(review['task']['workspace'])/'source.txt').write_text('changed after review')
        self.assertEqual(self.finish(review)['status'],'Failed')
        self.assertEqual(self.create(),ident)

    def test_real_subprocess_receives_actual_cwd_and_context(self):
        from agents import run
        script=self.root/'fake_cli.py'
        script.write_text('''import sys,json,os
from pathlib import Path
prompt=sys.stdin.read()
context=json.loads(prompt.split('Bound project context (shared by all adapters):\\n')[1])
assert str(Path.cwd())==context['workspace']
assert context['shared_documents']['README.md']=='original'
assert context['output_root'].startswith(str(Path.cwd()))
if 'You are the Execute agent' in prompt:
    Path('source.txt').write_text('subprocess implementation')
result='<acc_result>'+json.dumps(dict(status='succeeded',summary='Verified fake CLI.',details='Context and cwd matched.'))+'</acc_result>'
print(json.dumps(dict(type='item.completed',item=dict(type='agent_message',text=result))))
''')
        ident=self.create();self.control(ident,'run')
        with patch('agents.argv',return_value=[sys.executable,str(script)]):
            for _ in range(3):
                step=self.store.claim('local')
                run(step,lambda op,args:self.store.dispatch(dict(op=op,args=args)))
        self.assertEqual(self.store.get_task(ident)['status'],'Completed')
        self.assertEqual((self.repo/'source.txt').read_text(),'initial source')
        self.assertEqual((Path(step['task']['workspace'])/'source.txt').read_text(),'subprocess implementation')

    def test_snapshot_does_not_repeat_pinned_documents_or_walk_task_files(self):
        from bridge import metadata_size
        ident=self.create();self.claim(ident)
        self.assertNotIn('project_config',self.store.snapshot()['tasks'][0])
        before=metadata_size(self.store.root)
        (self.store.root/'workspaces'/'large-fixture.bin').write_bytes(b'x'*10000)
        self.assertEqual(metadata_size(self.store.root),before)
