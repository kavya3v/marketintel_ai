"""Deterministic, evidence-only presentation; never performs provider calls."""
import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from src.discovery_agent import DiscoveryError

REPORT_FORMAT_VERSION = '2.0'


def _clean(value):
    text = html.unescape(str(value or ''))
    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'</?[A-Za-z][^>]*>', ' ', text)
    text = re.sub(r'(?m)^\s*[-*+#]+\s+', '', text)
    text = re.sub(r'\|\s*[-:]+\s*\|', ' ', text)
    text = text.replace('|', ' / ').replace('**', '').replace('`', '')
    return ' '.join(text.split()).strip(' /')


def _text(value):
    return re.sub(r'([\\`*_{}\[\]<>#!$])', r'\\\1', _clean(value))


def _urls(claim):
    result = []
    for url in claim.get('evidence_urls', []):
        if isinstance(url, str) and not re.search(r'[\s<>]', url):
            parsed = urlparse(url)
            if parsed.scheme in ('https', 'http') and parsed.hostname and not parsed.username:
                result.append(url)
    return list(dict.fromkeys(result))


def _short(claim, limit=210):
    # The context may contain plan, role or eligibility restrictions absent from
    # the short value. Preserve it whole, or omit rather than remove qualifiers.
    text = _clean(claim.get('context') or claim.get('quote') or claim.get('value'))
    if not text or text.casefold() == 'not verified' or len(text) > limit:
        return ''
    return text


def _facts(fields, field, limit=5):
    result, seen = [], set()
    for claim in fields.get(field, []):
        if claim.get('status') != 'verified' or not _urls(claim):
            continue
        text = _short(claim)
        key = text.casefold()
        if text and key not in seen:
            result.append(dict(claim, display=text))
            seen.add(key)
    return result[:limit]


def _date(value):
    if not isinstance(value, str) or value == 'Not verified':
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _news(fields, timestamp):
    reference = _date(timestamp)
    if reference is None:
        return []
    result, seen = [], set()
    for claim in _facts(fields, 'recent_news', 100):
        published = _date(claim.get('publication_date'))
        if published is None or not 0 <= (reference.date() - published.date()).days <= 90:
            continue
        if len(claim.get('publication_date', '').strip()) > 10 and published > reference:
            continue
        text = claim['display']
        # A newly dated directory entry about an old funding event is not new funding.
        if re.search(r'funding|series\s+[a-f]|raised|round', text, re.I):
            event_dates = [_date(v) for v in re.findall(r'\b\d{4}-\d{2}-\d{2}\b', text)]
            if any(v and (reference.date() - v.date()).days > 90 for v in event_dates):
                continue
        key = (text.casefold(), published.date().isoformat())
        if key not in seen:
            result.append(dict(claim, display_date=published.date().isoformat()))
            seen.add(key)
    return result[:5]


MONEY = re.compile(r'(?P<currency>USD|EUR|GBP|CAD|AUD|US\$|CA\$|AU\$|[$€£])\s*(?P<amount>\d+(?:[.,]\d+)*)', re.I)
PLAN = r'(Free|Basic|Pro|Business|Enterprise|Team|Starter|Standard|Premium|Personal|Plus|Unlimited)'


