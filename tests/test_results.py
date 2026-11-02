import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from core import Store,result_contract,validate_execution_workspace
from unittest.mock import patch
from agents import argv

def result(status='succeeded',summary='Completed with evidence.',details='Evidence details'):
    return '<acc_result>'+json.dumps(dict(status=status,summary=summary,details=details))+'</acc_result>'

class ResultContractTests(unittest.TestCase):
    def test_contract_rejects_missing_malformed_and_long_summary(self):
        for text in ['plain output','<acc_result>bad</acc_result>',result('unknown'),result(summary='a'*161),result(summary='two\nlines')]:
            with self.assertRaises(ValueError):result_contract(text,required=True)
        self.assertEqual(result_contract(result(),required=True)['status'],'succeeded')
    def test_blocked_or_failed_never_claims_next_step(self):
        for outcome,expected in [('blocked','Blocked'),('failed','Failed'),('succeeded','Queued')]:
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as root:
                store=Store(root,host='local')
                ident=store.create(dict(key='one',prompt='test',workspace=root,acceptance='Evidence'))['id']
                store.control(ident,'run',1);step=store.claim('local')
                store.finish(step['id'],step['attempt'],result(outcome,'One sentence.','Detailed evidence'))
                self.assertEqual(store.get_task(ident)['status'],expected)
                self.assertEqual(store.snapshot()['events'][-1]['output_summary'],'One sentence.')
                self.assertEqual(len(store.snapshot()['artifacts']),1)
                if outcome!='succeeded':self.assertIsNone(store.claim('local'))
                store.close()
    def test_malformed_tag_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root,host='local');ident=store.create(dict(key='one',prompt='test',workspace=root,acceptance='Evidence'))['id']
            store.control(ident,'run',1);step=store.claim('local')
            store.finish(step['id'],step['attempt'],'<acc_result>not JSON</acc_result>')
            self.assertEqual(store.get_task(ident)['status'],'Failed');self.assertIsNone(store.claim('local'));store.close()
    def test_missing_closer_preserves_negative_outcome_and_evidence(self):
        for outcome,expected in [('blocked','Blocked'),('failed','Failed')]:
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as root:
                text=result(outcome,'Disk query denied.','PermissionDenied; exit code 1.').removesuffix('</acc_result>')
                self.assertEqual(result_contract(text,required=True)['details'],'PermissionDenied; exit code 1.')
                store=Store(root,host='local')
                ident=store.create(dict(key='one',prompt='test',workspace=root,acceptance='Evidence'))['id']
                store.control(ident,'run',1);step=store.claim('local')
                store.finish(step['id'],step['attempt'],text)
                self.assertEqual(store.get_task(ident)['status'],expected)
                self.assertIsNone(store.claim('local'))
                self.assertEqual(len(store.snapshot()['artifacts']),1)
                store.close()

    def test_write_mode_scope_and_persistence(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root,host='local')
            for i,workspace in enumerate(['C:/','D:/Projects/../','/']):
                with self.assertRaises(ValueError):store.create(dict(key=str(i),prompt='test',workspace=workspace,acceptance='Evidence',execution_mode='workspace-write'))
            ident=store.create(dict(key='valid',prompt='test',workspace='D:/Projects/acc',acceptance='Evidence',execution_mode='workspace-write'))['id']
            self.assertEqual(store.get_task(ident)['execution_mode'],'workspace-write');store.close()

    @patch('agents.shutil.which',return_value='/mock/codex')
    def test_scoped_write_argv_keeps_sandbox(self,_):
        readonly=argv('codex'); writable=argv('codex',execution_mode='workspace-write')
        self.assertNotIn('sandbox_workspace_write.network_access=true',readonly)
        self.assertIn('sandbox_workspace_write.network_access=true',writable)
        self.assertEqual(writable[writable.index('--sandbox')+1],'workspace-write')
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',writable)
        self.assertNotIn('danger-full-access',writable)
        with self.assertRaises(ValueError):argv('claude',execution_mode='workspace-write')
    def test_protected_workspaces_are_rejected(self):
        for path in ['C:/Windows/System32','C:/Program Files/App',str(Path.home()/'.codex'/'sessions')]:
            with self.assertRaises(ValueError):validate_execution_workspace(path)
        with patch.dict('os.environ',{'CODEX_HOME':'D:/AgentState/codex'}):
            for path in ['D:/AgentState/codex','D:/AgentState/codex/sessions','D:/AgentState']:
                with self.assertRaises(ValueError):validate_execution_workspace(path)
            validate_execution_workspace('D:/Projects/acc')

class ReviewerLoopTests(unittest.TestCase):
    def test_review_returns_feedback_then_completes(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root,host='local')
            ident=store.create(dict(key='review',prompt='Implement',workspace=root,acceptance='Tests pass'))['id']
            store.control(ident,'run',1)
            def finish(status='succeeded',details='Tests pass'):
                step=store.claim('local');self.assertIsNotNone(step)
                store.finish(step['id'],step['attempt'],result(status,details=details))
                return step
            finish();finish();finish('failed','Fix the incorrect total and rerun the test.')
            execute=store.claim('local')
            self.assertEqual(execute['role'],'Execute')
            self.assertIn('Fix the incorrect total',execute['context'][-1]['output'])
            store.finish(execute['id'],execute['attempt'],result())
            finish()
            self.assertEqual(store.get_task(ident)['status'],'Completed')
            self.assertEqual(store.get_task(ident)['review_rounds'],1)
            self.assertEqual(store.db.execute('SELECT count(*) FROM artifacts').fetchone()[0],5)
            store.close()

    def test_rework_limit_and_external_block(self):
        for outcome in ('failed','blocked'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as root:
                store=Store(root,host='local')
                ident=store.create(dict(key='loop',prompt='Implement',workspace=root,acceptance='Tests pass'))['id']
                store.control(ident,'run',1)
                for index in range(9 if outcome=='failed' else 3):
                    step=store.claim('local');self.assertIsNotNone(step)
                    value=outcome if step['role']=='Review' else 'succeeded'
                    store.finish(step['id'],step['attempt'],result(value,details='Fix the failing test.' if value=='failed' else 'Evidence or external obstacle.'))
                self.assertEqual(store.get_task(ident)['status'],'Blocked')
                self.assertIsNone(store.claim('local'))
                store.close()

    def test_legacy_waiting_task_is_sent_back_to_reviewer(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root,host='local')
            ident=store.create(dict(key='legacy',prompt='Implement',workspace=root,acceptance='Tests pass'))['id']
            store.control(ident,'run',1)
            for _ in range(3):
                step=store.claim('local');store.finish(step['id'],step['attempt'],result())
            store.db.execute("UPDATE tasks SET status='Verifying' WHERE id=?",(ident,));store.db.commit()
            store.control(ident,'review',store.get_task(ident)['revision'])
            step=store.claim('local');self.assertEqual(step['role'],'Review')
            store.finish(step['id'],step['attempt'],result())
            self.assertEqual(store.get_task(ident)['status'],'Completed')
            store.close()
