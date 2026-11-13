#!/usr/bin/env python3
"""Build a measurement guide and a row-level index from the published review data."""
import argparse
from html import escape
import json
from pathlib import Path
from urllib.parse import urlencode

from build_learning_hub import CSS
from site_metadata import canonical_url, finalize_page

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'reviews/interim-review'
VERSIONS = {
    'historical-replication': 'fc3839b9c84d698cb6b45c5bb0122bba4cfe4985',
    'prompt-framing': 'becc6a61a0ea6fdc5047cdd1a77ced3e2efa27dc',
}
REPO = 'https://github.com/helen-bird/geo-platform-observation'
GUIDE = 'learning-hub/measurement/index.html'
INDEX = 'learning-hub/review-evidence/index.html'
RECORD = 'learning-hub/review-evidence/record.html'
SHEET = 'ai-recommendation-measurement.xlsx'
CASE = 'IR2-GROK-WEB-EVIDENCE-CREATOR-'
EXTRA_CSS = '''
.step{padding:25px 0;border-top:1px solid var(--line)}.step h2{max-width:36ch}
.callout{padding:15px 18px;border:1px solid var(--line);background:var(--soft);border-radius:8px}
.table-wrap{overflow:auto;margin:16px 0}table{border-collapse:collapse;width:100%;font-size:14px}
td,th{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:8px 12px}
thead{background:var(--soft)}caption{text-align:left;font-weight:650;padding:7px 0}
td:last-child a+a{margin-left:14px}tr:target{background:#fff2c4}
code{overflow-wrap:anywhere}details{padding:12px 0;border-top:1px solid var(--line)}
summary{cursor:pointer;font-weight:650}pre{background:var(--soft);padding:14px;white-space:pre-wrap;overflow-wrap:anywhere}
'''
def load_part(route):
    files = {}
    for kind in ('answers', 'measurements'):
        p = ROOT / REVIEW / route / 'data' / (kind+'.jsonl')
        records = {}
        for line_no, line in enumerate(p.read_text().splitlines(), 1):
            row = json.loads(line)
            assert row['answer_id'] not in records
            records[row['answer_id']] = (line_no, row)
        files[kind] = records
    assert files['answers'].keys() == files['measurements'].keys()
    return files


def permalink(route, file, line=None):
    return f'{REPO}/blob/{VERSIONS[route]}/{REVIEW}/{route}/data/{file}' + (f'#L{line}' if line else '')


def record_url(route, key, section):
    return 'record.html?' + urlencode({'review': route, 'id': key}) + '#' + section


def example_data(part):
    route = 'prompt-framing'
    cfg = json.loads((ROOT/REVIEW/route/'data/conditions.json').read_text())
    records = []
    for key in sorted(part['answers']):
        if not key.startswith(CASE):
            continue
        _, answer = part['answers'][key]
        _, m = part['measurements'][key]
        assert not answer['body_url_links'] and not answer['explicit_source_urls']
        assert m['search_activity_observed'] is True and answer['original_visible_source_panel_count']
        records.append({
            'slot': f"B{m['block']:02d}", 'id': key, 'time': m['submitted_at'],
            'mention': 'Yes' if 'Helen Bird' in m['people_named'] else 'No',
            'citation': 'Unknown',
            'recommendation': 'Yes' if 'Helen Bird' in m['people_recommended'] else 'No',
            'answer': canonical_url(RECORD) + record_url(route, key, 'answer').removeprefix('record.html'),
            'measurement': canonical_url(RECORD) + record_url(route, key, 'coding').removeprefix('record.html'),
            'panel_count': answer['original_visible_source_panel_count'],
        })
    assert (len(records), sum(x['mention']=='Yes' for x in records),
            sum(x['recommendation']=='Yes' for x in records)) == (10, 8, 7)
    return {'prompt': cfg['prompts']['evidence-creator']['prompt'], 'records': records}


def shell(path, title, description, nav, body):
    links = ''.join(f'<a href="{escape(link, quote=True)}">{escape(label)}</a>' for link,label in nav)
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} · GEO Lab</title>
<meta name="description" content="{escape(description, quote=True)}"><link rel="canonical" href="{canonical_url(path)}">
<style>{CSS}{EXTRA_CSS}</style>{'<meta name="robots" content="noindex">' if path == RECORD else ''}</head><body><a class="skip" href="#main">Skip to content</a>
<div class="layout"><nav aria-label="Page contents"><strong>GEO Learning Log</strong><div class="nav-links">{links}</div></nav>
<main id="main"><h1>{escape(title)}</h1>{body}<p class="footer">GEO Learning Log · <a href="../">Learning Hub</a> · <a href="{REPO}">Repository</a></p></main></div></body></html>'''
    return finalize_page(document, path, kind='evidence-index' if path == INDEX else 'guide')


def guide(example):
    body = f'''
