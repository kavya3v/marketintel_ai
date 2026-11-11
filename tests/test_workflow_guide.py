import re
import unittest
from unittest.mock import patch
from langgraph.checkpoint.memory import InMemorySaver
from streamlit.testing.v1 import AppTest
from src.full_workflow import build_full_graph
from src.workflow_guide import workflow_diagram, active_step


class WorkflowGuideTests(unittest.TestCase):
    def test_diagram_matches_implemented_edges(self):
        diagram = workflow_diagram()
        actual = {(e.source, e.target) for e in build_full_graph(InMemorySaver()).get_graph().edges}
        edges = set()
        for line in diagram.splitlines():
            match = re.match(r'\s*(\w+)(?:\[[^]]*\]|\([^)]*\))?\s*-->(?:\|[^|]*\|)?\s*(\w+)', line)
            if match:
                a,b = match.groups()
                rename = {'start': '__start__', 'finish': '__end__'}
                edges.add((rename.get(a,a),rename.get(b,b)))
        self.assertEqual(edges, actual)

    def test_saved_review_and_completed_report_highlighting(self):
        self.assertEqual(active_step({'_pending_nodes': ['human_review'], '_interrupted': True}), 'human_review')
        self.assertEqual(active_step({'approval_status': 'approved', 'final_report': 'Report'}), 'briefing')
        self.assertIn('class human_review current', workflow_diagram('human_review'))
        self.assertNotIn('class untrusted current', workflow_diagram('untrusted'))

    def test_guide_renders_without_research_calls(self):
        with patch('src.discovery_agent.discover_competitors') as discover:
            app = AppTest.from_file('../app.py').run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Workflow map' in e.label for e in app.expander))
            text = '\n'.join(e.value for e in app.markdown)
            for agent in ('Discovery agent','Web Research agent','Intelligence Extraction agent','Evidence Verification agent','Briefing agent'):
                self.assertIn(agent, text)
            discover.assert_not_called()
