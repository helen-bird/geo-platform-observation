"""Deterministic post-hoc sensitivity views; no classification, calls or input edits.

``analyze_extensions(protocol, runs, analyzed, root)`` reads only the explicit
entity-normalization.json at root. Eligibility comes from the existing reviewed
sets in analyzed, not from keywords in the answer. All output URLs are cleaned
with the public export query policy; exact returned URLs remain in input records.
"""
from collections import Counter
from itertools import combinations, product
import json
from math import fsum
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


CATEGORIES = {
    'geo_visibility_product': 'GEO visibility products',
    'general_measurement_tool': 'General measurement tools',
    'research_or_publication_channel': 'Research or publication channels',
    'other_ai_surface_or_feature': 'Other AI surfaces or features',
}
TRACKING = {
    'trk', 'ref', 'referrer', 'roistat_visit', '_ga', '_gl', '_bhlid',
    'fbclid', 'gclid', 'isappinstalled', 'ck_subscriber_id', 'sh_kit',
    'campaign', 'st_source', 'mc_cid', 'mc_eid', 'igshid', 'fpr', 'via',
    'aff', 'aff_id', 'affiliate', 'srsltid', 'mkt_tok', 'spm', 'client_id',
    'session_id', 'request_id', 'response_id', '_rsc', 'cluster', 'cluster_id',
    'access_token', 'refresh_token', 'token', 'api_key', 'apikey', 'key',
    'signature', 'sig', 'credential', 'authorization', 'policy', 'password',
    'secret', 'expires', 'awsaccesskeyid', 'googleaccessid', 'key-pair-id',
}
REMOVED_PREFIXES = ('utm_', 'autm_', 'x-amz-', 'x-goog-')
PRIVATE_CHAT = re.compile(
    r'https?://(?:chatgpt\.com/(?:c|s|share)/|grok\.com/c/)', re.I)
BODY_URL = re.compile(r'https?://[^\s<>"\'\ue000-\uf8ff]+')


def clean_comparison_url(value):
    """Same query cleanup as export_stage3_public.public_url, without I/O.

    Invalid/private URLs and credential-bearing authorities are withheld. Host,
    path and fragment are not repaired, decoded, resolved or stripped of www.
    Query parsing/encoding intentionally matches the publication exporter.
    """
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        if (parts.scheme not in ('http', 'https') or not parts.hostname
                or parts.hostname in {'localhost', '127.0.0.1', '0.0.0.0'}
                or PRIVATE_CHAT.search(value) or parts.username or parts.password):
            return None
    except ValueError:
        return None
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith(REMOVED_PREFIXES)
             and k.lower() not in TRACKING]
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(query), parts.fragment))


def _label(platform):
    return 'Grok Expert · consumer interface' if platform == 'Grok' else platform


def _key(run):
    return (run.get('prompt_id', ''), run.get('repeat', 0), run['id'])


def _overlap(left, right):
    if left is None or right is None:
        return {'value': None, 'reason': 'Unavailable: one or both sets ineligible.',
                'eligible': False, 'both_empty': False, 'left_size': None,
                'right_size': None, 'intersection': None, 'union': None,
                'shared': None}
    left, right = set(left), set(right)
    shared, union = left & right, left | right
    return {'value': len(shared) / len(union) if union else None,
            'reason': 'N/A: both eligible sets are empty.' if not union else None,
            'eligible': True, 'both_empty': not union,
            'left_size': len(left), 'right_size': len(right),
            'intersection': len(shared), 'union': len(union),
            'shared': sorted(shared)}


def _pair(left, right, sets):
    return {'left': left['id'], 'right': right['id'],
            'left_attempt_id': left.get('selected_attempt_id') or left.get('_coding', {}).get('id'),
            'right_attempt_id': right.get('selected_attempt_id') or right.get('_coding', {}).get('id'),
            'left_prompt_id': left.get('prompt_id'),
            'right_prompt_id': right.get('prompt_id'),
            **_overlap(sets.get(left['id']), sets.get(right['id']))}


def _pair_summary(pairs, planned_pairs):
    numeric = [p['value'] for p in pairs if p['value'] is not None]
    return {'planned_pairs': planned_pairs, 'observed_pairs': len(pairs),
            'eligible_pairs': sum(p['eligible'] for p in pairs),
            'numeric_pairs': len(numeric),
            'both_empty_pairs': sum(p['both_empty'] for p in pairs),
            'unavailable_pairs': sum(not p['eligible'] for p in pairs),
            'missing_pair_records': max(0, planned_pairs - len(pairs)),
            'mean': fsum(numeric) / len(numeric) if numeric else None,
            'minimum': min(numeric) if numeric else None,
            'maximum': max(numeric) if numeric else None}


