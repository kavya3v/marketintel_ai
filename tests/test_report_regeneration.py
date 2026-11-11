import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.persistence import research_session, regenerate_briefing, load_run
from src.discovery_agent import DiscoveryError


class RegenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'runs.sqlite'

    def seed(self, status='approved'):
        with research_session(self.db) as graph:
            graph.update_state({'configurable': {'thread_id': 'saved'}}, {
                'company': 'Notion', 'industry': 'Productivity software', 'approval_status': status,
                'research_timestamp': '2026-11-10T00:00:00+00:00', 'verification': {}, 'gaps': [],
                'errors': [], 'final_report': '# Original report', 'approval_history': [{'action': 'approve'}]}, as_node='briefing')

    def test_archive_and_idempotent_regeneration_without_any_nodes(self):
        self.seed()
        from langgraph.graph.state import CompiledStateGraph
        with patch.object(CompiledStateGraph, 'invoke', side_effect=AssertionError('No graph execution allowed')):
            new = regenerate_briefing('saved', db_path=self.db)
            self.assertEqual(new['original_report'], '# Original report')
            self.assertEqual(new['report_history'][0]['report'], '# Original report')
            self.assertIn('Executive summary', new['final_report'])
            self.assertEqual(new['approval_history'], [{'action': 'approve'}])
            before = load_run('saved', db_path=self.db)
            again = regenerate_briefing('saved', db_path=self.db)
            self.assertEqual(before, again)
            self.assertFalse(again['_pending_nodes'])

    def test_pending_rejected_or_missing_run_cannot_regenerate(self):
        for status in ('pending', 'rejected'):
            self.seed(status)
            with self.assertRaises(DiscoveryError):
                regenerate_briefing('saved', db_path=self.db)
        with self.assertRaises(DiscoveryError):
            regenerate_briefing('missing', db_path=self.db)

    def test_no_new_checkpoint_when_already_current(self):
        self.seed()
        regenerate_briefing('saved', db_path=self.db)
        with research_session(self.db) as graph:
            old = graph.get_state({'configurable': {'thread_id': 'saved'}}).config
        regenerate_briefing('saved', db_path=self.db)
        with research_session(self.db) as graph:
            self.assertEqual(old, graph.get_state({'configurable': {'thread_id': 'saved'}}).config)

    def test_ui_regeneration_is_explicit_and_runs_once(self):
        from streamlit.testing.v1 import AppTest
        approved = {'approval_status': 'approved', 'company': 'Notion', 'industry': 'Productivity software',
                    'final_report': '# Old report', 'verification': {}, 'gaps': [], 'errors': [], '_pending_nodes': []}
        regenerated = dict(approved, final_report='# Improved report', original_report='# Old report',
                           report_history=[{'report': '# Old report'}])
        with patch('src.workflow_ui.load_run', side_effect=lambda *a, **kw: regenerated if generate.called else approved), patch(
                'src.workflow_ui.regenerate_briefing', return_value=regenerated) as generate:
            app = AppTest.from_file('../app.py')
            app.query_params['run'] = 'saved'
            app.run()
            generate.assert_not_called()
            app.button(key='regenerate_briefing').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Improved report' in element.value for element in app.markdown))
            app.run()
            generate.assert_called_once_with('saved')
