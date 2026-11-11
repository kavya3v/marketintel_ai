import unittest
from unittest.mock import Mock, patch
from src.research_agent import research_competitor
from src.discovery_agent import CompetitorCandidate


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.competitor = CompetitorCandidate(name='Atlas', website='https://atlas.example/',
                                              rationale='Alternative', source_urls=['https://atlas.example/'])

    def test_tavily_backoff_and_no_repeat_successful_search(self):
        client = Mock()
        client.search.side_effect = [TimeoutError(), {'results': [{'url': 'https://atlas.example/pricing',
            'title': 'Pricing', 'content': 'Pro costs $10.99 per month.'}]}]
        client.extract.return_value = {'results': []}
        with patch('src.research_agent.time.sleep') as sleep:
            first = research_competitor(self.competitor, client, categories=['pricing'])
        sleep.assert_called_once_with(0.5)
        self.assertEqual(client.search.call_count, 2)
        research_competitor(self.competitor, client, categories=['pricing'], previous=first)
        self.assertEqual(client.search.call_count, 2)

    def test_authentication_is_not_retried(self):
        client = Mock()
        failure = RuntimeError('secret')
        failure.status_code = 401
        client.search.side_effect = failure
        with patch('src.research_agent.time.sleep') as sleep:
            result = research_competitor(self.competitor, client, categories=['pricing'])
        self.assertEqual(client.search.call_count, 1)
        sleep.assert_not_called()
        self.assertTrue(result['errors'])

    def test_retry_exhaustion_records_gap(self):
        client = Mock()
        client.search.side_effect = TimeoutError()
        with patch('src.research_agent.time.sleep'):
            result = research_competitor(self.competitor, client, categories=['pricing'])
        self.assertEqual(client.search.call_count, 2)
        self.assertTrue(result['errors'])

    def test_extract_transient_retry_keeps_search_evidence(self):
        client = Mock()
        client.search.return_value = {'results': [{'url': 'https://atlas.example/pricing',
            'title': 'Pricing', 'content': 'Pro costs $10.99 per month.'}]}
        client.extract.side_effect = [TimeoutError(), {'results': [{'url': 'https://atlas.example/pricing',
            'raw_content': 'Pro plan costs $10.99 per month.'}]}]
        with patch('src.tool_recovery.time.sleep') as sleep:
            result = research_competitor(self.competitor, client, categories=['pricing'])
        self.assertEqual(client.extract.call_count, 2)
        self.assertEqual(result['extract_calls'], 2)
        sleep.assert_called_once_with(0.5)

    def test_discovery_tool_retry_cap_and_backoff(self):
        from src.tool_recovery import call_tavily
        operation = Mock(side_effect=TimeoutError())
        with patch('src.tool_recovery.time.sleep') as sleep, self.assertRaises(TimeoutError):
            call_tavily(operation, 'query', max_retries=2)
        self.assertEqual(operation.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.5, 1.0])

    def test_repair_preserves_previously_extracted_evidence(self):
        from src.research_agent import ResearchSource
        url = 'https://atlas.example/pricing'
        prior = {'sources': [ResearchSource(url=url, title='Pricing', snippet='Pro costs USD 10.99 per month. Includes team projects.',
            category='pricing', official=True, retrieved_at='2026-11-09T00:00:00+00:00')],
            'extracted_urls': [url]}
        client = Mock()
        client.search.return_value = {'results': [{'url': url, 'title': 'Pricing', 'content': 'Short pricing snippet'}]}
        result = research_competitor(self.competitor, client, categories=['pricing'], previous=prior, repair_round=1)
        self.assertTrue(any('Includes team projects' in s.snippet for s in result['sources']))
        self.assertTrue(any('Short pricing snippet' in s.snippet for s in result['sources']))
