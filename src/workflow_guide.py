"""Read-only workflow diagram and plain-language agent guide."""
import streamlit as st

STEPS = {
    'discovery': 'Discovery agent',
    'web_research': 'Web Research agent',
    'extraction': 'Intelligence Extraction agent',
    'verification': 'Evidence Verification agent',
    'targeted_research': 'Targeted research repair',
    'prepare_review': 'Prepare human review',
    'human_review': 'Human review',
    'briefing': 'Briefing agent',
}


def active_step(state=None):
    state = state or {}
    pending = state.get('_pending_nodes', [])
    if pending:
        return pending[0] if pending[0] in STEPS else None
    if state.get('approval_status') == 'approved' and state.get('final_report'):
        return 'briefing'
    if state.get('approval_status') in ('rejected', 'revision_limit_reached'):
        return 'human_review'
    if state.get('workflow_error'):
        return 'discovery'
    return None


def workflow_diagram(current=None):
    chart = '''flowchart TD
    start([Start]) -->|New competitor search| discovery
    start -->|Reuse selected competitors| web_research
    discovery["1. Discover competitors"] -->|Competitors found| web_research
    discovery -->|Discovery failed| finish([Finish])
    web_research["2. Research the web"] --> extraction
    extraction["3. Extract intelligence"] --> verification
    verification["4. Verify the evidence"] -->|Gaps and fewer than 2 repairs| targeted_research
    verification -->|Ready or repair limit reached| prepare_review
    targeted_research["Repair targeted evidence gaps"] --> extraction
    prepare_review["Prepare findings and warnings"] --> human_review
    human_review["5. Human review: workflow pauses"] -->|Approve| briefing
    human_review -->|Request revision: up to 2| targeted_research
    human_review -->|Reject or revision limit reached| finish
    briefing["6. Generate approved briefing"] --> finish
'''
    if current in STEPS:
        chart += f'    classDef current fill:#dbeafe,stroke:#2563eb,stroke-width:3px,color:#172554\n    class {current} current\n'
    return chart


def render_workflow_guide(state=None):
    with st.expander('Workflow map and agent guide', expanded=True):
        current = active_step(state)
        if current:
            label = ('Paused at' if state.get('_interrupted') else 'Next saved step' if state.get('_pending_nodes')
                     else 'Completed step' if state.get('approval_status') == 'approved' else 'Saved workflow step')
            st.caption(f'{label}: {STEPS[current]}')
        else:
            st.caption('Follow the main path from discovery to an approved briefing. Arrows show recovery and review decisions.')
        st.mermaid_chart(workflow_diagram(current), width='stretch',
            alt='Competitor research workflow: discovery, web research, extraction, verification, bounded repair, human review and approved briefing.')
        st.markdown('''
- **Discovery agent:** Fireworks AI chooses search queries and Tavily finds up to three competitors, with website links and selection evidence.
- **Web Research agent:** Tavily searches pricing, features, positioning and news, then extracts relevant official pages. It retains sources and partial results when a competitor fails.
- **Intelligence Extraction agent:** Fireworks AI turns retrieved evidence into Pydantic-validated profiles with quotes, citations and missing information.
- **Evidence Verification agent:** Python checks that citations and quotes support claims, including exact prices, billing context and conflicting evidence. Strategic inferences remain separate from facts.
- **Targeted research repair:** Searches the unresolved evidence categories and rechecks the results. Automatic repair stops after two cycles; gaps remain visible for review.
- **Human review:** The workflow pauses for **Approve**, **Request Revision** or **Reject**. At most two human revision requests are allowed; rejection does not create an approved report.
- **Briefing agent:** Deterministically formats approved findings into a Markdown comparison with pricing, dated recent news, strategic hypotheses, sources and limitations.
''')
        st.caption('Saved runs keep evidence and decisions in SQLite. Loading this guide does not call providers or resume the workflow. Report regeneration reuses approved evidence without repeating the agent steps.')
