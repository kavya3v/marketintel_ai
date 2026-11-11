import unittest
from src.extraction_agent import CompetitorProfile, EvidenceClaim
from src.research_agent import ResearchSource
from src.verification_agent import verify_profiles


def evidence(text='Pro plan costs USD 10.99 per user per month.', url='https://vendor.example/pricing', official=True):
    return ResearchSource(url=url, title='Pricing', snippet=text, category='pricing',
                          retrieved_at='2026-11-09T00:00:00+00:00', official=official)


def checked(value, quote=None, sources=None, status='verified', urls=None, field='pricing'):
    sources = sources or [evidence()]
    claim = EvidenceClaim(value=value, quote=quote or sources[0].snippet,
                          evidence_urls=urls or [sources[0].url], status=status)
    profile = CompetitorProfile(competitor_name='Vendor', **{field: [claim]})
    return verify_profiles({'profiles': {'Vendor': profile}, 'research': {'Vendor': {'sources': sources}}})


class VerificationTests(unittest.TestCase):
    def test_decimal_currency_period_and_plan_preserved(self):
        result = checked('USD 10.99')
        fact = result['verification']['Vendor']['pricing'][0]
        self.assertEqual(fact['status'], 'verified')
        self.assertIn('Pro plan', fact['context'])
        self.assertIn('per user per month', fact['context'])
        for bad in ['USD 10', 'EUR 10.99', 'USD 10.99 per year', 'Enterprise USD 10.99']:
            self.assertEqual(checked(bad)['verification']['Vendor']['pricing'][0]['status'], 'unsupported')

    def test_decimal_dollar_prefix_rejected(self):
        self.assertEqual(checked('$10', sources=[evidence('Pro costs $10.99 per month.')])['verification']['Vendor']['pricing'][0]['status'], 'unsupported')

    def test_negated_capability_is_not_positive_evidence(self):
        result = checked('unlimited storage', sources=[evidence('The product does not include unlimited storage.')], field='core_features')
        self.assertEqual(result['verification']['Vendor']['core_features'][0]['status'], 'unsupported')

    def test_negated_price_is_not_verified(self):
        result = checked('USD 10.99', sources=[evidence('Pro plan is not USD 10.99 per month.')])
        self.assertEqual(result['verification']['Vendor']['pricing'][0]['status'], 'unsupported')

    def test_per_user_and_per_team_prices_are_not_conflicting(self):
        result = checked('USD 10.99', sources=[evidence(), evidence(
            'Pro plan costs USD 100 per team per month.', 'https://vendor.example/team')])
        self.assertEqual(result['verification']['Vendor']['pricing'][0]['status'], 'verified')

    def test_different_plans_and_periods_are_not_conflicts(self):
        result = checked('USD 10.99', sources=[evidence(),
            evidence('Enterprise plan costs USD 20.99 per user per month.', 'https://vendor.example/enterprise'),
            evidence('Pro plan costs USD 99.99 per user per year.', 'https://vendor.example/annual')])
        self.assertEqual(result['verification']['Vendor']['pricing'][0]['status'], 'verified')

    def test_conflicting_official_sources(self):
        result = checked('USD 10.99', sources=[evidence(), evidence('Pro plan costs USD 12.99 per user per month.', 'https://vendor.example/other')])
        self.assertEqual(result['verification']['Vendor']['pricing'][0]['status'], 'conflicting')

    def test_unsupported_url_and_third_party(self):
        result = checked('USD 10.99', urls=['https://invented.example/'])
        self.assertEqual(result['verification']['Vendor']['pricing'][0]['status'], 'unsupported')
        result = checked('USD 10.99', sources=[evidence(official=False)])
        self.assertNotEqual(result['verification']['Vendor']['pricing'][0]['status'], 'verified')

    def test_inference_never_becomes_fact(self):
        result = checked('A strategic opportunity', status='inferred', field='positioning')
        self.assertEqual(result['verification']['Vendor']['positioning'][0]['status'], 'inferred')
        self.assertFalse(any(f['status'] == 'verified' for fs in result['verification']['Vendor'].values() for f in fs))

    def test_inferred_price_cannot_enter_report_as_strategic_claim(self):
        result = checked('USD 1000', status='inferred')
        self.assertEqual(result['verification']['Vendor']['pricing'][0]['status'], 'unsupported')

    def test_missing_news_is_explicit_gap(self):
        result = checked('USD 10.99')
        self.assertEqual(result['verification']['Vendor']['recent_news'][0]['status'], 'missing')
        self.assertIn('recent_news', result['repair_targets']['Vendor'])

    def test_news_without_publication_date_still_records_date_gap(self):
        from src.extraction_agent import NewsItem
        news = evidence('Atlas launched a new product.', 'https://news.example/story', official=False).model_copy(update={'category': 'news'})
        profile = CompetitorProfile(competitor_name='Vendor', recent_news=[NewsItem(value=news.snippet,
            quote=news.snippet, status='verified', evidence_urls=[news.url])])
        result = verify_profiles({'profiles': {'Vendor': profile}, 'research': {'Vendor': {'sources': [news]}}})
        self.assertTrue(any('publication date' in gap.lower() for gap in result['gaps']))