<p class="lead">A repeatable baseline for solo founders: choose one buyer question, record what AI search actually recommends, and check again after a documented change.</p>
<p class="author">By Helen Bird · GEO Learning Log</p>
<div class="callout"><strong>Start here:</strong> <a href="{SHEET}" download>Download the Excel worksheet</a>. It includes a blank template and a worked example using ten previously published responses.</div>
<section class="step" id="choose"><h2>1. Choose one real buyer question</h2>
<p>Start with a question a prospective user would ask before knowing your product. For example, replace the brackets in “What free tools help [buyer] do [task]?” with a real audience and task. Save the exact wording. Define the target product and acceptable aliases before testing; record a company's name separately if it is not the product name.</p>
<p>Use one worksheet copy for each exact question, target and environment. If you change wording or compare an API with a web interface, keep those results separate.</p></section>
<section class="step" id="run"><h2>2. Run and save the baseline</h2>
<ol><li>Write down the number of planned slots and the retry rule. Ten runs can be a manageable pilot. Treat the result as a snapshot; use more runs and multiple collection windows for decisions that need better precision.</li>
<li>Use a fresh session each time. Keep the interface, model, search setting, locale and personalization settings consistent. Record both whether search was enabled and what activity was actually observable.</li>
<li>Save the full answer, final links, separately observed queries or source panel, and the time. Log failed attempts; if a retry is allowed, use the same slot and a new attempt ID. Select at most one complete answer per slot. Save answers privately unless you have checked them for sensitive information.</li></ol></section>
<section class="step" id="score"><h2>3. Score three things separately</h2>
<div class="table-wrap"><table><caption>Coding guide</caption><thead><tr><th scope="col">Field</th><th scope="col">Yes means</th></tr></thead><tbody>
<tr><th scope="row">Mention</th><td>The target or a predeclared alias is explicitly named in the answer.</td></tr>
<tr><th scope="row">Citation</th><td>An identifiable final answer citation points to a target-owned or target-authored source, using the ownership rule you set before testing.</td></tr>
<tr><th scope="row">Recommendation</th><td>The answer actively suggests the target as a fit for the user's task. A neutral description, rejection or mere link does not count.</td></tr></tbody></table></div>
<blockquote><p>Use <strong>No</strong> when the needed evidence is observable and the event did not occur. Use <strong>Unknown</strong> when it cannot be judged. A domain in a search result or a separate source panel does not establish a final citation.</p></blockquote>
<p>Report each event as Yes / (Yes + No), alongside the number of selected answers, unknowns and failed attempts. If no judgment is possible, show no rate. A failure is an attempt outcome, not a negative answer.</p></section>
<section class="step" id="change"><h2>4. Record a change and repeat</h2>
<p>Save the page URL, what changed, the version and its deployment time. Wait until you can check whether the new version is available to the search path you are testing; record that evidence and its limits. Repeat the same question, settings and collection procedure. Keep a contemporaneous comparison question or unchanged page if possible, and note platform changes.</p>
<blockquote><p>A movement from, for example, 2/10 to 4/10 is a difference between two observed batches. It does not by itself show that the webpage edit caused the change. A search index check, a final citation and an AI recommendation measure different things.</p></blockquote></section>
<section class="step" id="worked-example"><h2>Worked example: a real baseline</h2>
<p>Target: <strong>Helen Bird as a person</strong>. This example transfers one existing condition from Interim Review Part 2: Grok Expert consumer web, fresh ordinary sessions, explicit native web search, X and conversation history personalization off during collection.</p>
<blockquote><p>{escape(example['prompt'])}</p></blockquote>
<ul><li><strong>Mention: 8/10.</strong> The answer named Helen Bird.</li><li><strong>Recommendation: 7/10.</strong> The answer suggested Helen Bird herself; listing a resource alone did not qualify.</li><li><strong>Final citation: no estimable rate.</strong> Ten selected answers; ten unknown. Source panels were observed, but the capture cannot attribute a final citation to Helen Bird. No follow-up batch was collected for this worksheet.</li></ul>
<p>In slot B01, the answer puts Helen Bird among the creators it says stand out. That counts as a mention and a recommendation. In B07, it describes her work in a background paragraph without selecting her as a recommended creator. The published coding counts a mention only.</p>
<p>In the workbook, open <strong>Worked example</strong> and compare the row codes with the saved answers. <a href="../review-evidence/#worked-example">Trace the exact ten rows and their coding</a>.</p></section>
<p>Related reading: <a href="../../stages/03-question-sensitivity/">Question sensitivity</a> · <a href="../../stages/05-technical-discoverability/">Technical discoverability</a> · <a href="../review-evidence/">Interim review evidence and reproduction</a></p>'''
    return shell(GUIDE,'Measure AI recommendations for your product',
                 'A free guide and worksheet to record an AI search recommendation baseline, score the evidence and repeat after a change.',
                 [('../','Learning Hub'),('#choose','Choose a question'),('#run','Run the baseline'),('#score','Score the evidence'),
                  ('#change','Repeat after a change'),('#worked-example','Worked example')],body)


def row_links(route, key):
    answer, coding = (escape(record_url(route,key,s), quote=True) for s in ('answer','coding'))
    return f'<a href="{answer}">Answer</a><a href="{coding}">Coding</a>'


def tables(route, part):
    groups = {}
    for key, (_, m) in sorted(part['measurements'].items()):
        name = m['condition_id'] if route == 'historical-replication' else ' · '.join((m['environment'],m['frame'],m['target']))
        groups.setdefault(name, []).append(key)
    output = []
    for name, keys in groups.items():
        rows = ''.join(f'<tr id="{escape(key, quote=True)}"><th scope="row">{escape(key)}</th><td>{row_links(route,key)}</td></tr>' for key in keys)
        output.append(f'<details id="cell-{escape(name.replace(" · ", "-"),quote=True)}"><summary>{escape(name)} · {len(keys)} answers</summary><div class="table-wrap"><table><thead><tr><th scope="col">Answer ID</th><th scope="col">Fixed evidence</th></tr></thead><tbody>{rows}</tbody></table></div></details>')
    return ''.join(output)


def part_index(route, part, title, ident):
    base = '../../'+REVIEW+'/'+route+'/'
    sha = VERSIONS[route]
    return f'''<section class="step" id="{ident}"><h2>{title}</h2>
