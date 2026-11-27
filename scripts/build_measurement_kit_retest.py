#!/usr/bin/env python3
"""Rebuild the Lab #09 supplement from its reviewed public evidence."""
from collections import Counter
from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
from zipfile import ZipFile

from build_learning_hub import CSS
from build_stage5_report import EXTRA, note, table
from build_visibility_baseline import EXCLUDED_PUBLIC_DATA
from report_series import finish_page
from site_metadata import supplements

ROOT = Path(__file__).resolve().parents[1]
ROUTE = 'stages/09-visibility-baseline/measurement-kit-retest/'
FOLDER = ROOT / ROUTE
TITLE = 'GEO Lab #09 Supplement: From 0 to 16 Recommendations'
GUIDE = '../../../learning-hub/measurement/'
REPOSITORY = 'https://github.com/helen-bird/geo-platform-observation'

# These labels match the published baseline coding. The last column describes
# the resource examined on November 24 and the change it suggested for the kit.
BENCHMARKS = (
    ('Diego Navarro', 'AI Visibility Tracker', 'https://diegonavarrocr.com/tools/ai-visibility-tracker/',
     'The public generator produces editable questions and a CSV. I added ready-to-copy questions and a browser-only question builder.'),
    ('Apollo Digital', 'Free GEO Course', 'https://apollodigital.io/learn/geo/',
     'The course connects lessons, examples and templates. I linked the first measurement steps to examples and published methods.'),
    ('Digital6ix', 'GEO Tracker', 'https://www.digital6ix.ca/templates/geo-ai-visibility-tracker/',
     'The workbook is previewable and includes a recurring dashboard. I added a preview, a blank workbook and results by round.'),
    ('Semantic Frame', 'Three-step GEO measurement', 'https://www.semanticframe.ai/en/resources/how-to-do-geo',
     'The guide specifies questions, assistants, repetitions and a worksheet. I added a short first-run procedure and separated eligible answers from planned rows.'),
    ('Nakama', 'AI Visibility Report Template', 'https://www.nakama.in/journal/ai-visibility-report-template',
     'The template connects a SaaS question library, evidence and decisions. I added a structured change log and two follow-up rounds.'),
    ('Catch AI', 'HeyCatch guides on free AI visibility tracking', 'https://heycatch.ai/blog/how-to-track-ai-visibility-metrics-on-a-0-budget',
     'The guides distinguish an initial check from recurring tracking. I made the solo-founder audience, the free download and the starting steps explicit.'),
    ('Geonauts', 'Free GEO Audit Template', 'https://geonauts.ai/blog/free-geo-audit-template/',
     'The guide links answer checks to technical and source checks and offers a CSV. I added a table that connects each observed result to a diagnostic step.'),
)


def load():
    def jsonl(path):
        return [json.loads(line) for line in path.read_text().splitlines()]

    baseline = [row for row in jsonl(FOLDER.parent / 'data/observations.jsonl') if row['prompt_id'] == 'M2']
    retest = jsonl(FOLDER / 'data/observations.jsonl')
    attempts = jsonl(FOLDER / 'data/attempts.jsonl')
    prompt = json.loads((FOLDER / 'data/prompts.json').read_text())[0]
    baseline_prompts = json.loads((FOLDER.parent / 'data/prompts.json').read_text())
    timing = json.loads((FOLDER / 'data/timing.json').read_text())
    assert prompt == {'id': 'M2', 'text': next(p['text'] for p in baseline_prompts if p['id'] == 'M2')}
    assert Counter(row['effort'] for row in baseline) == Counter(row['effort'] for row in retest) == {'medium': 15, 'high': 15}
    assert all(row['prompt_id'] == 'M2' for row in retest)
    assert all(sum(row['scores'].values()) == 0 for row in baseline)
    assert len(attempts) == len(retest) == 30 and all(row['selected'] for row in attempts)
    ids = [row['id'] for row in retest]
    assert len(set(ids)) == 30 and ids == [row['id'] for row in attempts]
    assert sum(row['scores']['recommendation'] for row in retest) == 16
    assert Counter(row['panel_coverage'] for row in retest) == {'complete': 16, 'partially_expanded': 7, 'not_available': 7}
    assert Counter(row['target_in_more'] for row in retest) == {'yes': 14, 'no': 9, 'unknown': 7}
    with ZipFile(FOLDER / 'public-data.zip') as archive:
        assert archive.testzip() is None
        for name in ('observations.jsonl', 'attempts.jsonl', 'prompts.json', 'timing.json'):
            assert archive.read('data/' + name) == (FOLDER / 'data' / name).read_bytes()
        assert len(archive.namelist()) == 5
        for name in archive.namelist():
            assert not EXCLUDED_PUBLIC_DATA.search(archive.read(name).decode()), name
        answers = [json.loads(line) for line in archive.read('data/redacted-answers.jsonl').decode().splitlines()]
    assert [row['id'] for row in answers] == ids
    assert all(a['answer_redacted'] and set(a) == {'id', 'answer_redacted', 'recommendation_excerpt',
                                                  'body_links', 'main_source_links', 'more_source_links'} for a in answers)
    assert all(bool(a['recommendation_excerpt']) == bool(r['scores']['recommendation']) for a, r in zip(answers, retest))
    return baseline, retest, answers, prompt['text'], timing


