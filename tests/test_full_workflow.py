import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from langgraph.types import Command
from src.discovery_agent import CompetitorCandidate
from src.extraction_agent import CompetitorProfile, EvidenceClaim
from src.research_agent import FollowupPlan
from src.persistence import research_session, start_run, load_run, review_run


def clients():
    search, followup, extract = Mock(), Mock(), Mock()
    search.search.return_value = {'results': [{'url': 'https://atlas.example/pricing', 'title': 'Atlas',
        'content': 'Pro plan costs USD 10.99 per user per month. Includes team projects.'}]}
    search.extract.return_value = {'results': []}
    followup.invoke.return_value = FollowupPlan()
    extract.invoke.return_value = CompetitorProfile(competitor_name='Atlas', pricing=[EvidenceClaim(
        value='USD 10.99', quote='Pro plan costs USD 10.99 per user per month.', status='verified',
        evidence_urls=['https://atlas.example/pricing'])])
    discover = Mock(return_value={'competitors': [CompetitorCandidate(name='Atlas', website='https://atlas.example/',
        rationale='Alternative', source_urls=['https://atlas.example/'])], 'errors': []})
    return dict(search_client=search, followup_model=followup, extraction_model=extract, discovery_runner=discover)


class FullWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'checkpoints.sqlite'
        self.dependencies = clients()

    def start(self, run='run-one'):
        return start_run(run, 'Notion', 'Productivity software', db_path=self.db, **self.dependencies)

    def test_checkpoint_reopen_interrupt_approve_and_report(self):
        state = self.start()
        self.assertEqual(state['approval_status'], 'pending')
        self.assertEqual(state['repair_count'], 2)
        self.assertFalse(state.get('final_report'))
        calls = self.dependencies['search_client'].search.call_count
        reopened = load_run('run-one', db_path=self.db)
        self.assertEqual(reopened['verification'], state['verification'])
        self.assertEqual(reopened['competitors'], state['competitors'])
        approved = review_run('run-one', 'approve', state['review_token'], db_path=self.db, **self.dependencies)
        self.assertEqual(approved['approval_status'], 'approved')
        self.assertIn('USD 10.99', approved['final_report'])
        self.assertIn('Research gaps', approved['final_report'])
        self.assertIn('Strategic opportunities', approved['final_report'])
        self.assertEqual(self.dependencies['search_client'].search.call_count, calls)
        again = review_run('run-one', 'approve', state['review_token'], db_path=self.db, **self.dependencies)
        self.assertEqual(len(again['approval_history']), 1)

    def test_rejection_never_produces_report(self):
        state = self.start()
        rejected = review_run('run-one', 'reject', state['review_token'], db_path=self.db, **self.dependencies)
        self.assertEqual(rejected['approval_status'], 'rejected')
        self.assertFalse(rejected.get('final_report'))

    def test_revision_limit_and_stale_review_token(self):
        first = self.start()
        second = review_run('run-one', 'revise', first['review_token'], feedback='Check news', db_path=self.db, **self.dependencies)
        self.assertEqual(second['revision_count'], 1)
        stale = review_run('run-one', 'approve', first['review_token'], db_path=self.db, **self.dependencies)
        self.assertEqual(stale['approval_status'], 'pending')
        third = review_run('run-one', 'revise', second['review_token'], db_path=self.db, **self.dependencies)
        ended = review_run('run-one', 'revise', third['review_token'], db_path=self.db, **self.dependencies)
        self.assertEqual(ended['approval_status'], 'revision_limit_reached')
        self.assertFalse(ended.get('final_report'))

    def test_start_same_thread_does_not_repeat_searches(self):
        self.start()
        calls = self.dependencies['search_client'].search.call_count
        self.start()
        self.assertEqual(self.dependencies['search_client'].search.call_count, calls)

    def test_secrets_never_enter_checkpoint(self):
        state = self.start()
        import json
        self.assertNotIn('api_key', json.dumps(state).lower())
        self.assertNotIn('authorization', json.dumps(state).lower())

    def test_checkpoint_load_in_fresh_python_process(self):
        import subprocess
        import sys
        self.start()
        code = ('from src.persistence import load_run; import sys; '
                "state=load_run('run-one',db_path=sys.argv[1]); "
                "print(state['approval_status'],state['repair_count'],state['_interrupted'])")
        result = subprocess.run([sys.executable, '-B', '-c', code, str(self.db)], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), 'pending 2 True')
