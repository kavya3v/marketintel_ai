"""Composable discovery -> web research -> intelligence extraction workflow."""

from langgraph.graph import START, END, StateGraph
from src.discovery_agent import (
    ResearchState, build_discovery_graph, discover_competitors, DiscoveryError,
    _configured_search_client, _configured_model,
)
from src.research_agent import FollowupPlan, research_competitor, ResearchSource
from src.extraction_agent import CompetitorProfile, extract_profile, validate_profile

def build_research_graph(*, search_client=None, followup_model=None, extraction_model=None,
                         discovery_runner=None, progress=None, raw_output=False):
    """Reuse existing competitors, or discover first when invoked without them.

    Resources are initialized lazily inside nodes so imports and initial UI loads
    never contact providers. A failure for one competitor does not halt the graph.
    """
    def notify(message):
        if progress:
            progress(message)

    def discover(state):
        notify('Discovering competitors')
        return (discovery_runner or discover_competitors)(state.get('company', ''), state.get('industry', ''))

    def research(state):
        nonlocal search_client, followup_model
        search_client = search_client if search_client is not None else _configured_search_client()
        followup_model = followup_model if followup_model is not None else _configured_model(FollowupPlan)
        evidence, errors = {}, {}
        for competitor in state.get('competitors', [])[:3]:
            notify(f'Researching {competitor.name}')
            try:
                record = research_competitor(competitor, search_client, followup_model, progress)
            except Exception:
                record = {'sources': [], 'errors': ['Research failed; check provider configuration and availability.']}
            evidence[competitor.name] = record
            errors[competitor.name] = record['errors']
        return {'research': evidence, 'research_errors': errors}

    def extraction(state):
        nonlocal extraction_model
        extraction_model = extraction_model if extraction_model is not None else _configured_model(CompetitorProfile)
        profiles, errors = {}, {}
        for competitor in state.get('competitors', [])[:3]:
            notify(f'Extracting profile for {competitor.name}')
            sources = [ResearchSource.model_validate(s) for s in state['research'][competitor.name]['sources']]
            try:
                profiles[competitor.name] = extract_profile(competitor.name, sources, extraction_model, raw_output=raw_output)
                errors[competitor.name] = []
            except Exception:
                profiles[competitor.name] = validate_profile(
                    CompetitorProfile(competitor_name=competitor.name), competitor.name, [])
                errors[competitor.name] = ['Intelligence extraction failed; evidence retained for review.']
        flattened = list(state.get('errors', []))
        for mapping in (state.get('research_errors', {}), errors):
            flattened.extend(f'{name}: {message}' for name, messages in mapping.items() for message in messages)
        gaps = [f'{name}: {gap}' for name, profile in profiles.items() for gap in profile.missing_information]
        return {'profiles': profiles, 'extraction_errors': errors, 'errors': flattened, 'gaps': gaps,
                'approval_status': 'not_requested'}

    builder = StateGraph(ResearchState)
    builder.add_node('discovery', discover)
    builder.add_node('web_research', research)
    builder.add_node('intelligence_extraction', extraction)
    builder.add_conditional_edges(START, lambda state: 'web_research' if state.get('competitors') else 'discovery',
                                  {'web_research': 'web_research', 'discovery': 'discovery'})
    builder.add_edge('discovery', 'web_research')
    builder.add_edge('web_research', 'intelligence_extraction')
    builder.add_edge('intelligence_extraction', END)
    return builder.compile()


def generate_research_profiles(state: ResearchState, *, progress=None) -> ResearchState:
    if not state.get('competitors'):
        raise DiscoveryError('Discover competitors before generating research profiles.')
    return build_research_graph(progress=progress).invoke(state)


__all__ = ['ResearchState', 'build_discovery_graph', 'build_research_graph', 'generate_research_profiles']
