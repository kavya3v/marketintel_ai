import unittest
from src.report_agent import generate_briefing
from src.discovery_agent import DiscoveryError


class BriefingTests(unittest.TestCase):
    def test_only_verified_facts_enter_factual_sections(self):
        fact = {'value': 'USD 10.99', 'context': 'Pro costs USD 10.99 per month.',
                'status': 'verified', 'official': True, 'evidence_urls': ['https://vendor.example/pricing']}
        rejected = dict(fact, value='INVENTED PRICE', context='INVENTED PRICE', status='unsupported')
        conflict = dict(fact, value='CONFLICTING PRICE', context='CONFLICTING PRICE', status='conflicting')
        state = {'approval_status': 'approved', 'company': 'Notion', 'industry': 'Productivity software',
                 'research_timestamp': '2026-11-09', 'verification': {'Vendor': {'pricing': [fact, rejected, conflict]}},
                 'gaps': ['Recent news not verified'], 'errors': []}
        report = generate_briefing(state)['final_report']
        self.assertIn('USD 10.99', report)
        self.assertNotIn('INVENTED PRICE', report)
        self.assertNotIn('CONFLICTING PRICE', report)
        self.assertIn('Recent news not verified', report)
        self.assertIn('https://vendor.example/pricing', report)

    def test_report_requires_approval(self):
        for status in ('pending', 'rejected', 'revision_requested'):
            with self.assertRaises(DiscoveryError):
                generate_briefing({'approval_status': status})

    def test_three_available_profiles_are_all_in_briefing(self):
        report = generate_briefing({'approval_status': 'approved', 'company': 'Notion',
            'verification': {'Atlas': {}, 'Beacon': {}, 'Cinder': {}}, 'gaps': [], 'errors': []})['final_report']
        for name in ('Atlas', 'Beacon', 'Cinder'):
            self.assertIn(f'## {name}', report)
