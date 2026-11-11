import unittest
from copy import deepcopy
from src.report_agent import generate_briefing


def claim(value, *, context=None, date='Not verified', status='verified'):
    return {'value': value, 'context': context or value, 'quote': context or value,
            'publication_date': date, 'status': status, 'official': True,
            'evidence_urls': ['https://vendor.example/evidence']}


def state(fields=None):
    return {'approval_status': 'approved', 'company': 'Notion', 'industry': 'Productivity software',
            'research_timestamp': '2026-11-10T03:57:15+00:00', 'verification': {'Vendor': fields or {}},
            'gaps': [], 'errors': []}


class PresentationTests(unittest.TestCase):
    def render(self, fields):
        return generate_briefing(state(fields))['final_report']

    def test_pricing_precision_currency_plan_and_period(self):
        text = self.render({'pricing': [claim('USD 10.99', context='Pro plan costs USD 10.99 per user per month, billed annually.')]})
        self.assertIn('10.99', text)
        self.assertIn('USD', text)
        self.assertIn('Pro', text)
        self.assertIn('per user per month', text)
        self.assertIn('billed annually', text)
        self.assertIn('Subscription', text)

    def test_custom_free_unknown_are_separate(self):
        text = self.render({'pricing': [claim('Custom pricing', context='Enterprise\nCustom pricing'),
                                       claim('Free plan'), claim('All prices exclude VAT.')]})
        self.assertIn('Custom enterprise', text)
        self.assertIn('Free', text)
        self.assertNotIn('$0', text)
        self.assertIn('Not verified', text)

    def test_missing_price_cannot_be_taken_from_unsupported_claim(self):
        text = self.render({'pricing': [claim('USD 999.99', status='unsupported')]})
        self.assertNotIn('999.99', text)
        self.assertIn('Not verified', text)

    def test_news_requires_dated_90_day_window(self):
        fields = {'recent_news': [claim('Undated event'), claim('Old funding', date='2020-04-15'),
            claim('Valid launch', date='2026-11-01'), claim('Boundary launch', date='2026-08-12'),
            claim('Too old', date='2026-08-11'), claim('Future event', date='2026-11-11')]}
        text = self.render(fields)
        self.assertIn('Valid launch', text)
        self.assertIn('2026-11-01', text)
        self.assertIn('Boundary launch', text)
        for excluded in ('Undated event', 'Old funding', 'Too old', 'Future event'):
            self.assertNotIn(excluded, text)

    def test_no_qualifying_news_and_research_time_missing(self):
        self.assertIn('No verified recent news found.', self.render({'recent_news': [claim('Undated')]}))
        data = state({'recent_news': [claim('A launch', date='2026-11-01')]})
        data.pop('research_timestamp')
        self.assertNotIn('A launch', generate_briefing(data)['final_report'])

    def test_recently_dated_directory_does_not_make_old_funding_recent(self):
        text = self.render({'recent_news': [claim('Series A 2020-04-15 11.00M USD', date='2026-11-01')]})
        self.assertNotIn('11.00M', text)
        self.assertIn('No verified recent news found.', text)

    def test_news_with_later_time_on_research_day_is_excluded(self):
        text = self.render({'recent_news': [claim('Later launch', date='2026-11-10 20:00:00+00:00')]})
        self.assertNotIn('Later launch', text)

    def test_multiple_rates_are_not_associated_with_arbitrary_plan(self):
        text = self.render({'pricing': [claim('USD 10.99', context='Pro plan USD 10.99 per month; Business plan USD 20.99 per month.')]})
        pricing = text.split('## Pricing comparison')[1].split('## Recent news')[0]
        self.assertNotIn('| Pro | 10.99', pricing)
        self.assertIn('Not verified', pricing)

    def test_one_paid_amount_is_not_assigned_to_free_plan(self):
        text = self.render({'pricing': [claim('USD 20', context='Free plan includes 5 projects and Pro plan costs USD 20 per month.')]})
        pricing = text.split('## Pricing comparison')[1].split('## Recent news')[0]
        self.assertNotIn('| Free | 20', pricing)
        self.assertNotIn('| Free |', pricing)
        self.assertIn('Not verified', pricing)

    def test_restrictive_context_is_preserved_when_value_is_short(self):
        text = self.render({'core_features': [claim('unlimited storage', context='Enterprise plan includes unlimited storage for admins only.')]})
        self.assertIn('Enterprise plan includes unlimited storage for admins only.', text)
        row = next(line for line in text.splitlines() if line.startswith('| Vendor') and 'storage' in line)
        self.assertIn('admins only', row)

    def test_dedup_markdown_and_feature_limit(self):
        text = self.render({'core_features': [claim('AI | search [docs]'), claim('AI | search [docs]'),
                *[claim(f'Capability {i}') for i in range(8)]]})
        comparison = text.split('## Competitor comparison table')[1].split('## Pricing comparison')[0]
        row = next(line for line in comparison.splitlines() if line.startswith('| Vendor'))
        self.assertEqual(row.count('|'), 7)
        self.assertEqual(row.count('AI'), 1)
        self.assertLessEqual(row.count('Capability'), 4)
        self.assertNotIn('[docs]', row)  # Escape source-provided Markdown.

    def test_summary_analysis_and_quality_preserve_statuses(self):
        data = state({'core_features': [claim('AI search'), claim('API integrations'), claim('Role-based permissions')],
            'positioning': [claim('Knowledge platform')], 'target_customers': [claim('Small teams')],
            'pricing': [claim('HIDDEN PRICE', status='unsupported')]})
        original = deepcopy(data)
        result = generate_briefing(data)['final_report']
        for heading in ('Executive summary', 'Competitive landscape overview', 'Competitor comparison table',
                        'Pricing comparison', 'Recent news', 'Strategic implications and recommended actions',
                        'Detailed competitor profiles', 'Research quality and limitations', 'Source references'):
            self.assertIn('## '+heading, result)
        for label in ('Observation', 'Strategic implication', 'Recommended next step', 'hypothesis'):
            self.assertIn(label, result)
        self.assertNotIn('HIDDEN PRICE', result)
        self.assertEqual(data, original)
