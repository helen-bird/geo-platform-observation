#!/usr/bin/env python3
"""Rebuild the visibility report from publication-safe answer-level evidence."""
from collections import Counter
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zipfile import ZipFile

from build_learning_hub import CSS
from build_stage5_report import EXTRA, note, table
from report_series import finish_page

ROOT = Path(__file__).resolve().parents[1]
ROUTE = 'stages/09-visibility-baseline'
FOLDER = ROOT / ROUTE
TITLE = 'GEO Lab #09: How often does ChatGPT recommend my GEO work?'
PROMPTS = ('U1', 'U2', 'O1', 'O2', 'M1', 'M2')
METRICS = ('mention', 'citation', 'recommendation')
EFFORTS = ('medium', 'high')
EXCLUDED_PUBLIC_DATA = re.compile(
    r'https?://(?:www\.)?(?:chatgpt\.com|grok\.com)/(?:c|s|share)/|'
    r'/Users/|127\.0\.0\.1|\blocalhost\b|[?&](?:utm_\w+|gclid|fbclid)=|'
    r'UI-202611\d{2}-B\d{3}|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}', re.I,
)


def read_jsonl(name):
    with (FOLDER / 'data' / name).open(encoding='utf-8') as handle:
        return [json.loads(line) for line in handle]


def page(filename, title, description, sections):
    navigation = ''.join(f'<a href="#{key}">{heading}</a>' for key, heading, _ in sections)
    content = ''.join(f'<section id="{key}"><h2>{heading}</h2>{body}</section>'
                      for key, heading, body in sections)
    alternate = ('<a href="technical-appendix.html">Methods and evidence</a>' if filename == 'index.html'
                 else '<a href="./">Return to the report</a>')
    document = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(description, quote=True)}">