def _pricing(fields):
    rows, seen = [], set()
    for claim in fields.get('pricing', []):
        if claim.get('status') != 'verified' or not _urls(claim):
            continue
        raw = str(claim.get('context') or claim.get('quote') or claim.get('value') or '')
        text = _clean(raw)
        if not text:
            continue
        plan = re.search(r'\b' + PLAN + r'\s+(?:plan|tier)\b', text, re.I)
        if not plan:
            plan = re.search(r'^\s*' + PLAN + r'(?:\s*$|\n|\s{2,})', raw, re.I)
        if not plan:
            plan = re.search(r'^\s*' + PLAN + r'\s+(?:costs?|is)\b', text, re.I)
        plan_name = plan.group(1) if plan else 'Not verified'
        money = list(MONEY.finditer(text))
        named_plans = {p.casefold() for p in re.findall(r'\b' + PLAN + r'\s+(?:plan|tier)\b', text, re.I)}
        named_plans.update(p.casefold() for p in re.findall(r'(?m)^\s*' + PLAN + r'\s*$', raw, re.I))
        custom = bool(re.search(r'\bcustom(?:\s+enterprise)?\s+pricing\b|\bcontact\s+sales\b|\blet.s talk\b|^custom$', text, re.I)
                      or re.search(r'(?m)^\s*custom\s*$', raw, re.I))
        free = bool(re.search(r'\bfree\s+(?:plan|account)\b|^free$', text, re.I)) and not bool(re.search(r'free trial', text, re.I))
        period = re.search(r'(?:per\s+(?:(?:user|seat|member|team|workspace)\s+per\s+)?|/\s*)(?:month|year|week|day)\b', text, re.I)
        billing = re.search(r'\bbilled\s+(?:annually|monthly|yearly|quarterly)\b', text, re.I)
        model = 'Custom enterprise' if custom else 'Free' if free else 'Subscription' if period or billing else 'Unknown'
        # Multiple rates in one excerpt have ambiguous associations: never pair arbitrarily.
        amount = money[0].group('amount') if len(money) == 1 and not custom else 'Not verified'
        currency = money[0].group('currency') if len(money) == 1 and not custom else 'Not verified'
        terms = '; '.join(v.group() for v in (period, billing) if v) or 'Not verified'
        if len(money) > 1 or len(named_plans) > 1:
            plan_name, terms, model = 'Not verified', 'Not verified', 'Unknown'
            amount, currency = 'Not verified', 'Not verified'
        if model == 'Unknown' and amount == 'Not verified':
            continue  # VAT footers and project limits are not price records.
        row = {'plan': plan_name, 'amount': amount, 'currency': currency, 'period': terms,
               'model': model, 'urls': _urls(claim)}
        key = tuple(row[k].casefold() for k in ('plan', 'amount', 'currency', 'period', 'model'))
        if key in seen:
            prior = next(r for r in rows if tuple(r[k].casefold() for k in ('plan', 'amount', 'currency', 'period', 'model')) == key)
            prior['urls'] = list(dict.fromkeys(prior['urls'] + row['urls']))
        else:
            rows.append(row)
            seen.add(key)
    return rows[:8]


def report_fingerprint(state):
    keys = ('company', 'industry', 'research_timestamp', 'verification', 'gaps', 'errors', 'extraction_errors')
    payload = {key: state.get(key) for key in keys}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _insight(claim):
    text = claim['display'].casefold()
    if re.search(r'\bapi\b|integrat|\bmcp\b|connect', text):
        return ('Integration breadth may affect adoption effort for teams with established toolchains.',
                'Prototype the cited integration in one representative workflow and measure setup effort and failure recovery.')
    if re.search(r'secur|permission|complian|gdpr|iso|role', text):
        return ('Governance requirements may influence product evaluation independently of feature breadth.',
                'Map the cited capability against a buyer security checklist and validate access-control scenarios.')
    if re.search(r'\bai\b|search|knowledge|answer', text):
        return ('Knowledge retrieval quality may matter more than an AI feature label for the intended workflow.',
                'Benchmark a fixed set of real questions, checking answer accuracy, citations, freshness, and time to completion.')
    return ('The documented workflow capability may affect task completion for its intended users.',
            'Test the cited workflow with representative users and compare completion time and errors before prioritizing changes.')


