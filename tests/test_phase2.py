import unittest
from unittest.mock import Mock
from src.discovery_agent import CompetitorCandidate
from src.research_agent import research_competitor, ResearchSource
from src.extraction_agent import CompetitorProfile, EvidenceClaim, validate_profile
from src.graph import build_research_graph


def competitor(name='Atlas'):
    return CompetitorCandidate(name=name, website=f'https://{name.lower()}.example/', rationale='Alternative', source_urls=['https://comparison.example/'])


def source(category='pricing', content='The Pro plan costs $10 per month.'):
    return ResearchSource(url='https://atlas.example/pricing', title='Atlas pricing',
        snippet=content, retrieved_at='2026-11-09T00:00:00+00:00', category=category, official=True)


class PhaseTwoTests(unittest.TestCase):
    def test_citations_and_missing_pricing(self):
        profile = CompetitorProfile(competitor_name='Atlas', pricing=[EvidenceClaim(
            value='$99', evidence_urls=['https://invented.example/'], quote='$99', status='verified')])
        checked = validate_profile(profile, 'Atlas', [source()])
        self.assertEqual(checked.pricing[0].value, 'Not verified')
        self.assertFalse(checked.evidence_urls)
        self.assertTrue(checked.missing_information)

    def test_supported_price_is_kept(self):
        profile = CompetitorProfile(competitor_name='Atlas', pricing=[EvidenceClaim(
            value='$10', quote='The Pro plan costs $10 per month.',
            evidence_urls=[source().url], status='verified')])
        checked = validate_profile(profile, 'Atlas', [source()])
        self.assertEqual(checked.pricing[0].value, '$10')
        self.assertEqual(checked.evidence_urls, [source().url])

    def test_unofficial_price_is_not_verified(self):
        evidence = source().model_copy(update={'official': False})
        profile = CompetitorProfile(competitor_name='Atlas', pricing=[EvidenceClaim(
            value='$10', quote='The Pro plan costs $10 per month.', evidence_urls=[evidence.url], status='verified')])
        self.assertEqual(validate_profile(profile, 'Atlas', [evidence]).pricing[0].value, 'Not verified')

    def test_partial_price_match_is_not_a_verified_price(self):
        evidence = source(content='The Pro plan costs $100 per month.')
        profile = CompetitorProfile(competitor_name='Atlas', pricing=[EvidenceClaim(
            value='$10', quote=evidence.snippet, evidence_urls=[evidence.url], status='verified')])
        self.assertEqual(validate_profile(profile, 'Atlas', [evidence]).pricing[0].value, 'Not verified')

    def test_transient_retries_respect_total_budget(self):
        client = Mock()
        client.search.side_effect = TimeoutError('secret')
        result = research_competitor(competitor(), client)
        self.assertEqual(client.search.call_count, 5)
        self.assertEqual(result['search_attempts'], 5)
        self.assertTrue(result['errors'])

    def test_full_route_and_extraction_partial_failure(self):
        from src.research_agent import FollowupPlan
        from langchain_core.messages import HumanMessage
        client, model, followup, discover = Mock(), Mock(), Mock(), Mock()
        client.search.side_effect = lambda query, **kw: {'results': [{
            'url': 'https://beacon.example/pricing', 'title': 'Beacon',
            'content': 'Pro is $10 per month.'}]} if 'Beacon' in query else {'results': []}
        client.extract.return_value = {'results': [], 'failed_results': []}
        followup.invoke.return_value = FollowupPlan()
        model.invoke.return_value = CompetitorProfile(competitor_name='Beacon', pricing=[EvidenceClaim(
            value='$10', quote='Pro is $10 per month.', status='verified',
            evidence_urls=['https://beacon.example/pricing'])])
        discover.return_value = {'competitors': [competitor(), competitor('Beacon')], 'errors': []}
        graph = build_research_graph(search_client=client, followup_model=followup,
                                    extraction_model=model, discovery_runner=discover)
        state = graph.invoke({'company': 'Notion', 'industry': 'Productivity software'})
        discover.assert_called_once_with('Notion', 'Productivity software')
        self.assertEqual(state['profiles']['Atlas'].pricing[0].value, 'Not verified')
        self.assertEqual(state['profiles']['Beacon'].pricing[0].value, '$10')
        self.assertIn('research', state)

    def test_extraction_failure_does_not_block_next_competitor(self):
        from src.research_agent import FollowupPlan
        client, model, followup = Mock(), Mock(), Mock()
        client.search.return_value = {'results': [{'url': source().url, 'title': 'Atlas', 'content': source().snippet}]}
        client.extract.return_value = {'results': []}
        followup.invoke.return_value = FollowupPlan()
        model.invoke.side_effect = [RuntimeError('secret-key'), CompetitorProfile(competitor_name='Beacon')]
        state = build_research_graph(search_client=client, followup_model=followup, extraction_model=model).invoke(
            {'competitors': [competitor(), competitor('Beacon')]})
        self.assertEqual(model.invoke.call_count, 2)
        self.assertTrue(state['extraction_errors']['Atlas'])
        self.assertFalse(state['extraction_errors']['Beacon'])

    def test_unsupported_quote_and_inferred_capability_rejected(self):
        for claim in [EvidenceClaim(value='Unlimited AI', quote='Invented quote', evidence_urls=[source().url], status='verified'),
                      EvidenceClaim(value='Unlimited AI', evidence_urls=[source().url], status='inferred')]:
            profile = CompetitorProfile(competitor_name='Atlas', core_features=[claim])
            self.assertEqual(validate_profile(profile, 'Atlas', [source()]).core_features[0].value, 'Not verified')

    def test_research_limits_and_metadata(self):
        client = Mock()
        client.search.return_value = {'results': [{'url': source().url, 'title': 'Pricing', 'content': source().snippet}]}
        client.extract.return_value = {'results': [{'url': source().url, 'raw_content': source().snippet}]}
        followup = Mock()
        from src.research_agent import FollowupPlan
        followup.invoke.return_value = FollowupPlan(queries=['Atlas enterprise pricing'])
        result = research_competitor(competitor(), client, followup)
        self.assertLessEqual(client.search.call_count, 5)
        self.assertEqual(client.extract.call_count, 1)
        self.assertTrue(result['sources'])
        self.assertTrue(all(s.retrieved_at and s.category for s in result['sources']))

    def test_llm_can_choose_followup_query(self):
        from src.research_agent import FollowupPlan
        client, followup = Mock(), Mock()
        client.search.return_value = {'results': []}
        followup.invoke.return_value = FollowupPlan(queries=['Atlas enterprise pricing details'], category='pricing')
        result = research_competitor(competitor(), client, followup)
        self.assertEqual(client.search.call_args.args[0], 'Atlas enterprise pricing details')
        self.assertEqual(result['search_attempts'], 5)

    def test_extract_failure_retains_search_evidence_and_news_date(self):
        client = Mock()
        client.search.return_value = {'results': [{'url': source().url, 'title': 'Launch',
            'content': 'Atlas launched a product.', 'published_date': '2026-11-01'}]}
        client.extract.side_effect = RuntimeError('secret')
        result = research_competitor(competitor(), client)
        news = next(s for s in result['sources'] if s.category == 'news')
        self.assertEqual(news.publication_date, '2026-11-01')
        self.assertEqual(news.snippet, 'Atlas launched a product.')
        self.assertTrue(result['errors'])
        self.assertNotIn('secret', str(result['errors']))

    def test_graph_continues_after_competitor_failure(self):
        client = Mock()
        client.search.side_effect = lambda query, **kw: (_ for _ in ()).throw(RuntimeError('secret')) if 'Atlas' in query else {'results': []}
        graph = build_research_graph(search_client=client, followup_model=Mock(), extraction_model=Mock())
        state = graph.invoke({'company': 'Notion', 'industry': 'Productivity software',
                              'competitors': [competitor(), competitor('Beacon')]})
        self.assertEqual(set(state['research']), {'Atlas', 'Beacon'})
        self.assertEqual(set(state['profiles']), {'Atlas', 'Beacon'})
        self.assertTrue(state['errors'])
        self.assertNotIn('secret', str(state['errors']))

    def test_news_date_cannot_be_invented(self):
        from src.extraction_agent import NewsItem
        evidence = source(category='news', content='Atlas launched a new product.')
        profile = CompetitorProfile(competitor_name='Atlas', recent_news=[NewsItem(
            value='Atlas launched a new product.', quote='Atlas launched a new product.',
            evidence_urls=[evidence.url], status='verified', publication_date='2026-10-01')])
        checked = validate_profile(profile, 'Atlas', [evidence])
        self.assertEqual(checked.recent_news[0].publication_date, 'Not verified')