def page(title, description, sections, record, kind):
    nav = ''.join(f'<a href="#{key}">{escape(heading)}</a>' for key, heading, _ in sections)
    content = ''.join(f'<section id="{key}"><h2>{escape(heading)}</h2>{body}</section>'
                      for key, heading, body in sections)
    other = ('<a href="technical-appendix.html">Methods and evidence</a>' if kind == 'reader'
             else '<a href="./">Return to the supplement</a>')
    document = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(description, quote=True)}">
<style>{CSS}{EXTRA}</style></head><body><a class="skip" href="#main">Skip to report</a><div class="layout">
<nav aria-label="Lab 09 supplement contents"><strong>On this page</strong><div class="nav-links">{nav}</div>
<div class="nav-group">{other}<a href="../">Original Lab #09 baseline</a><a href="public-data.zip">Download redacted data</a></div></nav>
<main id="main"><p class="lesson-name">GEO Lab #09 · Supplement</p><h1>{escape(title)}</h1>
<p class="author">Helen Bird · First retest on November 27, 2026 (Beijing time)</p>
{content}<p class="footer"><a href="../../../learning-hub/">GEO Learning Hub</a> · <a href="{REPOSITORY}">Repository</a></p>
</main></div></body></html>'''
    return finish_page(document, 9, kind, supplement=record)


def reader(baseline, retest, answers, prompt, timing, record):
    n = len(retest)
    recs = lambda batch: sum(row['scores']['recommendation'] for row in batch)
    lift = recs(retest) / n - recs(baseline) / len(baseline)
    findings = f'''<p class="lead">I rebuilt my free GEO measurement guide and worksheet after benchmarking the resources ChatGPT recommended for the same solo-founder question. Three days after release, ChatGPT recommended my kit in <strong>{recs(retest)}/{n} answers ({lift:.1%})</strong>, up from <strong>0/30</strong>.</p>
