"""Evidence-only claim verification. No LLM can promote its own inference to fact."""
import re
from src.evidence import literal_match, normalized
from src.extraction_agent import CompetitorProfile
from src.research_agent import ResearchSource

FIELDS = ('pricing', 'core_features', 'target_customers', 'positioning', 'recent_news')
MONEY = re.compile(r'(?:USD|EUR|GBP|CAD|AUD|US\$|CA\$|AU\$|[$€£])\s*\d+(?:[.,]\d+)*', re.I)


def _context(quote, text):
    # Preserve the complete pricing line/sentence, including plan and billing terms.
    for line in re.split(r'\n|(?<=[.!?])\s+', text):
        if literal_match(quote, line):
            return line.strip()
    return quote.strip()


def _price_records(text):
    records = []
    for line in re.split(r'\n|(?<=[.!?])\s+', text):
        for match in MONEY.finditer(line):
            plan = re.search(r'\b([\w-]+)\s+(?:plan|tier)\b', line, re.I)
            if not plan:
                plan = re.search(r'^\s*([\w-]+)\s+(?:costs?|is)\b', line, re.I)
            period = re.search(r'(?:per\s+(?:user\s+per\s+)?|/)\s*(month|year|week|day)\b', line, re.I)
            currency = re.match(r'[^\d]+', match.group()).group().strip().upper()
            unit = re.search(r'(?:per\s+|/\s*)(user|seat|team|workspace|organization|member)\b', line, re.I)
            records.append({'money': normalized(match.group()),
                            'key': (plan.group(1).casefold() if plan else None,
                                    period.group(1).casefold() if period else None, currency,
                                    bool(re.search(r'bill(?:ed|ing)?\s+annual', line, re.I)),
                                    unit.group(1).casefold() if unit else None),
                            'context': line.strip()})
    return records


def _check(claim, field, sources):
    base = {'value': claim.value, 'quote': claim.quote, 'context': '', 'evidence_urls': [],
            'official': False, 'publication_date': 'Not verified'}
    if claim.status == 'not_verified' or normalized(claim.value) == 'not verified':
        return dict(base, status='missing', reason='No reliable evidence supplied.')
    known = {s.url for s in sources}
    if not claim.evidence_urls or any(u not in known for u in claim.evidence_urls):
        return dict(base, status='unsupported', reason='Citation does not exist in this competitor\'s retrieved evidence.')
    cited = [s for s in sources if s.url in claim.evidence_urls]
    if field == 'recent_news':
        cited = [s for s in cited if s.category == 'news']
    matched = [s for s in cited if literal_match(claim.quote, s.snippet)]
    if not matched:
        return dict(base, status='unsupported', reason='Supporting quote is absent from the cited source.')
    base.update(evidence_urls=list(dict.fromkeys(s.url for s in matched)), official=any(s.official for s in matched))
    if claim.status == 'inferred':
        if field not in ('target_customers', 'positioning'):
            return dict(base, status='unsupported', reason='Inferred prices, product capabilities, and news are not factual evidence.')
        return dict(base, status='inferred', context=claim.quote,
                    reason='Strategic interpretation, not a verified factual finding.')
    if not literal_match(claim.value, claim.quote):
        return dict(base, status='unsupported', reason='Claim differs from its evidence, including exact numeric values.')
    if field in ('pricing', 'core_features'):
        matched = [s for s in matched if s.official]
        if not matched:
            return dict(base, status='unsupported', reason='Official vendor evidence is required; only third-party evidence was retrieved.')
        base['evidence_urls'] = list(dict.fromkeys(s.url for s in matched))
    context = _context(claim.quote, matched[0].snippet)
    if re.search(r'\b(?:not|no|never|without|cannot)\b', normalized(context)) and not re.search(
            r'\b(?:not|no|never|without|cannot)\b', normalized(claim.value)):
        return dict(base, status='unsupported', reason='The source context is negated; a positive factual claim cannot be inferred from it.')
    if field == 'pricing':
        for attribute in ('plan_name', 'currency', 'billing_period'):
            value = getattr(claim, attribute, None)
            if value and not literal_match(value, context):
                return dict(base, status='unsupported', reason=f'Pricing {attribute} is not supported by the source context.')
        records = _price_records(context)
        for record in records:
            if not record['key'][0] or not record['key'][1]:
                continue  # Unknown plan/period cannot establish a like-for-like conflict.
            alternatives = [(s, r) for s in sources if s.official and s.category == 'pricing'
                            for r in _price_records(s.snippet)
                            if r['key'] == record['key'] and r['money'] != record['money']]
            if alternatives:
                return dict(base, status='conflicting', context=context,
                            evidence_urls=list(dict.fromkeys(base['evidence_urls'] + [s.url for s, _ in alternatives])),
                            reason='Official sources disagree on price for the same plan, currency, and billing period.')
    if field == 'recent_news':
        dates = {s.publication_date for s in matched if s.publication_date}
        if getattr(claim, 'publication_date', None) in dates:
            base['publication_date'] = claim.publication_date
    return dict(base, status='verified', context=context,
                reason='Exact factual excerpt supported by retrieved evidence; official vendor' if base['official']
                else 'Exact factual excerpt from third-party evidence; not independently confirmed.')


def verify_profiles(state):
    findings, gaps, targets = {}, [], {}
    for name, data in state.get('profiles', {}).items():
        profile = CompetitorProfile.model_validate(data)
        sources = [ResearchSource.model_validate(s) for s in state.get('research', {}).get(name, {}).get('sources', [])]
        fields, missing = {}, []
        for field in FIELDS:
            fields[field] = [_check(c, field, sources) for c in getattr(profile, field)] or [
                {'value': 'Not verified', 'status': 'missing', 'reason': 'No evidence available.',
                 'evidence_urls': [], 'context': '', 'official': False, 'publication_date': 'Not verified'}]
            if any(c['status'] in ('unsupported', 'conflicting', 'missing') for c in fields[field]):
                missing.append(field)
                gaps.extend(f"{name} / {field}: {c['status']} — {c['reason']}" for c in fields[field]
                            if c['status'] in ('unsupported', 'conflicting', 'missing'))
            if field == 'recent_news' and any(c['status'] == 'verified' and c['publication_date'] == 'Not verified'
                                               for c in fields[field]):
                gaps.append(f'{name} / recent_news: publication date missing; recency is not verified.')
                if field not in missing:
                    missing.append(field)
        findings[name] = fields
        if missing:
            targets[name] = missing
    return {'verification': findings, 'gaps': gaps, 'repair_targets': targets,
            'verified_facts': {n: {f: [c for c in cs if c['status'] == 'verified'] for f, cs in fs.items()}
                               for n, fs in findings.items()}}
