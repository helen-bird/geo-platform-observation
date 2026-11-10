#!/usr/bin/env python3
"""Recompute public headline statistics and build the interim review pages."""
from collections import Counter, defaultdict
from fractions import Fraction
from html import escape
from itertools import combinations
import json
from pathlib import Path
import re
from statistics import median
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from build_learning_hub import CSS
from build_stage5_report import EXTRA, note, table
from report_series import CSS as SERIES_CSS, INTERIM_READER, series_navigation
from site_metadata import finalize_page

ROOT = Path(__file__).resolve().parents[1]
ROUTE = str(Path(INTERIM_READER).parent)
FOLDER = ROOT / ROUTE
METADATA = json.loads((FOLDER / 'record.json').read_text())
DATA = FOLDER / 'data'


def read_lines(name):
    with (DATA / name).open() as source:
        return [json.loads(line) for line in source]


def subset_rates(values, n):
    reference = Fraction(sum(values), len(values))
    rates = [Fraction(sum(combo), n) for combo in combinations(values, n)]
    return {
        'subsets': len(rates),
        'min': float(min(rates)),
        'max': float(max(rates)),
        'over_10_pp': sum(abs(rate - reference) > Fraction(1, 10) for rate in rates),
        'over_20_pp': sum(abs(rate - reference) > Fraction(1, 5) for rate in rates),
    }


def summarize():
    groups = defaultdict(dict)
    answers = read_lines('answers.jsonl')
    attempts = read_lines('attempts.jsonl')
    measurements = read_lines('measurements.jsonl')
    selected_ids = {r['answer_id'] for r in answers}
    assert len(answers) == len(measurements) == len(selected_ids) == 300
    assert selected_ids == {r['answer_id'] for r in measurements}
    assert selected_ids == {r['attempt_id'] for r in attempts if r['selected']}
    for row in measurements:
        groups[row['condition_id']][row['block_id']] = row
    assert len(groups) == 20 and all(set(g) == set(range(1, 16)) for g in groups.values())
    assert len(attempts) == len({r['attempt_id'] for r in attempts}) == 310
    assert all(row['answer_text'].strip() and row['search_enabled'] for row in answers)

    def values(condition, key):
        result = [groups[condition][i]['binary'][key] for i in range(1, 16)]
        assert all(type(value) is bool for value in result)
        return result

    def overlap(left, right):
        return Fraction(len(left & right), len(left | right))

    q3 = [[set(groups['S6-Q3-' + env][i]['sets']['recommended_entities'])
           for i in range(1, 16)] for env in ('OPENAI', 'GROK')]
    all_left, all_right = [set.union(*side) for side in q3]
    two = [overlap(q3[0][i] | q3[0][j], q3[1][i] | q3[1][j])
           for i, j in combinations(range(15), 2)]
    three = [overlap(*(set.union(*(side[i] for i in ids)) for side in q3))
             for ids in combinations(range(15), 3)]
    discovery = {
        env: {task: sum(values(f'S6-{task}-{env}', 'discovery_success')) for task in 'ABC'}
        for env in ('OPENAI', 'GROK')
    }
    rate_series = {
        'exact_quote_openai': values('S6-B-OPENAI', 'discovery_success'),
        'artur_or_work_grok_q3': values('S6-Q3-GROK', 'candidate_artur-ferreira_recommendation'),
    }
    citations = Counter(
        row['condition_id'].rsplit('-', 1)[-1] for row in measurements if row['sets']['cited_domains']
    )
    return {
        'answers': len(answers),
        'historical_answers': 60,
        'submissions': sum(row['submission_recorded'] for row in attempts),
        'attempts': len(attempts),
        'terminal_outcomes': dict(Counter(r['outcome'] for r in attempts)),
        'q3_overlap': {
            'full_intersection': len(all_left & all_right), 'full_union': len(all_left | all_right),
            'matched_n2_subsets': len(two), 'matched_n2_below_25_pct': sum(j < Fraction(1, 4) for j in two),
            'matched_n2_median': float(median(two)), 'matched_n3_max': float(max(three)),
        },
        'discovery_success_out_of_15': discovery,
        'grok_q1_the_geo_lab_recommendations': sum(values('S6-Q1-GROK', 'candidate_artur-ferreira_recommendation')),
        'grok_q1_artur_name_mentions': sum(values('S6-Q1-GROK', 'candidate_artur-ferreira_person_mention')),
        'answers_with_visible_final_citation_domains': dict(citations),
        'rate_sensitivity': {
            key: {'full_count': sum(series), 'full_n': len(series),
                  'n3': subset_rates(series, 3), 'n10': subset_rates(series, 10),
                  'first10_n3': subset_rates(series[:10], 3)}
            for key, series in rate_series.items()
        },
    }


