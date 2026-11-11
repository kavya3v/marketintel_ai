import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from src.discovery_agent import DiscoveryError
from test_discovery_agent import candidate
from src.extraction_agent import CompetitorProfile, validate_profile

class AppTests(unittest.TestCase):
    def test_phase2_action_preserves_discovery_across_reruns(self):
        profile = validate_profile(CompetitorProfile(competitor_name='Atlas'), 'Atlas', [])
        with patch('src.discovery_agent.discover_competitors', return_value={'competitors': [candidate()]} ) as discover, patch(
                'src.graph.generate_research_profiles', return_value={'profiles': {'Atlas': profile}, 'research': {}, 'errors': []}) as research:
            app = AppTest.from_file('../app.py').run()
            app.button[0].click().run()
            research.assert_not_called()
            app.button(key='generate_profiles').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(research.call_args.args[0]['company'], 'Notion')
            self.assertIn('research_result', app.session_state)
            app.run()
            discover.assert_called_once()
            research.assert_called_once()
            self.assertIn('Not verified', str(app))

    def test_initial_page(self):
        with patch('src.discovery_agent.discover_competitors') as discover:
            app = AppTest.from_file('../app.py').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.title[0].value, 'MarketIntel AI — Competitor Research Agent')
            self.assertEqual([w.value for w in app.text_input], ['Notion', 'Productivity software'])
            discover.assert_not_called()

    def test_submit_error(self):
        with patch('src.discovery_agent.discover_competitors', side_effect=DiscoveryError('Missing TAVILY_API_KEY.')):
            app = AppTest.from_file('../app.py').run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertIn('TAVILY_API_KEY', app.error[0].value)

    def test_submit_results(self):
        with patch('src.discovery_agent.discover_competitors', return_value={'competitors': [candidate()]}):
            app = AppTest.from_file('../app.py').run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.subheader[0].value, 'Atlas')
            self.assertIn('https://atlas.example/', str(app))
