import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


PENDING = {'company': 'Notion', 'industry': 'Productivity software', 'approval_status': 'pending',
           'review_token': 'token-one', '_interrupted': True, '_pending_nodes': ['human_review'],
           'verification': {}, 'gaps': ['News not verified'], 'errors': [], 'repair_count': 2}


class WorkflowUITests(unittest.TestCase):
    def test_full_run_pauses_and_approval_does_not_repeat(self):
        approved = dict(PENDING, approval_status='approved', final_report='# Approved briefing', _interrupted=False)
        with patch('src.workflow_ui.start_run', return_value=PENDING) as start, patch(
                'src.workflow_ui.load_run', side_effect=lambda *a, **kw: approved if review.called else PENDING), patch(
                'src.workflow_ui.review_run', return_value=approved) as review:
            app = AppTest.from_file('../app.py').run()
            app.button(key='run_full').click().run()
            self.assertFalse(app.exception)
            self.assertIn('News not verified', [element.value for element in app.text])
            app.button(key='approve_token-one').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Approved briefing' in element.value for element in app.markdown))
            app.run()
            start.assert_called_once()
            review.assert_called_once()

    def test_existing_run_load_is_read_only(self):
        with patch('src.workflow_ui.load_run', return_value=PENDING) as load, patch('src.workflow_ui.start_run') as start, patch('src.workflow_ui.review_run') as review:
            app = AppTest.from_file('../app.py')
            app.query_params['run'] = 'saved-run'
            app.run()
            self.assertFalse(app.exception)
            start.assert_not_called()
            review.assert_not_called()
            self.assertTrue(load.called)