def section(key, title, body):
    return f'<section id="{key}"><h2>{title}</h2>{body}</section>'


def page(filename, title, description, sections, utility):
    nav = ''.join(f'<a href="#{key}">{label}</a>' for key, label, _ in sections)
    content = ''.join(section(*part) for part in sections)
    reports = json.loads((ROOT / 'report-versions.json').read_text())['reports']
    series = series_navigation(reports, ROUTE, INTERIM_READER, 'reader' if filename == 'index.html' else 'appendix')
    text = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<meta name="description" content="{escape(description, quote=True)}"><style>{CSS}{EXTRA}{SERIES_CSS}
figure{{margin:20px 0}}figure img{{display:block;width:100%;max-width:980px;height:auto}}figcaption{{font-size:14px;color:var(--muted)}}
</style></head><body><a class="skip" href="#main">Skip to the review</a><div class="layout">
<nav aria-label="Interim review contents">{series}<strong>On this page</strong><div class="nav-links">{nav}</div>
<div class="nav-group">{utility}<a href="public-data.zip">Download public data</a></div></nav>
<main id="main"><p class="lesson-name">GEO Lab Interim Review · Part 1</p><h1>{escape(title)}</h1>
<p class="author">Helen Bird · Published {METADATA['first_published']} · v{METADATA['version']}</p>
{content}<p class="footer">Helen Bird · GEO Learning Log · <a href="https://github.com/helen-bird/geo-platform-observation">GitHub repository</a></p></main></div></body></html>'''
    return finalize_page(text, f'{ROUTE}/{filename}', kind='reader')


def reader(summary):
    q3 = summary['q3_overlap']
    discovery = summary['discovery_success_out_of_15']
    rates = summary['rate_sensitivity']
    title = 'Which GEO findings held up after 300 new answers?'
    assumptions = '''<p>An interim review is a checkpoint in the ongoing GEO Lab. Here we revisit earlier findings and use the evidence to shape the next experiments.</p>
<ul><li><strong>Several historical findings would recur.</strong> These include low cross-platform recommendation overlap and recommendations of a work without a named author.</li>
<li><strong>Three answers would give unstable estimates of some rates.</strong> We expected larger subsets to be less sensitive to which runs were included.</li></ul>'''
    method = '''<p>We reran ten original prompts from GEO Labs #01–#04 fifteen times per environment, for <strong>300 new answers</strong>. We compared them with 60 historical answers. The two environments were OpenAI Responses API with web search and Grok Expert in the web interface with web search.</p>
<p>For each condition we checked all 455 ways to keep three answers and all 3,003 ways to keep ten. For cross-environment comparisons, we used the same scheduled block numbers on both sides.</p>'''
    method += note('Labs #01 and #04 share the new answers for three identical prompts. Lab #05 covered technical discoverability and is outside this answer replication. Matching uses scheduled block numbers; actual submission times differ.')
    conclusions = f'''<ul>