<ul class="step-list"><li><strong>The leading alternatives made it easy to start.</strong> They offered an editable prompt set, a worksheet or a clear sequence of steps.</li>
<li><strong>I rebuilt the guide and the workbook together.</strong> I also added author and evidence links and included the guide in the sitemap.</li>
<li><strong>Both thinking levels recommended the kit after release.</strong> All 16 recommendations linked to the guide or worksheet in the answer body.</li></ul>'''
    findings += note('One before-and-after comparison measures a change in this batch. It cannot isolate the contribution of any edit or rule out changes in the search environment.')
    design = '<p>All 30 baseline answers and 30 first-retest answers used the same M2 question.</p>' + note(escape(prompt))
    design += '<p>The baseline public data gave me two things: zero recommendations for my kit and a shortlist of alternatives to try. I counted a resource once per answer, read the reasons ChatGPT gave, opened the linked pages and tested the public files or workflows where I could.</p>'
    design += '<p><a href="../#alternatives">Inspect the original recommendations</a> · <a href="../public-data.zip">Download the original 180-answer baseline</a></p>'
    counts = Counter(name for row in baseline for name in row['resources_recommended'])
    competitor = table(['Recommended resource', 'Baseline', 'What I checked and used'], [
        (f'<a href="{escape(url, quote=True)}">{escape(label)}</a>', f'{counts[name]}/30', escape(observation))
        for name, label, url, observation in BENCHMARKS
    ])
    competitor += note('The audit used pages and files available on November 24. Counts refer to resources or resource families, and an answer can recommend several. The linked HeyCatch article is one of three guides in its five-answer family count. The audit documents capabilities and answers’ stated reasons for recommending a resource. It cannot observe the retrieval or selection mechanism.')
    competitor += '<p>My v1 kit already distinguished failures and unknown outcomes. The larger gaps were getting started and turning the first run into a comparable follow-up. I kept the measurement rules and used the <a href="../../../stages/06-content-optimization/">Lab #06 evidence review</a> to prioritize task relevance, useful specifics and inspectable evidence.</p>'
    actions = table(['Gap', 'What changed in v2.0', 'How to inspect it'], [
        ('Unclear audience and first step', 'Made “free GEO visibility measurement guide and worksheet for solo founders” explicit. Added a quick start, a workbook preview and a download without a sign-in.', f'<a href="{GUIDE}#start">First measurement</a>'),
        ('No ready-to-use question library', 'Added six copyable starters, CSV download and a browser-only question builder. Marked which questions are for natural discovery and which name a product.', f'<a href="{GUIDE}#choose">Question starters</a>'),
        ('Hard to compare repeats', 'Rebuilt the workbook for a baseline and two follow-ups. It stores planned slots, complete and failed attempts, source roles and competitors. A comparison checks matching conditions and eligible denominators.', f'<a href="{GUIDE}ai-recommendation-measurement.xlsx">Download Excel</a>'),
        ('Weak path from a result to a decision', 'Added a checklist for cases such as missing source evidence, a More-only hit, a citation without a recommendation, or a recommendation with no verified referral.', f'<a href="{GUIDE}#diagnose-results">Diagnostic checklist</a>'),
        ('Useful evidence was hard to find', 'Added a walkthrough of the 0/30 baseline, a 15-answer recount, links to saved source evidence, and a short FAQ about interpreting results.', f'<a href="{GUIDE}#reproduce-a-result">Recount the example</a>'),
        ('Author and guide were loosely connected', 'Linked the byline to the Learning Hub author section, linked the kit from relevant research pages, documented the version, and added the guide to the sitemap. Adjusted the search title and description after live inspection.', '<a href="../../../learning-hub/#helen-bird">Author and research</a> · <a href="../../../sitemap.xml">Sitemap</a>'),
    ])
    actions += f'<p><a href="{REPOSITORY}/tree/15b222bddb55255ca67cc9409e126834450fb029/learning-hub/measurement">Inspect v1</a> · <a href="{REPOSITORY}/commit/{timing["kit_release_commit"]}">v2.0 release</a> · <a href="{REPOSITORY}/commit/{timing["metadata_commit"]}">Search-metadata release</a></p>'
    timeline = table(['Beijing time', 'What happened'], [
        ('November 23–24', 'Collected the 30 M2 baseline answers and audited the recommended competitor resources.'),
        ('November 24, 20:04', 'Published the v2.0 guide and workbook at their existing URLs. Google and Bing live tests fetched the new page.'),
        ('November 24, 20:24', 'Deployed the final search-title and description edits. Google’s retained crawl later that evening contained v2.0.'),
        ('November 27, 20:39', 'An unpersonalized ChatGPT Search session found the canonical guide and identified v2.0 given only its exact title. Bing Webmaster Tools still showed discovered and not crawled.'),
        ('November 27, 20:57–21:36', 'Ran the original M2 prompt 30 times, beginning about 3 days and 53 minutes after the v2.0 deployment.'),
    ]) + note('The exact-title check established that the new guide could be retrieved under that query. The formal retest supplied only the original M2 question in each fresh temporary chat. It used GPT-6 with 15 Medium and 15 High responses and let the interface decide when to search.')
    cohorts = [('All answers', baseline, retest)]
    cohorts += [(effort.capitalize(), [r for r in baseline if r['effort'] == effort], [r for r in retest if r['effort'] == effort]) for effort in ('medium', 'high')]
    results = table(['Recommendation', 'Before', 'First retest'], [
        (label, f'{recs(before)}/{len(before)}', f'<strong>{recs(after)}/{len(after)} ({recs(after)/len(after):.1%})</strong>')
        for label, before, after in cohorts
    ])
    for sample_id in ('T2-06', 'T2-07'):
        sample = next(row for row in answers if row['id'] == sample_id)
        results += note(f'<strong>{sample_id}.</strong> {escape(sample["recommendation_excerpt"])}')
    results += '<p>The kit was presented as a starting point or as one component of a workflow. Answers pointed to the solo-founder fit, the free Excel worksheet and the difference between mentions, citations and recommendations.</p>'
    repeat = '''<ol class="step-list"><li>Freeze one question and the target you will count. Save the full answers and score recommendations separately from links.</li>