<div class="links"><a href="{base}">Report</a><a href="{base}technical-appendix.html">Methods</a><a href="{base}public-data.zip">Download data</a>
<a href="{REPO}/tree/{sha}/{REVIEW}/{route}/data">Fixed dataset ({sha[:7]})</a><a href="{permalink(route,"conditions.json")}">Exact questions and settings</a><a href="{permalink(route,"attempts.jsonl")}">Attempt ledger</a></div>
<p>Open a condition to see its answer IDs, then choose Answer for the saved response or Coding for the published judgments.</p>{tables(route,part)}</section>'''


def evidence(parts, example):
    p1, p2 = VERSIONS
    first = parts[p1]
    records = [m for _,m in first['measurements'].values() if m['condition_id']=='S6-Q1-GROK']
    counts = [sum(m['binary'][key] for m in records) for key in ('candidate_artur-ferreira_recommendation','candidate_artur-ferreira_person_mention')]
    assert (len(records),counts)==(15,[15,0])
    sample = 'S6-Q1-GROK-B01-A01'
    rows = ''.join(f'<tr><th scope="row">{escape(x["slot"])}</th><td>{x["mention"]}</td><td>{x["citation"]}</td><td>{x["recommendation"]}</td><td>{row_links(p2,x["id"])}</td></tr>' for x in example['records'])
    body = f'''