<li><strong>Low recommendation overlap held up.</strong> On the tutorial prompt, overlap was below 25% in all {q3['matched_n2_subsets']} matched comparisons using two answers per environment. Median overlap was {q3['matched_n2_median']:.1%}. The full lists shared {q3['full_intersection']} of {q3['full_union']} distinct recommendation units.</li>
<li><strong>Direct access and natural discovery differed.</strong> Grok read the original X post in {discovery['GROK']['A']}/15 direct-link runs and found it in {discovery['GROK']['C']}/15 natural-search runs. The OpenAI API identified it in {discovery['OPENAI']['B']}/15 exact-quote runs through a public archive that became available after the original experiment.</li>
<li><strong>Work and author visibility diverged.</strong> On the free-learning prompt, Grok recommended The GEO Lab in {summary['grok_q1_the_geo_lab_recommendations']}/15 answers and named Artur Ferreira in {summary['grok_q1_artur_name_mentions']}/15. Measurement prompts usually elicited workflows and score-verification prompts usually elicited checklists. Evidence remains insufficient to establish whether wording changes consistently outweigh repeat variation.</li>
<li><strong>Three answers could give very different rates.</strong> On the tutorial prompt, Grok recommended Artur or his work in {rates['artur_or_work_grok_q3']['full_count']}/15 answers. Three-answer subsets ranged from 0% to 100%. For two example rates, the share of subsets more than 20 percentage points from the full-panel rate fell from 51.6% at three runs to 0.37% at ten.</li></ul>
<figure><img src="finite-panel-sensitivity.svg" alt="Four panels comparing the effect of keeping 3, 5, 7, 10 or 15 answers on measured rates and list overlap."><figcaption>Subset distributions from the observed 15-answer panels. At 15, there is only one possible subset.</figcaption></figure>
<p>Three runs can show that an outcome occurred. Ten to fifteen can support a more informative description of a fixed prompt. Estimating a rate to a specific precision requires a separate sample-size decision.</p>'''
    conclusions += note('The OpenAI arm measures the API setup. Earlier ChatGPT consumer results used a different environment. This comparison does not identify a causal effect of GEO optimization.')
    conclusions += '<p><a href="technical-appendix.html">See all twelve historical claim decisions and the public evidence.</a></p>'
    return page('index.html', title, 'GEO Lab interim review of 300 new AI search answers, which historical findings held up, and what changes when only three or ten runs are kept.',
                [('hypotheses', '1. What did we expect?', assumptions), ('validation', '2. How did we test it?', method), ('conclusions', '3. What did we find?', conclusions)],
                '<a href="technical-appendix.html">Methods and evidence</a>')


def appendix(summary):
    claims = json.loads((DATA / 'claims.json').read_text())
    assert len(claims) == 12
    claim_table = table(['Historical claim ID', 'Decision', 'Observed evidence'], [
        [escape(row[key]) for key in ('claim_id', 'status', 'observed_result')] for row in claims
    ])
    methods = '''<p>Collection took place November 7–10, 2026, Beijing time. OpenAI used <code>gpt-5.6-sol</code>, medium reasoning and a 16-call native web-search cap. The maximum recorded number of web-search calls was 15. Grok used fresh ordinary Expert chats with an explicit web-search chip and both personalization settings disabled for collection. Expert is the visible model label. An exact backend version is unavailable.</p>
<p>The ledger retains 305 submitted attempts and five preparations without a submission. Of the submissions, 300 were selected, four OpenAI outcomes remained unresolved, and one complete Grok response was excluded for mode deviation.</p>
<p>Set overlap is intersection size divided by union size. Unknown sets and comparisons of two observed empty sets are handled separately. Citation domains represent final answer sources. A source panel item is retrieval evidence and is recorded separately.</p>'''
    methods += note('Across the 150 planned pairs, the median absolute submission gap was 2.35 hours and the maximum was 52.15 hours. Historical interface, tool-cap and source availability differences limit comparisons across batches. The historical ChatGPT consumer interface and the current OpenAI Responses API are separate environments.')
    rate_table = []
    for key, name in [('exact_quote_openai', 'Exact quote, OpenAI API'), ('artur_or_work_grok_q3', 'Artur or his work, Grok Q3')]:
        record = summary['rate_sensitivity'][key]
        for n in ('n3', 'n10'):
            row = record[n]
            rate_table.append([name, n[1:], f"{row['min']:.0%}–{row['max']:.0%}", f"{row['over_20_pp']:,}/{row['subsets']:,} ({row['over_20_pp']/row['subsets']:.2%})"])
    sensitivity = table(['Metric', 'Answers kept', 'Rate range', 'More than 20 pp from the full rate'], rate_table)
    sensitivity += note('Subsets reuse answers and their distribution describes this batch. The 95% Wilson intervals for 11/15 and 4/15 are about 48%–89% and 11%–52%. The interval model assumes approximately independent binary observations.')
    files = '''<ul><li><a href="data/conditions.json">Original prompts and condition identifiers</a></li>