<style>{CSS}{EXTRA}</style></head>
<body><a class="skip" href="#main">Skip to report</a><div class="layout">
<nav aria-label="GEO Lab 09 contents"><strong>On this page</strong><div class="nav-links">{navigation}</div>
<div class="nav-group">{alternate}<a href="measurement-kit-retest/">Supplement · Optimization and retest</a><a href="public-data.zip">Download redacted data</a></div></nav>
<main id="main"><p class="lesson-name">GEO Lab #09 · AI Visibility Baseline</p><h1>{escape(title)}</h1>
<p class="author">Helen Bird · Observed November 23–24, 2026 (Beijing time)</p>
{content}<p class="footer"><a href="../../learning-hub/">GEO Learning Hub</a> · <a href="https://github.com/helen-bird/geo-platform-observation">Repository</a></p></main>
</div></body></html>'''
    return finish_page(document, 9, 'reader' if filename == 'index.html' else 'appendix')


def hit_count(rows, metric):
    return sum(row['scores'][metric] for row in rows)


def additional_count(rows):
    return f"{sum(row['target_in_more'] == 1 for row in rows)}/{sum(row['panel_coverage'] == 'complete' for row in rows)}"


def reader(rows):
    n = len(rows)
    covered = [row for row in rows if row['panel_coverage'] == 'complete']
    surfaced = [row for row in covered if row['target_in_more'] == 1]
    outcomes = '<ul class="step-list">'
    outcomes += ''.join(f'<li><strong>{label} {hit_count(rows, metric)}/{n}.</strong> {explanation}</li>'
                        for metric, label, explanation in (
        ('mention', 'Mention', 'No answer identified Helen Bird, the project, or one of its resources in the final prose.'),
        ('citation', 'Observed citation', 'No recorded answer link, inline citation, or main source pointed to the target.'),
        ('recommendation', 'Recommendation', 'No answer explicitly advised readers to use, read or follow the target resources.'),
    ))
    outcomes += f'<li><strong>Additional sources {len(surfaced)}/{len(covered)}.</strong> Two of my research pages surfaced in the “More” list.</li></ul>'
    groups = [
        ('Information prompts', [r for r in rows if r['prompt_id'] in ('U1', 'O1', 'M1')]),
        ('Resource prompts', [r for r in rows if r['prompt_id'] in ('U2', 'O2', 'M2')]),
        *((effort.capitalize(), [r for r in rows if r['effort'] == effort]) for effort in EFFORTS),
    ]
    outcomes += table(['Group', 'Mention', 'Observed citation', 'Recommendation', 'More hits / full panels'],
                      [(group, *(f'{hit_count(subset, metric)}/{len(subset)}' for metric in METRICS),
                        additional_count(subset)) for group, subset in groups])
    outcomes += note('The “More” list is an additional observation. The citation count uses recordable answer links, inline citations and main sources. Thirty-five early answers lack a full panel and one answer displayed body links without a source panel.')
    prompts = json.loads((FOLDER / 'data/prompts.json').read_text())
    prompt_rows = []
    for question in prompts:
        group = [row for row in rows if row['prompt_id'] == question['id']]
        counts = []
        for effort in EFFORTS:
            cell = [r for r in group if r['effort'] == effort]
            counts.append(' / '.join(str(hit_count(cell, m)) for m in METRICS))
        prompt_rows.append((question['id'], escape(question['text']), *counts, additional_count(group)))
    design = '<p>Six fixed questions about understanding, improving and measuring GEO were each asked 15 times at Medium and High in fresh unpersonalized Temporary Chats. GPT-6 was the selected label. Search was automatic and explicitly visible in 150 answers. The remaining 30 search states are unknown.</p>'
    design += table(['Prompt', 'Question', 'Medium M / C / R (n = 15)', 'High M / C / R (n = 15)', 'More hits / full panels'], prompt_rows)
    design += note('Each cell has 15 answers, so the equal-cell rates match the pooled counts in this batch. An observed 0/15 has a Wilson 95% reference interval of 0–20.4%. Repeated answers can share search conditions and model state.')
    pages = Counter(urlsplit(url).path for row in surfaced for url in row['target_more_urls'])
    links = {
        '/geo-platform-observation/stages/04-creator-benchmark/technical-appendix.html':
            ('Lab #04 evidence appendix', '../../stages/04-creator-benchmark/technical-appendix.html'),
        '/geo-platform-observation/stages/06-content-optimization/':
            ('Lab #06 content optimization review', '../../stages/06-content-optimization/'),
    }
    sources = '<ul class="step-list">' + ''.join(
        f'<li><a href="{links[path][1]}">{links[path][0]}</a> appeared in {count} answers’ “More” lists.</li>'
        for path, count in pages.most_common()) + '</ul>'
    sources += '<p>One answer surfaced both pages. The two pages appeared under the measurement-method, evidence-backed guide and beginner-learning questions. Both stayed outside the visible cited and recommended content.</p>'
    m2 = [row for row in rows if row['prompt_id'] == 'M2']
    recs = Counter(resource for row in m2 for resource in row['resources_recommended'])
    mentioned = Counter(resource for row in m2 for resource in row['resources_mentioned'])
    measurement = f'<p>M2 asked for a free measurement guide or worksheet for a solo founder. My <a href="../../learning-hub/measurement/">Measurement Kit</a> was recommended in {hit_count(m2, "recommendation")}/{len(m2)} answers and surfaced in {additional_count(m2)} complete “More” lists. The answers frequently suggested other step-by-step guides and trackers.</p>'
    measurement += table(['Resource or provider', 'Mentioned', 'Recommended'],
                         [(escape(name), f'{mentioned[name]}/30', f'{count}/30')
                          for name, count in sorted(recs.items(), key=lambda entry: (-entry[1], entry[0]))[:7]])
    measurement += '<p><a href="measurement-kit-retest/">See how I used this shortlist to rebuild and retest the Measurement Kit.</a></p>'
    bounds = '<p>This batch gives a starting measurement for these exact six questions. It has no comparable prior week or controlled content change. Earlier experiments used other questions or collection conditions. The study records visible answers and sources, with no visibility into the model’s full retrieval or selection process.</p>'
    bounds += '<p><a href="technical-appendix.html">Read the scoring and coverage notes</a> · <a href="public-data.zip">Download the redacted evidence</a></p>'
    bounds += '<p><a href="../../learning-hub/measurement/#change">Set up your own repeat measurement</a> with an exact prompt, a saved baseline and a change record.</p>'
    return page('index.html', TITLE,
                'A 180-answer ChatGPT web baseline measuring GEO mentions, citations, recommendations, and appearances in additional sources.',
                [('findings', 'What appeared in the answers?', outcomes),
                 ('design', 'Six questions and two thinking levels', design),
                 ('sources', 'Which of my pages surfaced?', sources),
                 ('alternatives', 'What did ChatGPT recommend instead?', measurement),
                 ('limits', 'What can be compared later?', bounds)])


def appendix(rows, attempts):
    coverage = Counter(row['panel_coverage'] for row in rows)
    counts = '<p>180 selected answers, 182 formal submissions and two retained source-capture failures. Each failed planned position has one fresh same-condition replacement. The 12-answer pilot is outside the formal denominator. The first 39 selected positions rely on collection records for the selected settings. Later records retain direct settings evidence. GPT-6 identifies the web selector label.</p>'
    rules = '<ul class="step-list"><li><strong>Mention.</strong> Identify the author, project or uniquely attributable asset in final prose.</li><li><strong>Citation.</strong> Match saved answer links, inline citation cards and main sources to the confirmed owned routes.</li><li><strong>Recommendation.</strong> Require explicit advice to use, read, follow or refer to an attributable target asset.</li><li><strong>Additional sources.</strong> Count an approved target URL in the separately labelled “More” list, once per answer. Missing coverage stays unknown.</li></ul>'
    rules += note('Recurring alternatives were coded from answer context and verified against verbatim evidence before URL cleanup. Lists include selected relevant resources and tools. Some answers recommend multiple resources.')
    rules += '<p>An AI agent coded the answers and checked the surrounding text and links for ten potentially ambiguous target references. The project owner authorized release of this edition. The scoring record identifies the agent as the reviewer.</p>'
    sources = table(['Coverage group', 'Answers', 'What was observable'],
                    [('Complete panel', coverage['complete'], 'Main and “More” sources preserved.'),
                     ('Earlier inline evidence', coverage['not_preserved'], 'Body and inline sources preserved. Full panel unknown.'),
                     ('Panel not displayed', coverage['not_exposed'], 'Completed answer with four body links and no “View Sources” control.')])
    sources += '<p>Ten answers contain attributable links in their additional source lists. Their public observation IDs and target URLs are listed here.</p>'
    sources += table(['Answer', 'Prompt / effort', 'Additional target links'],
                     [(row['id'], f'{row["prompt_id"]} / {row["effort"]}',
                       '<br>'.join(f'<a href="{escape(url, quote=True)}">{escape(urlsplit(url).path.rsplit("/", 2)[-2] if url.endswith("/") else urlsplit(url).path.rsplit("/", 1)[-1])}</a>' for url in row['target_more_urls']))
                      for row in rows if row['target_in_more'] == 1])
    sources += note('The overall 0/180 citation count uses recorded evidence. A sensitivity view restricted to 144 full panels also has zero observed primary citations. The broader visibility count is 10/144, or 6.9% (Wilson 95% reference interval 3.8%–12.3%). The complete-panel subset is defined by evidence availability.')
    data = '<p>The download includes 180 redacted answer texts, the six frozen prompts, answer-level codes and a manifest of 182 attempts. It omits private session URLs, UI or account metadata, raw browser captures and failed answer bodies. Public IDs follow planned positions. Source links have tracking and other nonessential URL parameters removed.</p>'
    data += '<p><a href="data/observations.jsonl">Answer-level observations</a> · <a href="data/attempts.jsonl">Attempt manifest</a> · <a href="data/prompts.json">Exact prompts</a> · <a href="public-data.zip">Redacted answer archive</a></p>'
    return page('technical-appendix.html', 'GEO Lab #09: AI Visibility Methods and Evidence',
                'Scoring definitions, evidence coverage, failures and redacted answers for the one-time ChatGPT web baseline.',
                [('sample', 'Sample and attempts', counts), ('coding', 'Scoring rules', rules),
                 ('coverage', 'Source panel coverage', sources), ('data', 'Data and reproduction', data)])


def load_and_check():
    rows = read_jsonl('observations.jsonl')
    attempts = read_jsonl('attempts.jsonl')
    assert len(rows) == 180 and len({r['id'] for r in rows}) == 180 and len(attempts) == 182
    assert {r['id'] for r in rows} == {r['id'] for r in attempts if r['selected']}
    assert Counter((r['prompt_id'], r['effort']) for r in rows) == {
        (prompt, effort): 15 for prompt in PROMPTS for effort in EFFORTS}
    assert all(hit_count(rows, metric) == 0 for metric in METRICS)
    assert Counter(row['panel_coverage'] for row in rows) == {
        'complete': 144, 'not_preserved': 35, 'not_exposed': 1}
    assert additional_count(rows) == '10/144'
    assert Counter(row['search_evidence'] for row in rows) == {'yes': 150, 'unknown': 30}
    assert all((r['target_in_more'] == 'UNKNOWN') == (r['panel_coverage'] != 'complete') for r in rows)
    with ZipFile(FOLDER / 'public-data.zip') as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {f'data/{name}' for name in (
            'attempts.jsonl', 'observations.jsonl', 'prompts.json', 'redacted-answers.jsonl')}
        for name in archive.namelist():
            assert not EXCLUDED_PUBLIC_DATA.search(archive.read(name).decode('utf-8')), name
        for name in ('attempts.jsonl', 'observations.jsonl', 'prompts.json'):
            assert archive.read('data/' + name) == (FOLDER / 'data' / name).read_bytes()
        answers = [json.loads(line) for line in archive.read('data/redacted-answers.jsonl').splitlines()]
        assert {r['id'] for r in answers} == {r['id'] for r in rows}
        assert len(answers) == 180 and all(r['answer_redacted'] for r in answers)
        assert all(set(row) == {'id', 'answer_redacted', 'observed_primary_links', 'resource_evidence'}
                   for row in answers)
    return rows, attempts


def main():
    rows, attempts = load_and_check()
    (FOLDER / 'index.html').write_text(reader(rows), encoding='utf-8')
    (FOLDER / 'technical-appendix.html').write_text(appendix(rows, attempts), encoding='utf-8')
    print('Visibility baseline built from 180 answers and 182 attempts.')


if __name__ == '__main__':
    main()