def _pool(group, sets):
    eligible = [r for r in group if sets.get(r['id']) is not None]
    members = [set(sets[r['id']]) for r in eligible]
    union = set().union(*members) if members else None
    return {'eligible_denominator': len(eligible), 'planned_positions': len(group),
            'eligible_ids': [r['id'] for r in eligible],
            'union': sorted(union) if union is not None else None,
            'partial_coverage': len(eligible) != len(group),
            'prevalence': {name: {'numerator': sum(name in s for s in members),
                                  'denominator': len(members)}
                           for name in sorted(union or [])}}


def _contrast(left, right, sets):
    a, b = _pool(left, sets), _pool(right, sets)
    return {'left': a, 'right': b,
            'pooled_overlap': _overlap(a['union'], b['union'])}


def _platforms(runs):
    present = {r.get('platform') for r in runs if r.get('platform')}
    preferred = ['OpenAI API + web search', 'Grok']
    return [p for p in preferred if p in present] + sorted(present - set(preferred))


def _groups(runs, platform, intent):
    left = sorted([r for r in runs if r.get('platform') == platform
                   and r.get('prompt_id') == intent + '1'], key=_key)
    right = sorted([r for r in runs if r.get('platform') == platform
                    and r.get('prompt_id') == intent + '2'], key=_key)
    return left, right


def _recommended(analyzed, run):
    value = analyzed.get(run['id'], {}).get('sets', {}).get('recommended_tools')
    return sorted(set(value)) if value is not None else None


def _reviewed_url_inventory(run, existing):
    """Return cleaned reviewed URLs, plus parallel representation diagnostics.

    No URL is made a citation merely because it appears in the answer text.
    Explicit links must already belong to the reviewed answer-source inventory.
    """
    code = run.get('_coding', {})
    sources = code.get('answer_sources')
    raw = run.get('answer_links')
    observed_eligible = existing.get('sets', {}).get('observed_cited_domains') is not None
    if not observed_eligible or not isinstance(sources, list) or not isinstance(raw, list):
        return {'observed_urls': None, 'strict_urls': None,
                'citation_mapping_complete': code.get('capture_scope', {}).get('citation_mapping_complete'),
                'reason': 'Existing reviewed source inventory is unavailable/ineligible.',
                'records': [], 'unreviewed_explicit_comparison_urls': []}
    def counter(items):
        values = [clean_comparison_url(x.get('url'))
                  for x in items if isinstance(x, dict)]
        return Counter(v for v in values if v is not None)
    recorded, coded = counter(raw), counter(sources)
    # Compare privacy-cleaned equivalents so redaction cannot alter eligibility.
    valid = set(recorded) == set(coded)
    invalid_count = sum(clean_comparison_url(x.get('url')) is None
                        for x in sources + raw if isinstance(x, dict))
    if invalid_count:
        valid = False
    body_values = [m.group(0).rstrip('.,;)]}')
                   for m in BODY_URL.finditer(run.get('answer_text') or '')]
    body = Counter(u for u in map(clean_comparison_url, body_values) if u is not None)
    explicit = counter(code.get('explicit_body_links', []))
    reviewed = sorted(set(coded))
    complete_mapping = code.get('capture_scope', {}).get('citation_mapping_complete') is True
    strict_eligible = (valid and complete_mapping
                       and existing.get('sets', {}).get('cited_domains') is not None)
    return {'observed_urls': reviewed if valid else None,
            'strict_urls': reviewed if strict_eligible else None,
            'citation_mapping_complete': complete_mapping,
            'coverage_qualified': valid and not strict_eligible,
            'reason': ('Recorded/coded URL inventories disagree or contain withheld URLs.' if not valid
                       else 'Observed URL inventory only; complete citation mapping not confirmed.'
                       if not strict_eligible else None),
            'records': [{'comparison_url': u,
                         'representation_counts': {
                             'recorded_answer_links': recorded[u],
                             'coded_answer_sources': coded[u],
                             'explicit_body_URLs': body[u],
                             'coded_explicit_body_links': explicit[u]},
                         'count_in_URL_set': 1,
                         'exact_returned_URLs_retained_in_input_only': True}
                        for u in reviewed],
            'unreviewed_explicit_comparison_urls': sorted((set(body) | set(explicit)) - set(coded))}


