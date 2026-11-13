#!/usr/bin/env python3
"""Recompute the public Part 2 results and render the report and appendix."""
from html import escape
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from build_interim_review import ROOT, page
from build_stage5_report import note, table
from prompt_framing_stats import ENVS, FRAMES, summarize
from report_series import INTERIM_PART2_READER

ROUTE = INTERIM_PART2_READER.removesuffix('/index.html')
FOLDER = ROOT / ROUTE
DATA = FOLDER / 'data'
META = json.loads((FOLDER / 'record.json').read_text())
PRIVATE_EVIDENCE = re.compile(
    r'https?://(?:www\.)?(?:chatgpt\.com/(?:c|s|share)/|grok\.com/(?:c|share)/|claude\.ai/chat/)'
    r'|https?://(?:docs\.google\.com|drive\.google\.com)/|https?://[^/\s<>"\x27]+@'
    r'|file://|/var/folders/|/Users/|\blocalhost\b|127\.0\.0\.1'
    r'|\b(?:resp|req|ws|msg|rs)_[A-Za-z0-9_-]{12,}\b'
    r'|\b(?:sk-(?:proj-)?|gh[pousr]_)[A-Za-z0-9_-]{20,}'
    r'|Bearer [A-Za-z0-9._-]{16,}|[\w.-]+@[\w.-]+\.[A-Za-z]{2,}'
    r'|[?&](?:utm_\w+|gclid|fbclid|token|api_key|session_id|signature|x-(?:amz|goog)-[^=]+)=',
    re.I,
)
ENV_LABELS = {'chatgpt-web': 'ChatGPT web', 'grok-web': 'Grok Expert'}
FRAME_LABELS = {'discovery': 'Discovery', 'recommendation': 'Explicit recommendation', 'evidence': 'Original experiments'}


def read_lines(name):
    return [json.loads(line) for line in (DATA / name).read_text().splitlines() if line]


def rate(item, interval=False):
    value = f"{item['k']}/{item['n']}" if item['n'] else 'N/A'
    if interval and item['n']:
        lo, hi = item['wilson_95']
        value += f" [{lo:.0%}–{hi:.0%}]"
    return value


def comparison(a, b, key, interval=False):
    return ' → '.join(rate(row[key], interval) for row in (a, b))


def render(filename, title, description, sections, utility):
    return page(filename, title, description, sections, utility, route=ROUTE, metadata=META)


def cell(summary, env, frame, target):
    return summary['cells'][f'{env}/{frame}/{target}']


def prompts_table():
    conditions = json.loads((DATA / 'conditions.json').read_text())
    def prompt(frame, target):
        full = conditions['prompts'][f'{frame}-{target}']['prompt']
        return escape(full.removesuffix(' Explain why and cite sources when available.'))
    return table(['Frame', 'Resource prompt', 'Creator prompt'], [
        [FRAME_LABELS[frame], prompt(frame, 'resource'), prompt(frame, 'creator')]
        for frame in FRAMES
    ])