<p class="lead">Follow a report result back to the original answer, its coding and the exact public version. The two reviews cover 420 selected responses.</p>
<section class="step" id="reproduce"><h2>Recalculate a reported number</h2>
<p>From a clean copy of the repository, run the command for either fixed version below. Python 3 uses the checked-in public data. The build overwrites derived files in that copy; it does not send prompts or make API calls.</p>
<h3>Part 1: work versus author</h3>
<pre><code>git switch --detach {VERSIONS[p1]}
python3 scripts/build_interim_review.py
PYTHONPATH=scripts python3 -c "import build_interim_review as review; review.check()"</code></pre>
<p>Compare the report and <a href="{permalink(p1,'summary.json')}">saved summary</a>: of the 15 Grok answers to Q1, 15 recommended The GEO Lab and 0 explicitly named Artur Ferreira. For example, <a href="{escape(record_url(p1,sample,"answer"),quote=True)}">{sample}</a> shows the work; its <a href="{escape(record_url(p1,sample,"coding"),quote=True)}">coding row</a> records the separate author judgment. The result applies to this prompt and batch.</p>
<h3>Part 2: the worked measurement baseline</h3>
<pre><code>git switch --detach {VERSIONS[p2]}
python3 scripts/build_prompt_framing.py
PYTHONPATH=scripts python3 -c "import build_prompt_framing as review; review.check()"</code></pre>
<p>Compare the report and <a href="{permalink(p2,'summary.json')}">saved summary</a>: for Grok on the evidence-creator prompt, Helen Bird was named in 8 of 10 answers and recommended in 7 of 10. <a href="#worked-example">Trace the ten rows below</a>.</p>
<blockquote><p>These commands reproduce arithmetic from archived coding. To check a judgment, read the linked answer. To rerun online, use the linked exact prompts, settings and attempt rules, capture a new batch, and report model, search and interface changes. Live results can differ and API usage can cost money. The original search environment and uncaptured fields cannot be recreated by running an offline script.</p></blockquote></section>
<section class="step" id="worked-example"><h2>Part 2: ten baseline answers</h2>
<p>Download the <a href="../measurement/{SHEET}">worked worksheet</a> or compare the stored rows. A visible source panel is search evidence; final target citation attribution is unknown in this capture.</p>
<div class="table-wrap" tabindex="0" role="region" aria-label="Ten baseline answers"><table><thead><tr><th scope="col">Slot</th><th scope="col">Mention</th><th scope="col">Citation</th><th scope="col">Recommendation</th><th scope="col">Fixed evidence</th></tr></thead><tbody>{rows}</tbody></table></div></section>
{part_index(p1,first,'Part 1: Historical replication','part-1')}
{part_index(p2,parts[p2],'Part 2: Question framing','part-2')}
'''
    return shell(INDEX,'Interim review evidence',
                 'Trace 420 selected GEO review responses to fixed original answers, coding, settings and offline reproduction steps.',
                 [('../','Learning Hub'),('#reproduce','Recalculate results'),('#worked-example','Ten baseline answers'),
                  ('#part-1','Part 1 · Historical replication'),('#part-2','Part 2 · Question framing')],body)


def reader():
    sources = json.dumps({
        route: f'{REPO}/blob/{sha}/{REVIEW}/{route}/data/'
        for route, sha in VERSIONS.items()
    })
    body = """
<p>Read the original public response and the corresponding published coding. Each section links to its fixed GitHub source file.</p>
<noscript><p>JavaScript is needed to open an individual record here. The <a href="./">evidence index</a> links to the complete versioned datasets.</p></noscript>
<p id="load-status" role="status"></p>
<section id="answer" class="step"><h2>Original public answer</h2><p><a id="answer-source" hidden>Fixed answer file on GitHub</a></p><pre id="answer-text" hidden></pre></section>
<section id="coding" class="step"><h2>Published coding</h2><p><a id="coding-source" hidden>Fixed coding file on GitHub</a></p><pre id="coding-text" hidden></pre></section>
<script>
const versions = """ + sources + r""";
const params = new URLSearchParams(location.search);
const review = params.get("review");
const id = params.get("id");
const status = document.getElementById("load-status");
const kinds = [["answer","answers"],["coding","measurements"]];
async function showRecord() {
    if (!Object.hasOwn(versions, review) || !id || !/^[A-Z0-9-]+$/.test(id)) {
        status.textContent = "Select a valid answer from the evidence index.";
        return;
    }
    status.textContent = "Loading " + id + "…";
    await Promise.all(kinds.map(async ([section,file]) => {
        const name = file + ".jsonl";
        const source = document.getElementById(section + "-source");
        source.href = versions[review] + name;
        source.hidden = false;
        const response = await fetch("../../reviews/interim-review/" + review + "/data/" + name);
        if (!response.ok) throw new Error("Archive unavailable");
        const rows = (await response.text()).trimEnd().split(/\r?\n/);
        for (let i = 0; i < rows.length; i++) {
            const row = JSON.parse(rows[i]);
            if (row.answer_id !== id) continue;
            source.href += "#L" + (i+1);
            const content = document.getElementById(section + "-text");
            content.textContent = section === "answer" ? row.answer_text : JSON.stringify(row, null, 2);
            content.hidden = false;
            return;
        }
        throw new Error("Answer ID not found");
    }));
    status.textContent = "Answer ID: " + id;
    if (location.hash === "#answer" || location.hash === "#coding") {
        document.getElementById(location.hash.slice(1)).scrollIntoView();
    }
}
showRecord().catch(() => {
    status.textContent = "This record could not be loaded. Use the fixed GitHub files above or the evidence index.";
});
</script>"""
    return shell(RECORD, 'Read a review answer',
                 'Open an individual original GEO review answer and its published coding.',
                 [('./','Evidence index'),('#answer','Original answer'),('#coding','Published coding')],body)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--example-json', action='store_true', help='Print the worked-example inputs for the workbook')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()
    parts = {route: load_part(route) for route in VERSIONS}
    assert [len(p['answers']) for p in parts.values()] == [300, 120]
    example = example_data(parts['prompt-framing'])
    if args.example_json:
        print(json.dumps(example))
        return
    for path, html in ((GUIDE,guide(example)),(INDEX,evidence(parts,example)),(RECORD,reader())):
        target = ROOT/path
        if args.check:
            assert target.read_text() == html, f'Rebuild {path}'
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html)
    print('Measurement guide and evidence index: 420 selected answers, 10 worked-example rows.')

if __name__ == '__main__':
    main()