def generate_briefing(state):
    if state.get('approval_status') != 'approved':
        raise DiscoveryError('A briefing can only be generated after human approval.')
    fields_by_name = state.get('verification', {})
    prepared = {name: {'features': _facts(fields, 'core_features'), 'positioning': _facts(fields, 'positioning', 2),
        'customers': _facts(fields, 'target_customers', 2), 'pricing': _pricing(fields),
        'news': _news(fields, state.get('research_timestamp'))} for name, fields in fields_by_name.items()}
    references = {}
    def cite(urls):
        markers = []
        for url in dict.fromkeys(urls):
            if url not in references:
                references[url] = len(references) + 1
            markers.append(f'[{references[url]}]')
        return ' '.join(markers)
    def describe(claim):
        return _text(claim['display']) + ' ' + cite(_urls(claim))
    def describe_many(claims):
        return '; '.join(describe(c) for c in claims) or 'Not verified'

    lines = [f"# Competitor briefing: {_text(state.get('company', ''))}",
        f"Company: {_text(state.get('company', ''))}", f"Industry: {_text(state.get('industry', ''))}",
        f"Research timestamp (UTC): {_text(state.get('research_timestamp', 'Not verified'))}",
        '', '## Executive summary',
        'The saved evidence highlights different documented emphases, not exclusive capabilities. '
        'Analysis below is a hypothesis for product evaluation; it does not establish a feature gap in the target company.']
    highlights = []
    for name, data in prepared.items():
        candidate = next(iter(data['positioning'] or data['features']), None)
        if candidate:
            highlights.append(f"- **{_text(name)}:** {describe(candidate)} "
                '**Analysis (hypothesis):** ' + _insight(candidate)[0])
    for name, data in prepared.items():
        if len(highlights) >= 5:
            break
        if data['pricing']:
            kinds = ', '.join(dict.fromkeys(p['model'] for p in data['pricing']))
            urls = [u for p in data['pricing'] for u in p['urls']]
            highlights.append(f"- **{_text(name)} pricing:** {_text(kinds)} {cite(urls)} "
                '**Analysis (hypothesis):** Validate procurement fit and complete costs before using price in prioritization.')
    lines.extend(highlights[:5] or ['Insufficient verified evidence for a supported competitive summary.'])
    lines += ['', '## Competitive landscape overview',
        f"The run covers {len(prepared)} competitor(s): " + ', '.join(_text(n) for n in prepared) + '.',
        'The comparison summarizes saved evidence; unreported capabilities are unknown rather than absent.',
        '', '## Competitor comparison table',
        '| Competitor | Positioning | Target customer | Key capabilities | Pricing model | Evidence confidence |',
        '|---|---|---|---|---|---|']
    for name, data in prepared.items():
        values = [c for group in ('features', 'positioning', 'customers') for c in data[group]]
        pricing = '; '.join(dict.fromkeys(p['model'] for p in data['pricing'])) or 'Not verified'
        coverage = sum(bool(data[k]) for k in ('features', 'positioning', 'customers', 'pricing', 'news'))
        origin = 'Official vendor' if values and all(c.get('official') for c in values) else 'Mixed/third-party' if values else 'Insufficient'
        confidence = f'{origin}; {coverage}/5 sections covered; source-supported, not independently audited'
        lines.append(f"| {_text(name)} | {describe_many(data['positioning'])} | {describe_many(data['customers'])} | "
                     f"{describe_many(data['features'][:3])} | {_text(pricing)} | {_text(confidence)} |")
    lines += ['', '## Pricing comparison',
        'Currency symbols are preserved as symbols; a dollar sign alone does not verify a currency code. '
        'Custom pricing is not zero. Missing rates, plan associations, and terms remain Not verified.',
        '| Competitor | Plan | Amount | Currency | Billing period / terms | Pricing model | Evidence |',
        '|---|---|---|---|---|---|---|']
    for name, data in prepared.items():
        for row in data['pricing'] or [{'plan': 'Not verified', 'amount': 'Not verified', 'currency': 'Not verified',
                                      'period': 'Not verified', 'model': 'Unknown', 'urls': []}]:
            cells = [name, row['plan'], row['amount'], row['currency'], row['period'], row['model']]
            lines.append('| ' + ' | '.join(_text(v) for v in cells) + ' | ' + (cite(row['urls']) or 'Not verified') + ' |')
    lines += ['', '## Recent news', 'Only verified publication dates within the 90 calendar days ending at the research timestamp qualify.']
    for name, data in prepared.items():
        lines += ['', f'### {_text(name)}']
        lines.extend([f"- {c['display_date']}: {describe(c)}" for c in data['news']] or ['No verified recent news found.'])
    lines += ['', '## Strategic implications and recommended actions',
              '### Strategic opportunities — analysis and hypotheses, not established facts']
    insights, seen = [], set()
    for offset in range(5):
        for name, data in prepared.items():
            if len(data['features']) <= offset:
                continue
            feature = data['features'][offset]
            key = feature['display'].casefold()
            if key not in seen:
                insights.append((name, feature))
                seen.add(key)
    for index, (name, feature) in enumerate(insights[:5], 1):
        implication, step = _insight(feature)
        lines += ['', f'#### {index}. Evaluate {_text(name)}\'s documented capability',
                  f'- **Observation:** {describe(feature)}',
                  f'- **Strategic implication (hypothesis):** {implication}',
                  f'- **Recommended next step (hypothesis to test):** {step}']
    if not insights:
        lines.append('Insufficient verified capability evidence for grounded strategic recommendations.')
    lines += ['', '## Detailed competitor profiles']
    for name, data in prepared.items():
        lines += ['', f'### {_text(name)}']
        for field, label in [('positioning', 'Positioning'), ('customers', 'Target customers'), ('features', 'Key capabilities')]:
            lines.append(f'**{label}:**')
            lines.extend(['- ' + describe(c) for c in data[field]] or ['Not verified.'])
        prices = []
        for price in data['pricing']:
            label = price['model']
            if price['amount'] != 'Not verified':
                label += f" — {price['currency']} {price['amount']}"
                if price['period'] != 'Not verified':
                    label += ' ' + price['period']
            prices.append(label)
        lines.append('**Pricing:** ' + ('; '.join(_text(v) for v in dict.fromkeys(prices)) or 'Not verified') + ' (see pricing comparison).')
        lines.append('**News:** ' + (f"{len(data['news'])} qualifying item(s); see recent news." if data['news'] else 'No verified recent news found.'))
    counts = Counter(c.get('status', 'missing') for fields in fields_by_name.values() for claims in fields.values() for c in claims)
    gaps = list(dict.fromkeys(state.get('gaps', [])))
    failures = list(dict.fromkeys(str(e) for e in state.get('errors', []) if 'extract' in str(e).casefold()))
    lines += ['', '## Research quality and limitations',
        f"Recorded claim statuses before presentation deduplication: **{counts['verified']} verified**, "
        f"**{counts['unsupported']} unsupported**, **{counts['inferred']} inferred**, "
        f"**{counts['conflicting']} conflicting**, **{counts['missing']} missing**.",
        f'Research gaps: **{len(gaps)}**. Recorded extraction failures/warnings: **{len(failures)}**.',
        'Verified here means supported by saved excerpts, not independently audited truth. Vendor marketing is vendor-reported. '
        'Unsupported, conflicting and inferred claims are excluded from factual comparisons. '
        'This formatter does not rerun verification or repair historical verification decisions. '
        'Long claims that cannot be safely shortened are omitted; missing coverage is not evidence of a product weakness.',
        '', '**Pricing and news coverage:**']
    for name, data in prepared.items():
        numeric = any(p['amount'] != 'Not verified' for p in data['pricing'])
        lines.append(f"- {_text(name)}: numeric pricing {'available' if numeric else 'Not verified'}; "
                     f"{'dated recent news available' if data['news'] else 'No verified recent news found.'}")
    lines += ['', '### Research gaps']
    lines.extend(['- ' + _text(g) for g in gaps] or ['No recorded gaps.'])
    if failures:
        lines += ['', '**Extraction failures/warnings:**', *['- ' + _text(e) for e in failures]]
    other_errors = list(dict.fromkeys(str(e) for e in state.get('errors', []) if str(e) not in failures))
    if other_errors:
        lines += ['', '**Other research warnings:**', *['- ' + _text(e) for e in other_errors]]
    lines += ['', '## Source references']
    for url, number in references.items():
        lines.append(f'- [{number}]')
    lines.append('')
    lines.extend(f'[{number}]: <{url}>' for url, number in references.items())
    if not references:
        lines.append('No verified factual sources available.')
    return {'final_report': '\n'.join(lines), 'approval_status': 'approved',
            'report_formatter_version': REPORT_FORMAT_VERSION, 'report_source_fingerprint': report_fingerprint(state)}