def reader(summary):
    expectations = '''<p>Part 1 found that Grok recommended The GEO Lab in 15/15 answers to a free-resource prompt and named its author in 0/15. We expected creator prompts to make names more visible. We also tested whether asking for original, reproducible experiments changes who gets selected.</p><p><a href="../historical-replication/">Part 1 · Historical replication</a></p>'''
    methods = '''<p>We tested six fixed English prompts in ten blocks on ChatGPT web (GPT-5.6 Sol, Medium) and Grok Expert. Each prompt had ten answers per environment. Both used native web search in fresh chats. ChatGPT used Temporary Chat and Grok used ordinary chats with both personalization controls off.</p>'''
    methods += prompts_table()
    methods += '''<p>Each prompt ended with “Explain why and cite sources when available.” The first two resource questions share the practical tutorial goal. The third asks for a different kind of evidence. The 300 Part 1 answers provide historical context for this separate 120-answer panel.</p>'''

    conclusions = '''<ul>
<li><strong>All 60 creator-prompt answers recommended a person.</strong> All 60 resource-prompt answers directed their recommendations toward resources. Those answers could still name authors, especially when discussing papers.</li>
<li><strong>The same site can be recommended with or without its author.</strong> Grok recommended The GEO Lab in 10/10 answers for each of the two evidence prompts. Artur Ferreira was named in 4/10 resource answers and 10/10 creator answers.</li>
<li><strong>The evidence requirement changes the shortlist.</strong> ChatGPT recommended Aleyda Solis and Kevin Indig in 10/10 answers each under the explicit tutorial recommendation prompt. Each appeared as a personal recommendation in 1/10 under the original-experiments creator prompt.</li></ul>'''
    conclusions += '<h3>What changed when we kept asking for resources?</h3>'
    resource_rows = []
    for env in ENVS:
        for frame in FRAMES:
            info = cell(summary, env, frame, 'resource')['focal_examples']['Artur Ferreira']
            resource_rows.append([ENV_LABELS[env], FRAME_LABELS[frame],
                                  rate(info['resource_family_recommended']), rate(info['person_named'])])
    conclusions += table(['Environment', 'Resource framing', 'The GEO Lab or its works recommended', 'Artur named'], resource_rows)
    conclusions += '''<p>Grok's original-experiments resource question surfaced both the site and its author more often than either tutorial resource question. The two tutorial versions differed in site recommendation frequency and neither named Artur in these ten runs.</p>
<figure><img src="creator-naming.png" alt="Any-name rates and average distinct names per answer for each resource and creator prompt"><figcaption>Answer-level naming rates with 95% Wilson intervals and average names per answer.</figcaption></figure>
<h3>Helen Bird and the GEO Learning Hub</h3>
<p>The original-experiments creator prompt named Helen Bird in 3/10 ChatGPT and 8/10 Grok answers. Personal recommendations were 3/10 and 7/10. The question supplied neither her name nor a URL. All three recommending ChatGPT answers linked the <a href="../../../learning-hub/">GEO Learning Hub</a> in the body. All seven recommending Grok answers included the hub in their visible source panel. In one Grok trace, broad topic queries preceded a browse of the site and a subsequent search using Helen Bird's name.</p>
<figure><img src="resource-overlap.png" alt="Median recommended-resource overlap for repeat prompts and resource-to-creator comparisons"><figcaption>Median resource overlap was 11.8%–40.0% within the same prompt and 2.9%–22.5% after switching the target within a block.</figcaption></figure>'''
    conclusions += note('These results describe the observed questions and collection window. Which page or byline caused an individual recommendation remains unknown. The two interfaces expose different citation evidence.')
    conclusions += '<p><a href="technical-appendix.html">Read the full methods, per-condition results and public evidence.</a></p>'
    return render('index.html', 'How does question framing change AI recommendations?',
                  'A 120-answer ChatGPT and Grok experiment on resource framing, creator visibility and public source evidence.',
                  [('hypotheses', '1. What did we expect?', expectations),
                   ('validation', '2. How did we test it?', methods),
                   ('conclusions', '3. What did we find?', conclusions)],
                  '<a href="technical-appendix.html">Methods and evidence</a> <a href="../../../learning-hub/review-evidence/#part-2">Find original answers</a>')


def appendix(summary):
    methods = '''<p>Collection ran from November 10 at 23:23 to November 11 at 03:13, 2026, Beijing time. All 120 submitted questions produced analyzable bodies. Grok's minimum observed submission interval was 181.059 seconds. Twenty-four same-prompt cross-environment pairs reversed the planned lead. Block matching uses the planned block and actual timestamps.</p>
<p>Codex semantically coded the full bodies by frame, with a review of evidence excerpts and focal cases. The corpus has one primary coding pass per frame. A name in substantive answer text counts as a mention. Direct personal recommendation requires an affirmative selection of that person. Author naming and explicit, verified attribution are recorded separately. First-party pages verify 432 of 897 recommended resource instances. The other instances have unknown personal attribution.</p>
<p>Binary intervals use the Wilson 95% formula with answers as units. Resource-instance fractions and block contrasts are descriptive. Jaccard overlap is intersection size divided by union size. Each same-prompt comparison uses the 45 pairs of its ten answers. Each different-prompt comparison uses ten same-block pairs. Link comparisons require observable sets on both sides.</p>'''
    methods += note('One Grok evidence-resource snapshot missed its final word. The expanded capture from that session supplied an exact matching body and the trailing word. The public row includes the recovered text and marks the repair. The answer interpreted GEO in several senses. Only generative-engine optimization resource recommendations enter the primary count.')

    target_rows, conditional_rows = [], []
    for env in ENVS:
        for frame in FRAMES:
            a, b = [cell(summary, env, frame, t) for t in ('resource', 'creator')]
            target_rows.append([ENV_LABELS[env], FRAME_LABELS[frame],
                                comparison(a['rates'], b['rates'], 'any_person_named', True),
                                comparison(a['rates'], b['rates'], 'any_person_recommended'),
                                ' → '.join(f"{row['counts']['resources']['mean']:.1f}" for row in (a, b))])
            shared = summary['target_contrasts'][f'{env}/{frame}']['shared_verified_recommendations']
            n = len(shared)
            paired = ' → '.join(f"{sum(x[side + '_author_named'] for x in shared)}/{n}"
                               for side in ('left', 'right')) if n else 'N/A'
            conditional_rows.append([ENV_LABELS[env], FRAME_LABELS[frame],
                                     comparison(a, b, 'conditional_any_author_named', True), paired])
    results = '<p>Each row switches from a resource prompt to a creator prompt. Brackets show Wilson intervals.</p>'
    results += table(['Environment', 'Frame', 'Any name', 'Any personal recommendation', 'Mean resources'], target_rows)
    results += table(['Environment', 'Frame', 'Any recommended resource author named', 'Shared verified resource instances with author named'], conditional_rows)
    results += '''<h3>Resource lists across frames</h3><p>These are median overlaps within each platform and target, paired by block.</p>'''
    keys = ('discovery-recommendation', 'discovery-evidence', 'recommendation-evidence')
    results += table(['Environment', 'Target', 'Discovery vs. recommendation', 'Discovery vs. evidence', 'Recommendation vs. evidence'], [
        [ENV_LABELS[env], target.title(), *[
            f"{summary['frame_contrasts'][f'{env}/{target}/{key}']['matched_overlap']['resources']['median']:.1%}"
            for key in keys]]
        for env in ENVS for target in ('resource', 'creator')
    ])

    sources = '''<p>Observable answer URLs appeared in 60/60 ChatGPT and 4/60 Grok answers. The conservative identifiable source-URL subset was 47/60 and 1/60. ChatGPT grouped citations were not expanded. Grok exposed a source panel in all 60 runs, with a median of 72 normalized URLs. Panel candidates and page visits have separate fields. Only one matched cross-platform answer pair had identifiable source URLs on both sides.</p>
<p>To inspect the open-ended search path, locate <code>IR2-GROK-WEB-EVIDENCE-CREATOR-B03-A01</code> in the answer file. Compare the generic search terms, site visit and follow-up query with the displayed answer. <code>IR2-CHATGPT-WEB-EVIDENCE-CREATOR-B08-A01</code> includes both the hub and GitHub as body links.</p>'''
    files = '''<ul><li><a href="data/conditions.json">Original prompts, settings and collection summary</a></li>
<li><a href="data/answers.jsonl">120 redacted answer bodies, body links and visible search evidence</a></li>
<li><a href="data/attempts.jsonl">120 attempt histories</a></li>
<li><a href="data/measurements.jsonl">Normalized coding, counts and supporting excerpts</a></li>
<li><a href="data/entity-registry.json">Entity aliases and first-party authorship checks</a></li>
<li><a href="data/summary.json">Recomputed metrics and block comparisons</a> · <a href="public-data.zip">Download data archive</a></li></ul>
<p>Rebuild offline with <code>python3 scripts/build_prompt_framing.py</code> from the repository root. Cite a GitHub commit permalink and the relevant answer ID for a fixed record.</p>'''
    files += note('The public export removes private links, credentials, local paths, opaque identifiers, tracking parameters and unrelated same-name search hits. It retains aggregate source-domain sets used by the calculations and omits source-panel previews. The curated URL list can be shorter than the original visible source panel.')
    return render('technical-appendix.html', 'Question framing methods and evidence',
                  'Public methods and evidence for the 120-answer GEO Lab question-framing experiment.',
                  [('method', 'Methods and collection', methods), ('results', 'Per-condition results', results),
                   ('sources', 'Search and source evidence', sources), ('data', 'Data and reproduction', files)],
                  '<a href="./">Return to the report</a>')