<li><a href="data/answers.jsonl">300 redacted answer records with links, visible queries and source panels</a></li>
<li><a href="data/attempts.jsonl">310 attempt histories with recorded submission and failure statuses</a></li>
<li><a href="data/measurements.jsonl">Normalized outcomes and sets used for calculations</a></li>
<li><a href="data/claims.json">All twelve claim decisions</a> · <a href="data/summary.json">Recomputed summary</a> · <a href="public-data.zip">Data archive</a></li></ul>
<p>Reproduce the headline metrics offline with <code>python3 scripts/build_interim_review.py</code> from the repository root. See the <a href="https://github.com/helen-bird/geo-platform-observation/tree/main/reviews/interim-review/historical-replication">GitHub experiment record</a> for the data guide. Cite a commit permalink and an answer ID to point to a fixed record.</p>'''
    files += note('Public records omit private conversation links, unverified document-sharing links, credentials, account details, local paths, opaque provider IDs, signed and tracking parameters, and private interface captures. Search evidence unavailable from the provider remains unknown. Exported bodies may differ from the private originals where redaction was necessary.')
    return page('technical-appendix.html', 'Historical replication and sample-size evidence', 'Methods, twelve historical claim decisions, observed subset distributions and a redacted dataset for 300 new AI search answers.',
                [('method', 'Methods and collection', methods), ('claims', 'Historical claims', claim_table), ('subsets', 'Subset results', sensitivity), ('data', 'Data and reproduction', files)],
                '<a href="./">Return to the report</a>')


def main():
    summary = summarize()
    assert summary['q3_overlap']['matched_n2_below_25_pct'] == 105
    assert summary['submissions'] == 305
    (DATA / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    (FOLDER / 'index.html').write_text(reader(summary))
    (FOLDER / 'technical-appendix.html').write_text(appendix(summary))
    with ZipFile(FOLDER / 'public-data.zip', 'w') as archive:
        for path in sorted(DATA.iterdir()):
            name = path.relative_to(FOLDER).as_posix()
            archive.writestr(ZipInfo(name), path.read_bytes(), compress_type=ZIP_DEFLATED)


def check():
    summary = summarize()
    assert summary == json.loads((DATA / 'summary.json').read_text())
    assert summary['q3_overlap']['matched_n2_below_25_pct'] == 105
    assert summary['submissions'] == 305
    assert (FOLDER / 'index.html').read_text() == reader(summary)
    assert (FOLDER / 'technical-appendix.html').read_text() == appendix(summary)
    private_pattern = re.compile(
        r'https?://(?:www\.)?(?:chatgpt\.com/(?:c|s|share)/|grok\.com/(?:c|share)/|claude\.ai/chat/)'
        r'|https?://(?:docs\.google\.com|drive\.google\.com)/|https?://[^/\s<>"\x27]+@'
        r'|file://|/var/folders/|\blocalhost\b|127\.0\.0\.1'
        r'|\b(?:resp|req|ws|msg|rs)_[A-Za-z0-9_-]{12,}\b'
        r'|\b(?:sk-(?:proj-)?|gh[pousr]_)[A-Za-z0-9_-]{20,}'
        r'|Bearer [A-Za-z0-9._-]{16,}|[\w.-]+@[\w.-]+\.[A-Za-z]{2,}'
        r'|[?&](?:utm_\w+|gclid|fbclid|token|api_key|session_id|signature|x-(?:amz|goog)-[^=]+)=', re.I
    )
    with ZipFile(FOLDER / 'public-data.zip') as archive:
        expected = {path.relative_to(FOLDER).as_posix() for path in DATA.iterdir()}
        assert set(archive.namelist()) == expected and archive.testzip() is None
        for name in expected:
            body = archive.read(name)
            assert body == (FOLDER / name).read_bytes()
            text = body.decode()
            assert '/Users/' not in text and not private_pattern.search(text), name
    print(json.dumps({'interim_review': 1, 'answers': 300, 'attempts': 310,
                      'reproduction_privacy_and_archive': 'passed'}))


if __name__ == '__main__':
    main()