def analyze_extensions(protocol, runs, analyzed, root):
    """Read-only post-hoc views of existing eligible sets and explicit mapping.

    Return JSON-serializable objects. Root is the input data directory, both for
    private collection and the redacted public edition. No output files or input
    mutation occur here. Missing mapping entries withhold affected lenses.
    """
    root = Path(root)
    issues = []
    path = root / 'entity-normalization.json'
    try:
        mapping = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(mapping, dict) or not isinstance(mapping.get('entities'), dict):
            raise ValueError('Expected an explicit entities object.')
    except (OSError, ValueError, TypeError):
        mapping = {'entities': {}, 'categories': dict(CATEGORIES), 'rules': []}
        issues.append('Explicit entity-normalization.json unavailable or invalid; no family/category inference performed.')
    categories = mapping.get('categories')
    categories = categories if isinstance(categories, dict) and categories else dict(CATEGORIES)
    rules = mapping['entities']
    strict = {r['id']: _recommended(analyzed, r) for r in runs}
    family, category = {}, {}
    filtered = {c: {} for c in categories}
    seen_names = {e['entity'] for r in runs for e in r.get('_coding', {}).get('entity_observations', [])
                  if isinstance(e, dict) and isinstance(e.get('entity'), str)}
    missing = sorted(seen_names - set(rules))
    if missing:
        issues.append('Some coded entity names have no explicit normalization rule; affected derived lenses are withheld.')
    per_answer = {}
    for run in runs:
        rid, names = run['id'], strict[run['id']]
        if names is None:
            family[rid] = category[rid] = None
            for c in categories:
                filtered[c][rid] = None
        else:
            rows = [rules.get(name) for name in names]
            family_ok = all(isinstance(row, dict) and isinstance(row.get('family'), str)
                            and row['family'] for row in rows)
            category_ok = all(isinstance(row, dict) and row.get('category') in categories
                              for row in rows)
            family[rid] = sorted({row['family'] for row in rows}) if family_ok else None
            category[rid] = sorted({row['category'] for row in rows}) if category_ok else None
            for c in categories:
                filtered[c][rid] = sorted(name for name in names if rules[name]['category'] == c) if category_ok else None
            if not family_ok or not category_ok:
                issues.append(f'{rid}: incomplete explicit family/category rule; strict set unchanged.')
        per_answer[rid] = {'strict': names, 'family': family[rid], 'category': category[rid],
                          'type_filtered': {c: filtered[c][rid] for c in categories}}

    platforms = _platforms(runs)
    within_cross, wording_lenses, intent_lenses = [], [], []
    lenses = {'strict': strict, 'family': family, 'category': category}
    for platform in platforms:
        for intent in ('M', 'V'):
            left, right = _groups(runs, platform, intent)
            within = [_pair(a, b, strict) for group in (left, right)
                      for a, b in combinations(group, 2)]
            cross = [_pair(a, b, strict) for a, b in product(left, right)]
            within_stats, cross_stats = _pair_summary(within, 6), _pair_summary(cross, 9)
            delta = ((cross_stats['mean'] - within_stats['mean']) * 100
                     if cross_stats['mean'] is not None and within_stats['mean'] is not None else None)
            within_cross.append({'platform': platform, 'environment_label': _label(platform),
                                 'intent': intent, 'metric': 'recommended_tools',
                                 'within': {'pairs': within, 'summary': within_stats},
                                 'cross': {'pairs': cross, 'summary': cross_stats},
                                 'delta_pp': delta,
                                 'answer_ids': [r['id'] for r in left + right],
                                 'unique_answer_denominator': len(left + right),
                                 'unit': 'Answer-pair Jaccard, reusing the same six answers; pairs are not independent trials.'})
            wording_lenses.append({'platform': platform, 'environment_label': _label(platform),
                                   'intent': intent,
                                   'views': {**{name: _contrast(left, right, values) for name, values in lenses.items()},
                                             'type_filtered': {c: _contrast(left, right, filtered[c]) for c in categories}}})
        left = sorted([r for r in runs if r.get('platform') == platform and r.get('intent', r.get('prompt_id', '')[:1]) == 'M'], key=_key)
        right = sorted([r for r in runs if r.get('platform') == platform and r.get('intent', r.get('prompt_id', '')[:1]) == 'V'], key=_key)
        intent_lenses.append({'platform': platform, 'environment_label': _label(platform),
                              'views': {**{name: _contrast(left, right, values) for name, values in lenses.items()},
                                        'type_filtered': {c: _contrast(left, right, filtered[c]) for c in categories}},
                              'unit': 'Pooled M-versus-V sets; different tasks, not a wording-only effect.'})

    url_answers = {r['id']: _reviewed_url_inventory(r, analyzed.get(r['id'], {})) for r in runs}
    url_sets = {
        'strict_urls': {rid: value['strict_urls'] for rid, value in url_answers.items()},
        'observed_urls': {rid: value['observed_urls'] for rid, value in url_answers.items()},
    }
    for metric in ('cited_domains', 'observed_cited_domains'):
        url_sets[metric] = {r['id']: analyzed.get(r['id'], {}).get('sets', {}).get(metric) for r in runs}
    url_wording = []
    for platform in platforms:
        for intent in ('M', 'V'):
            left, right = _groups(runs, platform, intent)
            url_wording.append({'platform': platform, 'environment_label': _label(platform),
                                'intent': intent,
                                'metrics': {name: _contrast(left, right, values) for name, values in url_sets.items()}})
    return {
        'schema_version': 1, 'analysis_status': 'posthoc_descriptive_sensitivity',
        'environments': [{'platform': p, 'environment_label': _label(p)} for p in platforms],
        'within_vs_cross': within_cross,
        'entity_lenses': {
            'mapping': {'file': 'entity-normalization.json', 'input_schema_version': mapping.get('schema_version'),
                        'rules': mapping.get('rules', []), 'categories': categories,
                        'mapped_entity_count': len(rules), 'coded_entity_count': len(seen_names),
                        'missing_entities': missing,
                        'interpretation': 'Post-hoc declared family/category sensitivity, not a correction of frozen strict coding.'},
            'per_answer': per_answer, 'wording_contrasts': wording_lenses, 'intent_contrasts': intent_lenses},
        'url_lens': {
            'normalization_policy': {
                'removed_query_keys': sorted(TRACKING), 'removed_query_prefixes': list(REMOVED_PREFIXES),
                'basis': 'Same declared query cleanup as export_stage3_public.public_url; private/invalid/userinfo URLs withheld.',
                'preserved': ['scheme', 'hostname including www', 'path including encoded text', 'fragment', 'non-sensitive query parameters'],
                'not_performed': ['redirect resolution', 'path/fragment decoding or repair', 'independent source verification'],
                'representation_rule': 'Deduplicate annotation, source-table and explicit-body representations by cleaned URL; unreviewed body URLs are diagnostic only.',
                'privacy': 'Only cleaned comparison URLs are emitted. Exact returned URLs remain in the input records; signed copies may cease to be fetchable after cleanup.'},
            'per_answer': url_answers, 'wording_contrasts': url_wording},
        'warnings': [
            'All analyses here are post-hoc descriptive extensions; the frozen strict coding and original metrics are unchanged.',
            'Within-wording six pairs and cross-wording nine pairs reuse the same six answers; do not treat them as 15 independent observations.',
            'Delta is cross-pair mean minus within-pair mean in percentage points; numeric denominators exclude both-empty N/A and unavailable pairs.',
            'M1 includes explicit no-GEO-budget/reliability cues; M2 explicitly asks for a free repeatable workflow. V1 and V2 change budget/context and action wording. These are not pure lexical substitutions.',
            'M-versus-V changes the task; no p-values, causal effects or universal wording penalty are estimated.',
            'OpenAI API + web search is not ChatGPT web/app performance; the API batch followed the Grok consumer batch, confounding time and interface.',
            'Family/category labels come only from the explicit reviewed file. Corporate-parent or keyword merging is not inferred.',
            'Observed URLs are a separate coverage-qualified view. The first native Grok records do not establish complete citation mapping or exact original hrefs.',
            'URL cleanup preserves encoded paths/fragments and does not repair suspicious or malformed-looking destinations.',
            'Human/source-validation status is not upgraded by this extension; existing assistant coding and provisional source judgments remain qualified.'],
        'validation_issues': sorted(set(issues)),
    }
