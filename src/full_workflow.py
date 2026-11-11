"""Checkpointed full workflow; the existing discovery and Phase 2 graphs remain usable."""
from datetime import datetime, timezone
from uuid import uuid4
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from src.discovery_agent import ResearchState, CompetitorCandidate, discover_competitors, _configured_search_client
from src.graph import build_research_graph
from src.research_agent import research_competitor
from src.verification_agent import verify_profiles
from src.report_agent import generate_briefing


def plain(value):
    if hasattr(value, 'model_dump'):
        return plain(value.model_dump(mode='json'))
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def hydrated(state):
    return dict(state, competitors=[CompetitorCandidate.model_validate(c) for c in state.get('competitors', [])])


def build_full_graph(checkpointer, *, search_client=None, followup_model=None, extraction_model=None,
                     discovery_runner=None, progress=None):
    phase = build_research_graph(search_client=search_client, followup_model=followup_model,
        extraction_model=extraction_model, raw_output=True, progress=progress)

    def notify(message):
        if progress:
            progress(message)

    def discovery(state):
        notify('Discovering competitors')
        try:
            result = (discovery_runner or discover_competitors)(state['company'], state['industry'])
            return plain(result)
        except Exception:
            return {'workflow_error': 'Discovery failed. Check sanitized terminal diagnostics and provider configuration.',
                    'approval_status': 'failed', 'competitors': []}

    def research(state):
        notify('Collecting research evidence')
        try:
            return plain(phase.builder.nodes['web_research'].runnable.invoke(hydrated(state)))
        except Exception:
            return {'research': {c['name']: {'sources': [], 'errors': ['Research provider unavailable.']}
                                 for c in plain(state['competitors'])},
                    'errors': list(state.get('errors', [])) + ['Research provider initialization failed; review missing evidence.']}

    def extraction(state):
        notify('Extracting structured intelligence')
        current = hydrated(state)
        if state.get('selected_names'):
            current['competitors'] = [c for c in current['competitors'] if c.name in state['selected_names']]
        try:
            update = plain(phase.builder.nodes['intelligence_extraction'].runnable.invoke(current))
            profiles = dict(state.get('profiles', {}))
            for name, new in update['profiles'].items():
                old = profiles.get(name, {})
                for field, claims in state.get('verification', {}).get(name, {}).items():
                    keep = {c['value'] for c in claims if c['status'] == 'verified'}
                    retained = [c for c in old.get(field, []) if c['value'] in keep]
                    existing = {c['value'] for c in retained}
                    limit = 10 if field == 'core_features' else 5 if field == 'recent_news' else 8
                    new[field] = (retained + [c for c in new.get(field, []) if c['value'] not in existing])[:limit]
                profiles[name] = new
            update['profiles'] = profiles
            update['errors'] = list(dict.fromkeys(update.get('errors', [])))
            return update
        except Exception:
            return {'profiles': state.get('profiles', {}),
                    'errors': list(state.get('errors', [])) + ['Extraction failed; available evidence retained.']}

    def verification(state):
        notify('Verifying claims against retrieved evidence')
        profiles = dict(state.get('profiles', {}))
        for candidate in plain(state.get('competitors', [])):
            profiles.setdefault(candidate['name'], {'competitor_name': candidate['name']})
        update = verify_profiles(dict(state, profiles=profiles))
        update['retry_count'] = sum(record.get('retry_count', 0) for record in state.get('research', {}).values())
        return update

    def repair(state):
        nonlocal search_client
        notify('Repairing targeted evidence gaps')
        records = dict(state.get('research', {}))
        count = state.get('repair_count', 0) + (state.get('approval_status') != 'revision_requested')
        changed = []
        for competitor in hydrated(state)['competitors']:
            targets = state.get('repair_targets', {}).get(competitor.name, [])
            if not targets:
                continue
            categories = list(dict.fromkeys({'core_features': 'features', 'target_customers': 'positioning',
                                           'recent_news': 'news'}.get(f, f) for f in targets))
            try:
                if search_client is None:
                    search_client = _configured_search_client()
                records[competitor.name] = research_competitor(competitor, search_client, progress=progress,
                    categories=categories, previous=records.get(competitor.name),
                    repair_round=count + state.get('revision_count', 0) * 2,
                    feedback=state.get('revision_feedback', ''))
            except Exception:
                record = dict(records.get(competitor.name, {'sources': []}))
                record['errors'] = ['Targeted research failed; retained previous evidence.']
                records[competitor.name] = record
            changed.append(competitor.name)
        return plain({'research': records, 'selected_names': changed, 'repair_count': count,
                      'retry_count': sum(record.get('retry_count', 0) for record in records.values())})

    def route_verification(state):
        if state.get('repair_targets') and state.get('repair_count', 0) < 2:
            return 'targeted_research'
        return 'prepare_review'

    def prepare_review(state):
        notify('Awaiting human review')
        return {'approval_status': 'pending', 'review_token': str(uuid4())}

    def review(state):
        # No calls or side effects before interrupt: this node restarts on resume.
        decision = interrupt({'review_token': state['review_token'], 'company': state['company'],
            'verification': state.get('verification', {}), 'gaps': state.get('gaps', []),
            'errors': state.get('errors', []), 'repair_count': state.get('repair_count', 0)})
        action = decision.get('action', 'reject') if isinstance(decision, dict) else 'reject'
        valid = isinstance(decision, dict) and decision.get('review_token') == state['review_token']
        if not valid or action not in ('approve', 'revise', 'reject'):
            return {'approval_status': 'rejected', 'final_report': ''}
        history = list(state.get('approval_history', [])) + [{
            'action': action, 'review_token': state['review_token'],
            'timestamp': datetime.now(timezone.utc).isoformat()}]
        if action == 'approve':
            return {'approval_status': 'approved', 'approval_history': history}
        if action == 'reject':
            return {'approval_status': 'rejected', 'final_report': '', 'approval_history': history}
        if state.get('revision_count', 0) >= 2:
            return {'approval_status': 'revision_limit_reached', 'final_report': '', 'approval_history': history}
        targets = state.get('repair_targets') or {name: ['pricing', 'core_features', 'positioning', 'recent_news']
                                                 for name in state.get('profiles', {})}
        return {'approval_status': 'revision_requested', 'revision_count': state.get('revision_count', 0) + 1,
                'revision_feedback': str(decision.get('feedback', ''))[:500],
                'repair_targets': targets, 'approval_history': history, 'final_report': ''}

    def report(state):
        notify('Formatting approved briefing')
        return generate_briefing(state)

    graph = StateGraph(ResearchState)
    for name, node in [('discovery', discovery), ('web_research', research), ('extraction', extraction),
                       ('verification', verification), ('targeted_research', repair),
                       ('prepare_review', prepare_review), ('human_review', review), ('briefing', report)]:
        graph.add_node(name, node)
    graph.add_conditional_edges(START, lambda s: 'web_research' if s.get('competitors') else 'discovery',
                               ['web_research', 'discovery'])
    graph.add_conditional_edges('discovery', lambda s: 'web_research' if s.get('competitors') else END,
                               ['web_research', END])
    graph.add_edge('web_research', 'extraction')
    graph.add_edge('extraction', 'verification')
    graph.add_conditional_edges('verification', route_verification, ['targeted_research', 'prepare_review'])
    graph.add_edge('targeted_research', 'extraction')
    graph.add_edge('prepare_review', 'human_review')
    graph.add_conditional_edges('human_review', lambda s: {'approved': 'briefing',
        'revision_requested': 'targeted_research'}.get(s['approval_status'], END),
        ['briefing', 'targeted_research', END])
    graph.add_edge('briefing', END)
    return graph.compile(checkpointer=checkpointer)