<li>Open the resources the answers actually recommend. Walk through a first use and record the gaps you can fix in your own product.</li>
<li>Ship a dated release with a frozen before version. Use a separate title-only search to verify the new content is discoverable.</li>
<li>Repeat the unchanged natural question using the original settings. Keep the results and repeat in a later window to check persistence.</li></ol>'''
    repeat += note('The second retest is pending. Publication of this supplement and its internal links is a later site change. Future comparisons should record it and distinguish recommendations of the exact kit from recommendations of this report.')
    repeat += '<p><a href="technical-appendix.html">Methods and answer-level evidence</a> · <a href="public-data.zip">Download the 30 redacted answers</a></p>'
    return page(TITLE, 'How Helen Bird benchmarked GEO resources, rebuilt a free measurement kit, and retested the same ChatGPT question three days after release.', [
        ('findings', 'What changed in the answers?', findings), ('prompt', 'The original question', design),
        ('benchmark', 'What the recommended resources did well', competitor), ('changes', 'What I changed', actions),
        ('timeline', 'When I retested', timeline), ('results', 'First retest results', results),
        ('reuse', 'How to run the same kind of check', repeat),
    ], record, 'reader')


def appendix(baseline, retest, prompt, timing, record):
    protocol = note(escape(prompt)) + '<p>ChatGPT web, GPT-6 selected in the interface. Medium and High each had 15 fresh, unpersonalized Temporary Chats, a single identical message and default automatic search. Backend routing was unverified. Thirty submitted answers completed. Pre-submission navigation and sign-in interruptions were resolved without submitting an extra question.</p>'
    time_data = json.dumps(timing)
    assert not EXCLUDED_PUBLIC_DATA.search(time_data)
    protocol += '<p><a href="data/timing.json">Release and collection timestamps</a> · <a href="data/prompts.json">Exact prompt</a> · <a href="data/attempts.jsonl">Attempt manifest</a></p>'
    rules = '<ul class="step-list"><li><strong>Mention.</strong> The final prose identifies Helen Bird, GEO Learning Log or a confirmed resource from the project.</li><li><strong>Observed citation.</strong> A visible answer link, inline citation or main source points to a verified target URL.</li><li><strong>Recommendation.</strong> The answer explicitly suggests the guide, worksheet or an attributable target resource for the task. A supplemental source link alone does not qualify.</li><li><strong>More.</strong> Positives may be verified in a partial panel. A negative requires the complete list. These links are outside the primary citation count.</li></ul>'
    rules += note('An AI agent reviewed context and links. A reply recommending several resources can qualify for each. This release does not include measured traffic or a new cross-engine test.')
    counts = []
    for name in ('mention', 'citation', 'recommendation'):
        counts.append((name.capitalize(), *(f'{sum(r["scores"][name] for r in batch)}/{len(batch)}' for batch in (baseline, retest))))
    counts.extend((('More · complete panels only', '0/23', '7/16'), ('Web search observed', '23/30', '24/30')))
    coverage = table(['Metric', 'Baseline M2', 'First retest'], counts)
    coverage += note('The retest had 16 full More panels, seven partially expanded panels and seven unavailable. Across all 30 answers, 14 have a verified target URL in More, nine have no target in a complete panel and seven are unknown. Six answers had insufficient evidence of actual search. Keep these evidence limits when interpreting zeroes.')
    public_data = '<p>The archive includes 30 redacted answers, separate lists of body, main-source and More links, recommendation excerpts, the prompt, timing and coded observations. The fields use public answer IDs. Private conversation addresses, account and browser metadata, raw interface captures, Search Console account evidence, tracking parameters and credentials are excluded.</p>'
    public_data += '<p><a href="public-data.zip">Download redacted answers</a> · <a href="data/observations.jsonl">Answer-level observations</a> · <a href="../technical-appendix.html">Original baseline methods</a></p><p>To reproduce the reader and appendix, run <code>python3 scripts/build_measurement_kit_retest.py</code> from the repository root.</p>'
    return page('GEO Lab #09 Supplement: Retest Methods and Evidence', 'The M2 prompt, measurement settings, scoring and redacted first-retest evidence for the GEO Measurement Kit study.', [
        ('protocol', 'Prompt and protocol', protocol), ('coding', 'Scoring rules', rules), ('coverage', 'Coverage and denominators', coverage),
        ('data', 'Data and reproduction', public_data),
    ], record, 'appendix')


def main():
    record = next(r for r in supplements() if r['path'] == ROUTE + 'index.html')
    baseline, retest, answers, prompt, timing = load()
    (FOLDER / 'index.html').write_text(reader(baseline, retest, answers, prompt, timing, record))
    (FOLDER / 'technical-appendix.html').write_text(appendix(baseline, retest, prompt, timing, record))
    print('Lab #09 supplement rebuilt from 30 baseline and 30 retest observations.')


if __name__ == '__main__':
    main()