def check_inputs(measurements, summary):
    answers, attempts = read_lines('answers.jsonl'), read_lines('attempts.jsonl')
    ids = {r['answer_id'] for r in answers}
    assert len(ids) == len(answers) == len(attempts) == len(measurements) == 120
    assert ids == {r['answer_id'] for r in measurements} == {r['attempt_id'] for r in attempts}
    assert all(r['answer_text'].strip() for r in answers)
    assert sum(r['body_suffix_recovered_from_same_session'] for r in answers) == 1
    for row in attempts:
        events = [event['event'] for event in row['events']]
        assert events.count('SUBMITTED') == events.count('COMPLETE_BODY_CAPTURED') == 1
    assert all(c['answers'] == 10 for c in summary['cells'].values())
    assert all(c['binary']['any_person_recommended']['change_pp'] == 100 for c in summary['target_contrasts'].values())


def main():
    measurements = read_lines('measurements.jsonl')
    summary = summarize(measurements)
    check_inputs(measurements, summary)
    (DATA / 'summary.json').write_text(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + '\n')
    (FOLDER / 'index.html').write_text(reader(summary))
    (FOLDER / 'technical-appendix.html').write_text(appendix(summary))
    with ZipFile(FOLDER / 'public-data.zip', 'w') as archive:
        for path in sorted(DATA.iterdir()):
            archive.writestr(ZipInfo(path.relative_to(FOLDER).as_posix()), path.read_bytes(), compress_type=ZIP_DEFLATED)


def check():
    measurements = read_lines('measurements.jsonl')
    summary = summarize(measurements)
    check_inputs(measurements, summary)
    assert summary == json.loads((DATA / 'summary.json').read_text())
    assert reader(summary) == (FOLDER / 'index.html').read_text()
    assert appendix(summary) == (FOLDER / 'technical-appendix.html').read_text()
    with ZipFile(FOLDER / 'public-data.zip') as archive:
        expected = {p.relative_to(FOLDER).as_posix() for p in DATA.iterdir()}
        assert archive.testzip() is None and set(archive.namelist()) == expected
        for name in expected:
            data = archive.read(name)
            assert data == (FOLDER / name).read_bytes()
            assert not PRIVATE_EVIDENCE.search(data.decode()), name
    print('Part 2 evidence, reproduction and archive checks passed')


if __name__ == '__main__':
    main()
