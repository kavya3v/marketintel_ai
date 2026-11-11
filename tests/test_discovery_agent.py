import os
import unittest
from unittest.mock import patch
from src import discovery_agent as a

class Model:
    def __init__(self, result): self.result = result
    def invoke(self, messages): return self.result

class Search:
    def __init__(self, results=None, error=None):
        self.queries, self.results, self.error = [], results, error
    def search(self, query, **kwargs):
        self.queries.append(query)
        if self.error: raise self.error
        return {'results': self.results if self.results is not None else [
            {'title': n, 'url': f'https://{n.lower()}.example/',
             'content': f'{n} offers project management as an alternative to Acme.'}
            for n in ['Atlas', 'Beacon']]}

def candidate(name='Atlas', **changes):
    data = dict(name=name, website=f'https://{name.lower()}.example/',
                rationale='Offers project management as an alternative to Acme.',
                source_urls=[f'https://{name.lower()}.example/'])
    data.update(changes)
    return a.CompetitorCandidate(**data)

class DiscoveryTests(unittest.TestCase):
    def run_graph(self, candidates=None, search=None, company='Acme'):
        return a.build_discovery_graph(search_client=search or Search(),
            query_model=Model(a.SearchPlan(queries=['LLM selected alternatives query'])),
            discovery_model=Model(a.CompetitorDiscoveryResult(competitors=
                candidates if candidates is not None else [candidate(), candidate('Beacon')]))
        ).invoke({'company': company, 'industry': 'project management'})

    def test_llm_query_and_partial_results(self):
        search = Search()
        state = self.run_graph(search=search)
        self.assertEqual(search.queries, ['LLM selected alternatives query'])
        self.assertEqual([c.name for c in state['competitors']], ['Atlas', 'Beacon'])
        self.assertEqual(state['competitors'][0].website, 'https://atlas.example/')

    def test_filters_unreturned_citations(self):
        state = self.run_graph([candidate(source_urls=['https://invented.example/', 'https://atlas.example/'])])
        self.assertEqual(state['competitors'][0].source_urls, ['https://atlas.example/'])

    def test_rejects_unsupported_website_and_name(self):
        for item in [candidate(website='https://invented.example/'), candidate('Imaginary')]:
            with self.subTest(item=item), self.assertRaisesRegex(a.DiscoveryError, 'verify'):
                self.run_graph([item])

    def test_excludes_target_and_duplicates(self):
        state = self.run_graph([candidate(), candidate(), candidate('Acme')])
        self.assertEqual(len(state['competitors']), 1)

    def test_empty_search_and_selection(self):
        with self.assertRaisesRegex(a.DiscoveryError, 'no usable'):
            self.run_graph(search=Search(results=[]))
        with self.assertRaisesRegex(a.DiscoveryError, 'verify'):
            self.run_graph([])

    def test_safe_search_error(self):
        with self.assertRaisesRegex(a.DiscoveryError, 'Tavily search failed') as caught:
            self.run_graph(search=Search(error=RuntimeError('secret-key')))
        self.assertNotIn('secret-key', str(caught.exception))

    def test_blank_input(self):
        with self.assertRaisesRegex(a.DiscoveryError, 'company and industry'):
            self.run_graph(company=' ')

    def test_invalid_model_output_is_safe(self):
        graph = a.build_discovery_graph(search_client=Search(),
            query_model=Model({'queries': ['not structured']}),
            discovery_model=Model(None))
        with self.assertRaisesRegex(a.DiscoveryError, 'Fireworks AI query planning failed'):
            graph.invoke({'company': 'Acme', 'industry': 'project management'})

    def test_selection_failure_is_safe(self):
        graph = a.build_discovery_graph(search_client=Search(),
            query_model=Model(a.SearchPlan(queries=['alternatives'])),
            discovery_model=Model(None))
        with self.assertRaisesRegex(a.DiscoveryError, 'Fireworks AI competitor selection failed'):
            graph.invoke({'company': 'Acme', 'industry': 'project management'})

    def test_unsafe_source_urls_are_not_evidence(self):
        with self.assertRaisesRegex(a.DiscoveryError, 'no usable'):
            self.run_graph(search=Search(results=[
                {'title': 'Atlas', 'url': 'javascript:alert(1)', 'content': 'Atlas'}]))

    def test_missing_keys(self):
        with patch.dict(os.environ, {'TAVILY_API_KEY': '', 'FIREWORKS_API_KEY': ''}), patch.object(a, 'load_dotenv'):
            with self.assertRaisesRegex(a.DiscoveryError, 'TAVILY_API_KEY'): a.build_discovery_graph()
        with patch.dict(os.environ, {'FIREWORKS_API_KEY': ''}), patch.object(a, 'load_dotenv'):
            with self.assertRaisesRegex(a.DiscoveryError, 'FIREWORKS_API_KEY'): a.build_discovery_graph(search_client=Search())
