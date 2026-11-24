#!/usr/bin/env python3
"""Build a measurement guide and a row-level index from the published review data."""
import argparse
import csv
from html import escape
from io import StringIO
import json
from pathlib import Path
from urllib.parse import urlencode

from build_interim_review import subset_rates
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
PROMPT_CSV = 'prompt-starters.csv'
CASE = 'IR2-GROK-WEB-EVIDENCE-CREATOR-'
LAB09 = 'stages/09-visibility-baseline'
GUIDE_V1 = '15b222bddb55255ca67cc9409e126834450fb029'
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
GUIDE_CSS = '''
.kit-actions{display:flex;flex-wrap:wrap;align-items:center;gap:10px 22px;margin:22px 0}
.kit-download{display:inline-block;padding:10px 16px;border:1px solid var(--accent);border-radius:7px;background:var(--accent);color:#fff;font-weight:700;text-decoration:none}
.kit-download:hover{background:#105761;text-decoration:underline}
.kit-specs{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:9px 20px;max-width:72ch;margin:22px 0 30px;padding:15px 18px;border-block:1px solid var(--line)}
.kit-specs dt{font-weight:650}.kit-specs dd{min-width:0;margin:0}
.kit-preview{max-width:78ch;margin:16px 0 0}.kit-preview caption{text-align:left}
.kit-prompts{list-style:none;padding:0;margin-top:8px;max-width:72ch}
.kit-prompts li{display:flex;gap:8px 14px;align-items:baseline;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--line)}
.kit-prompts p{margin:0}.kit-copy{flex:none;font:inherit;font-size:14px;min-height:36px;padding:3px 9px;background:white;color:var(--accent);border:1px solid #9cb7bb;border-radius:5px;cursor:pointer}
.kit-copy:hover{background:var(--soft)}.kit-prompts+.kit-section-label{margin-top:24px}
.kit-builder{max-width:72ch;margin:22px 0;padding:12px 16px;border:1px solid var(--line);border-radius:7px}
.kit-builder legend{font-weight:650;padding:0 6px}.kit-builder label{display:block;font-weight:600}
.kit-builder input{display:block;width:100%;max-width:45ch;min-height:40px;margin:3px 0 12px;padding:6px 8px;font:inherit;color:var(--ink);border:1px solid #9cb7bb;border-radius:5px}
.kit-generated{margin-top:14px}.kit-generated output{display:block;margin-bottom:10px;overflow-wrap:anywhere}
.kit-status{min-height:1.65em;font-size:14px;color:var(--muted)}
.kit-faq dt{font-weight:700;margin:13px 0 4px}.kit-faq dd{margin:0 0 16px;max-width:72ch}
.kit-next{font-weight:650}
@media(max-width:650px){.kit-actions{align-items:stretch;flex-direction:column;gap:14px}.kit-download{text-align:center}
.kit-specs{grid-template-columns:1fr;gap:2px}.kit-specs dd{margin:0 0 8px}
.kit-copy,.kit-builder input{min-height:44px}.kit-preview th,.kit-preview td{padding:7px 8px}}
'''
STARTER_PROMPTS = (
    ('Category discovery', 'Unbranded discovery', (
        'What free tools help a solo founder schedule customer interviews?',
        'Which lightweight bug trackers work well for a two-person software team?',
    )),
    ('Problem discovery', 'Unbranded discovery', (
        'How can a one-person SaaS team track failed payments without a paid dashboard?',
        'How can I collect and prioritise feature requests from early customers on a small budget?',
    )),
    ('Named comparison', 'Named diagnostic', (
        'What should I check before choosing between [my product] and [alternative] for [task]?',
        'Which features of [my product] and [alternative] help a solo founder with [task]?',
    )),
)
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


def shell(path, title, description, nav, body, *, search_title=None):
    links = ''.join(f'<a href="{escape(link, quote=True)}">{escape(label)}</a>' for link,label in nav)
    css = CSS + EXTRA_CSS + (GUIDE_CSS if path == GUIDE else '')
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(search_title or title)} · GEO Lab</title>
<meta name="description" content="{escape(description, quote=True)}"><link rel="canonical" href="{canonical_url(path)}">
<style>{css}</style>{'<meta name="robots" content="noindex">' if path == RECORD else ''}</head><body><a class="skip" href="#main">Skip to content</a>
<div class="layout"><nav aria-label="Page contents"><strong>GEO Learning Log</strong><div class="nav-links">{links}</div></nav>
<main id="main"><h1>{escape(title)}</h1>{body}<p class="footer">GEO Learning Log · <a href="../">Learning Hub</a> · <a href="{REPO}">Repository</a></p></main></div></body></html>'''
    return finalize_page(document, path, kind='evidence-index' if path == INDEX else 'guide')


def m2_example():
    data = ROOT / LAB09 / 'data'
    prompts = json.loads((data / 'prompts.json').read_text())
    observations = [(line_no, json.loads(line)) for line_no, line in
                    enumerate((data / 'observations.jsonl').read_text().splitlines(), 1)]
    selected = [(line, row) for line, row in observations if row['prompt_id'] == 'M2']
    rows = [row for _, row in selected]
    n = len(rows)
    known_more = [row for row in rows if row['panel_coverage'] == 'complete']
    observed_search = sum(row['search_evidence'] == 'yes' for row in rows)
    scores = {key: sum(row['scores'][key] for row in rows) for key in ('mention', 'citation', 'recommendation')}
    more_hits = sum(row['target_in_more'] == 1 for row in known_more)
    split = [sum(row['effort'] == effort for row in rows) for effort in ('medium', 'high')]
    assert (n, split, len(known_more), more_hits, observed_search, sum(scores.values())) == (30, [15, 15], 23, 0, 23, 0)
    fixed_observations = f'{REPO}/blob/{GUIDE_V1}/{LAB09}/data/observations.jsonl'
    complete_row = next(line for line, row in selected if row['panel_coverage'] == 'complete')
    missing_row = next(line for line, row in selected if row['panel_coverage'] != 'complete')
    return {
        'prompt': next(row['text'] for row in prompts if row['id'] == 'M2'),
        'n': n, 'known_more': len(known_more), 'more_hits': more_hits,
        'unknown_more': n - len(known_more), 'observed_search': observed_search,
        'unknown_search': n - observed_search, 'scores': scores,
        'fixed_observations': fixed_observations,
        'complete_row': f'{fixed_observations}#L{complete_row}',
        'missing_row': f'{fixed_observations}#L{missing_row}',
    }


def replication_example(part):
    route = 'historical-replication'
    conditions = json.loads((ROOT / REVIEW / route / 'data/conditions.json').read_text())
    condition = 'S6-Q3-GROK'
    records = [(line, row) for line, row in part['measurements'].values()
               if row['condition_id'] == condition]
    field = 'candidate_artur-ferreira_recommendation'
    values = [row['binary'][field] for _, row in records]
    assert len(values) == 15 and all(type(value) is bool for value in values)
    examples = [next((line, row) for line, row in records if row['binary'][field] is value)
                for value in (True, False)]
    return {
        'prompt': next(row['prompt'] for row in conditions if row['condition_id'] == condition),
        'full_n': len(values), 'full_yes': sum(values),
        'subsets': {n: subset_rates(values, n) for n in (3, 10)},
        'examples': [(canonical_url(RECORD) + record_url(route, row['answer_id'], 'answer').removeprefix('record.html'),
                      permalink(route, 'measurements.jsonl', line)) for line, row in examples],
    }


def reproduction_section(example):
    route = 'historical-replication'
    full_rate = f'{example["full_yes"]}/{example["full_n"]}'
    rows = ''.join(
        f'<tr><th scope="row">{n} of {example["full_n"]}</th>'
        f'<td>{metrics["min"]:.0%} to {metrics["max"]:.0%}</td>'
        f'<td>{metrics["over_20_pp"]:,}/{metrics["subsets"]:,} '
        f'({metrics["over_20_pp"]/metrics["subsets"]:.2%})</td></tr>'
        for n, metrics in example['subsets'].items()
    )
    examples = ' · '.join(
        f'<a href="{escape(answer, quote=True)}">{label} original answer</a> '
        f'(<a href="{escape(coding, quote=True)}">saved code</a>)'
        for label, (answer, coding) in zip(('Yes', 'No'), example['examples'])
    )
    return f'''
<section class="step" id="reproduce-a-result"><h2>Reproduce a result from 15 saved answers</h2>
<p>A historical Grok Expert batch asked the following question. The target was Artur Ferreira or his work, and <strong>{full_rate} answers ({example['full_yes']/example['full_n']:.1%})</strong> actively recommended the target.</p>
<blockquote><p>{escape(example['prompt'])}</p></blockquote>
<div class="table-wrap" tabindex="0" role="region" aria-label="Recount of three-answer and ten-answer subsets"><table><caption>How much the recorded rate changed when keeping fewer answers</caption>
<thead><tr><th scope="col">Answers kept</th><th scope="col">Recommendation rate range</th><th scope="col">Subsets more than 20 percentage points from {full_rate}</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p><strong>Try the recount.</strong> Read a Yes and a No example. Then open the fixed measurements, filter <code>condition_id</code> to <code>S6-Q3-GROK</code>, and count the true values in <code>candidate_artur-ferreira_recommendation</code>. The denominator is all {example['full_n']} coded responses in that batch. To check the table, enumerate every group of 3 and every group of 10 from those same responses, then compare each group’s rate with {full_rate}. The original build script calculates both distributions offline.</p>
<p>{examples}</p>
<p><a href="{permalink(route, 'conditions.json')}">Fixed questions and settings</a> · <a href="{permalink(route, 'measurements.jsonl')}">Fixed measurement records</a> · <a href="../../{REVIEW}/{route}/technical-appendix.html#data">Reproduce the published calculation</a></p>
<p><strong>Apply it to your own work.</strong> Use three answers to practise capture and scoring, then pre-plan a larger batch before making a decision. Subsets reuse the same 15 answers. They show sensitivity in this batch, and the figures do not establish how many responses your own study needs.</p></section>'''


def prompt_library():
    sections = []
    for group, (label, use, prompts) in enumerate(STARTER_PROMPTS, 1):
        rows = []
        for number, prompt in enumerate(prompts, 1):
            key = f'kit-prompt-{group}-{number}'
            rows.append(f'<li><p id="{key}">{escape(prompt)}</p><button type="button" class="kit-copy" hidden data-copy="{key}" aria-label="Copy {label.lower()} example {number}">Copy</button></li>')
        intro = ('<p>Use these questions to check how AI describes named options. Measure unprompted discovery with a separate, unbranded question.</p>'
                 if use == 'Named diagnostic' else '')
        sections.append(f'<h3 class="kit-section-label">{escape(label)}</h3>{intro}<ul class="kit-prompts">{"".join(rows)}</ul>')
    return ''.join(sections)


def prompt_csv():
    output = StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(('Intent', 'Prompt', 'Use'))
    writer.writerows((intent, prompt, use) for intent, use, prompts in STARTER_PROMPTS for prompt in prompts)
    return output.getvalue()


PROMPT_BUILDER = '''
<form id="kit-prompt-builder" hidden>
<fieldset class="kit-builder"><legend>Make a question for your product category</legend>
<p>Try an audience and the job they want to do. This runs in your browser. Your entries stay on this page.</p>
<label for="kit-audience">Buyer or team</label><input id="kit-audience" required maxlength="100" placeholder="a solo founder">
<label for="kit-task">Task, starting with an action verb</label><input id="kit-task" required maxlength="140" placeholder="schedule customer interviews">
<button type="submit" class="kit-copy">Build a question</button>
<p id="kit-generated" class="kit-generated" hidden><output for="kit-audience kit-task" id="kit-generated-question" aria-live="polite"></output>
<button type="button" class="kit-copy" data-copy="kit-generated-question" aria-label="Copy the question you built">Copy</button></p></fieldset></form>
<p id="kit-copy-status" class="kit-status" role="status" hidden></p>
<script>
(() => {
  const form = document.getElementById("kit-prompt-builder");
  const audience = document.getElementById("kit-audience");
  const task = document.getElementById("kit-task");
  const result = document.getElementById("kit-generated-question");
  const resultBlock = document.getElementById("kit-generated");
  const status = document.getElementById("kit-copy-status");
  form.addEventListener("submit", event => {
    event.preventDefault();
    const buyer = audience.value.trim();
    const action = task.value.trim().replace(/[.?!]+$/, "").trim();
    if (!buyer || !action) {
      status.hidden = false;
      status.textContent = "Enter a buyer and a task to build a question.";
      (buyer ? task : audience).focus();
      return;
    }
    resultBlock.hidden = false;
    result.textContent = "What free tools can help " + buyer + " " + action + "?";
    status.hidden = true;
  });
  form.addEventListener("input", () => { resultBlock.hidden = true; status.hidden = true; });
  form.hidden = false;
  if (!navigator.clipboard?.writeText) return;
  document.querySelectorAll("[data-copy]").forEach(button => {
    button.hidden = false;
    button.addEventListener("click", async () => {
      const text = document.getElementById(button.dataset.copy).textContent;
      status.hidden = false;
      try {
        await navigator.clipboard.writeText(text);
        status.textContent = "Question copied.";
      } catch {
        status.textContent = "Copy unavailable. Select the question text and copy it.";
      }
    });
  });
})();
</script>
'''


def guide(example, replication):
    first = example['records'][0]
    m2 = m2_example()
    lab09 = '../../' + LAB09 + '/'
    previous = f'{REPO}/tree/{GUIDE_V1}/learning-hub/measurement'
    body = f'''
<p class="lead">See whether ChatGPT, Grok, or another AI search interface recommends your product. Start with one buyer question, keep the answers, then repeat after a documented change.</p>
<p class="author">By <a href="../#helen-bird">Helen Bird</a> · GEO Learning Log · Measurement Kit v2.0</p>
<div class="kit-actions"><a class="kit-download" href="{SHEET}" download>Download the free Excel worksheet</a><a class="kit-next" href="#start">Start your first measurement</a></div>
<dl class="kit-specs" aria-label="What the kit includes">
<dt>Who it’s for</dt><dd>Solo founders and indie SaaS teams measuring AI recommendations on a small budget.</dd>
<dt>What you get</dt><dd>A step-by-step guide, copyable prompts, a blank Excel workbook with worked examples and before-and-after results, and a checklist for interpreting what you find.</dd>
<dt>What you need</dt><dd>Access to the AI interface you want to measure. The .xlsx download requires no sign-in. Use it locally to record manual tests.</dd>
</dl>
<div class="table-wrap kit-preview" tabindex="0" role="region" aria-label="Worksheet preview"><table><caption>Worksheet preview · one saved answer from the <a href="#worked-example">real Grok case</a></caption>
<thead><tr><th scope="col">Slot / evidence</th><th scope="col">Named</th><th scope="col">Final citation</th><th scope="col">Recommended</th></tr></thead>
<tbody><tr><th scope="row"><a href="{escape(first['answer'], quote=True)}">{escape(first['slot'])} · saved answer</a></th><td>{first['mention']}</td><td>{first['citation']}</td><td>{first['recommendation']}</td></tr></tbody>
</table></div>
<section class="step" id="start"><h2>Start with one question and one test setup</h2>
<p>Open <strong>Start here</strong> in the workbook. Write down the exact question, the target or accepted aliases, the interface and model settings, and the number of answers you plan to collect. Try three answers to practise the workflow before committing to a full batch. Mark practice attempts separately.</p>
<ol><li>Choose a question that real buyers would ask.</li><li>Save each answer and its sources in the workbook.</li><li>Read the counts in <strong>Results</strong>, then <a href="#diagnose-results">check where the evidence stops</a> before choosing a change.</li></ol></section>
<section class="step" id="choose"><h2>1. Choose one real buyer question</h2>
<p>For a discovery test, use a question someone would ask before learning your product name. Save its exact wording. Define whether you are tracking a person, project, product or distinctive resource. Record a company or author separately if their name alone does not identify the product.</p>
<p>Use one workbook copy for each exact question and target. Compare like-for-like settings. Keep consumer web and API measurements separate, even if the model names look similar.</p>
<div id="prompt-library"><h3>Copy a starting question</h3><p>Adapt a question to your buyers before you freeze it. Change an input or the wording only when you want to start a separate test. <a href="{PROMPT_CSV}" download>Download the six starters as CSV</a>.</p>
{prompt_library()}{PROMPT_BUILDER}</div></section>
<section class="step" id="run"><h2>2. Run and save the baseline</h2>
<ol><li>Number the planned slots and set a retry rule before you run. Ten answers can be a manageable pilot. Use more answers across different collection windows when the decision requires better precision.</li>
<li>Start a fresh session each time. Record platform, interface, model label, reasoning level, locale, and personalization. Save the search setting and whether you observed search separately.</li>
<li>In <strong>Attempts</strong>, record the time, slot and attempt ID, and where the full answer is saved. Preserve failed attempts. Give a retry a new attempt ID and the same slot. Select at most one complete answer per slot.</li>
<li>In <strong>Sources</strong>, attach each exact URL to its attempt and indicate where it appeared. In <strong>Competitors</strong>, save each recommended alternative with a consistent name, its position and the exact excerpt. Keep raw conversations private unless they are reviewed for sensitive information.</li></ol></section>
<section class="step" id="score"><h2>3. Distinguish what was named, cited and recommended</h2>
<div class="table-wrap" tabindex="0" role="region" aria-label="Evidence coding rules"><table><caption>What counts as a positive observation</caption><thead><tr><th scope="col">Measure</th><th scope="col">When to mark Yes</th></tr></thead><tbody>
<tr><th scope="row">Mention</th><td>The final answer explicitly names the target or a predeclared alias.</td></tr>
<tr><th scope="row">Recommendation</th><td>The answer actively suggests the target for the buyer’s task. A neutral description, rejection or link alone gets No.</td></tr>
<tr><th scope="row">Strict final citation</th><td>An identifiable link or inline citation in the final answer points to the target’s own or authored material under your ownership rule.</td></tr>
<tr><th scope="row">Observed citation in Lab #09</th><td>A recorded body link, inline citation card or main source points to the target. Keep the original link role and note incomplete coverage.</td></tr>
<tr><th scope="row">More exposure</th><td>A target URL appears in the separately labelled More list. A captured positive can be scored with partial coverage. Score No only when the complete list is available. Report coverage alongside the rate.</td></tr></tbody></table></div>
<blockquote><p>Record <strong>No</strong> when the needed evidence is available and no qualifying event appears. Record <strong>Unknown</strong> when coverage is insufficient. A page shown only in More leaves recommendation and citation unchanged. A failed attempt remains in the attempt record and supplies no answer-level score.</p></blockquote>
<p>Report Yes / (Yes + No), unknowns and failed attempts for each measure. A missing denominator produces no rate. Compare the original Lab #09 observed-citation count alongside panel coverage: absence in the saved links does not establish absence from an uncaptured panel.</p></section>
<section class="step" id="diagnose-results"><h2>Diagnose the result before changing your page</h2>
<p>Check the specific page or resource that answers the buyer’s question. Record where it appeared, and pick the next check that addresses that observation.</p>
<div class="table-wrap" tabindex="0" role="region" aria-label="Troubleshooting by observed outcome"><table><caption>Search-to-answer diagnostic checklist</caption>
<thead><tr><th scope="col">What you observed</th><th scope="col">What to check next</th><th scope="col">What to save</th></tr></thead>
<tbody>
<tr><th scope="row">Target page absent from the captured answer and complete sources</th><td>Open the canonical URL anonymously and check that the current page is readable. Then use a separate exact-title or branded search to see whether the specific page appears. Check indexing and crawl eligibility where tools are available.</td><td>The exact URL, version cue, date and separate diagnostic result. A successful direct visit does not establish natural discovery. See <a href="../../stages/05-technical-discoverability/">Lab #05’s technical checks</a>.</td></tr>
<tr><th scope="row">Target page appears only in More</th><td>Check whether it is the buyer-facing page or evidence about an adjacent topic. Compare the page and an actually recommended source. Which decision-critical fact, example, or free download answers this particular question?</td><td>The More URL, one competing recommendation with its matching page and the specific gap you can test. See <a href="{lab09}#sources">the Lab #09 source sightings</a>.</td></tr>
<tr><th scope="row">Target is cited but not recommended</th><td>Read the sentence around the citation. Check whether the page supplies background or confirms that the product meets the requested constraints. Inspect what the recommended options actually deliver.</td><td>The linked sentence, target and competing URLs, and the missing detail if one can be verified. A citation by itself establishes source visibility.</td></tr>
<tr><th scope="row">Target is recommended but referrals are unconfirmed</th><td>Follow the actual link as a signed-out visitor. Check the landing page and test your attribution separately from live traffic. Keep tagged test visits separate from measured reader visits and downloads.</td><td>The exact answer link, resolved destination and any confirmed visit or download signal. Consent and missing attribution can leave real traffic unobserved. See <a href="../../stages/08-distribution/#finding-3">Lab #08’s traffic and attribution checks</a>.</td></tr>
<tr><th scope="row">Search or source evidence is missing</th><td>Mark coverage Unknown. Score what you can see in a complete answer and keep the record. If the answer itself failed, use the retry rule you set before collection.</td><td>Which panel or answer portion was unavailable. Use <a href="#m2-example">the M2 case</a> to see how to report known and unknown denominators together.</td></tr>
</tbody></table></div>
<p>Keep diagnostic queries separate from your unbranded measurement and repeat the original wording and settings when you <a href="#change">retest a real change</a>.</p></section>
<section class="step" id="change"><h2>4. Record a change and repeat</h2>
<ol><li><strong>Freeze the baseline.</strong> Save the existing page or resource, published URL, exact question, scoring rule, settings and attempts.</li>
<li><strong>Record the change.</strong> Save what shipped, the new version and the actual deployment time. Record outside promotion separately.</li>
<li><strong>Check whether the new version can be found.</strong> Verify the live version and that its content is readable. Check for evidence of that version in relevant search results or official index tools. Record what you can verify and mark unknowns. Access by direct link only establishes that the page can be fetched.</li>
<li><strong>Run Retest 1 and Retest 2.</strong> Repeat the same question, settings, slot and retry rules. Collect the second retest in a later window, such as one week later. Track platform changes and keep a reference question, resource or set of competitors when possible.</li></ol>
<p>Use <strong>Results</strong> to compare matching conditions in percentage points. Split results when the interface, effort, search setting, prompt version or scoring rule changes.</p>
<blockquote><p><strong>Illustrative numbers.</strong> If recommendations move from 2/10 to 4/10, report 20% to 40% (+20 percentage points), with both denominators. Repeated batches help assess whether the difference persists. Platform changes and other events can still account for some or all of it.</p></blockquote></section>
<section class="step" id="worked-example"><h2>Worked example · an author’s baseline</h2>
<p>Target: <strong>Helen Bird as a person</strong>. This example transfers one existing condition from Interim Review Part 2: Grok Expert consumer web, fresh ordinary sessions, explicit native web search, X and conversation history personalization off during collection.</p>
<blockquote><p>{escape(example['prompt'])}</p></blockquote>
<ul><li><strong>Mention: 8/10.</strong> The answer named Helen Bird.</li><li><strong>Recommendation: 7/10.</strong> The answer suggested Helen Bird herself; listing a resource alone did not qualify.</li><li><strong>Final citation: no estimable rate.</strong> Ten selected answers; ten unknown. Source panels were observed, but the capture cannot attribute a final citation to Helen Bird. No follow-up batch was collected for this worksheet.</li></ul>
<p>In slot B01, the answer puts Helen Bird among the creators it says stand out. That counts as a mention and a recommendation. In B07, it describes her work in a background paragraph without selecting her as a recommended creator. The published coding counts a mention only.</p>
<p>In the workbook, open <strong>Examples</strong> and compare the row codes with the saved answers. <a href="../review-evidence/#worked-example">Trace the exact ten rows and their coding</a>.</p></section>
<section class="step" id="m2-example"><h2>Worked example · a resource with zero recommendations</h2>
<p>Lab #09 asked ChatGPT about a resource a solo founder could use, in 15 fresh sessions at Medium and 15 at High. This case tracks Helen Bird and clearly attributable resources, including the Measurement Kit. It is separate from the Grok author example above.</p>
<blockquote><p>{escape(m2['prompt'])}</p></blockquote>
<ul><li><strong>Recommendation: {m2['scores']['recommendation']}/{m2['n']}.</strong> No answer recommended the target.</li>
<li><strong>Mention and observed citation: {m2['scores']['mention']}/{m2['n']} and {m2['scores']['citation']}/{m2['n']}.</strong> No answer named the target or contained a recorded qualifying source. Some main source evidence is unavailable.</li>
<li><strong>More exposure: {m2['more_hits']}/{m2['known_more']} complete panels.</strong> A further {m2['unknown_more']} answers were left unknown in the historical coding.</li>
<li><strong>Search evidence:</strong> observed in {m2['observed_search']} answers, unknown in {m2['unknown_search']}. Search activity and complete source coverage are recorded independently.</li></ul>
<p><strong>Check the denominators.</strong> In the <a href="{m2['fixed_observations']}">fixed observations</a>, filter <code>prompt_id</code> to <code>M2</code>. Count all selected rows for recommendations. For the complete-panel rate, count rows with <code>panel_coverage</code> set to <code>complete</code> and sum their <code>target_in_more</code> values. Compare a <a href="{m2['complete_row']}">complete panel with no target</a> and a <a href="{m2['missing_row']}">row with incomplete coverage</a>.</p>
<p>At this point, you can inspect the resources that answered the task well, check how your own guide addresses it, and keep a change record before retesting. The original 0/{m2['n']} is a baseline for this question and batch.</p>
<p><a href="{lab09}">Read the Lab #09 report</a> · <a href="{lab09}technical-appendix.html#coverage">Check scoring and coverage</a> · <a href="{lab09}public-data.zip">Download the public evidence</a></p></section>
{reproduction_section(replication)}
<section class="step" id="common-questions"><h2>When the result is unclear</h2>
<dl class="kit-faq">
<dt>Can I claim improvement if the model or prompt changed?</dt><dd>Report the two results with their conditions and keep the change in your log. Start a new baseline with the current settings before making a like-for-like comparison.</dd>
<dt>Can I read the rate as zero when the sources are missing?</dt><dd>Score what is visible in the final answer. Mark the missing panel as Unknown. Show the number of known answers next to the numerator and keep the missing answers in the coverage total.</dd>
<dt>When should I run the first retest?</dt><dd>Check the live URL and the current version first. Look for dated evidence of the new content in your chosen search path. If discoverability remains unknown, record that limit before interpreting the retest.</dd>
</dl></section>
<section class="step" id="design-notes"><h2>Method and version history</h2>
<p><a href="../#helen-bird">Helen Bird</a> publishes small AI search experiments in the GEO Learning Log. The <a href="#reproduce-a-result">15-answer recount</a> shows why the guide separates practice runs from measured batches. <a href="{lab09}technical-appendix.html#coverage">Lab #09’s coverage audit</a> shows why it keeps recommendations, primary citations and More separate. Read the <a href="../../stages/07-brand-authority/">Lab #07 report</a> for how the original kit was built and the <a href="../../stages/06-content-optimization/">Lab #06 evidence review</a> for what content changes can support.</p>
<p><strong>v2.0</strong> adds a prompt library, source roles, a second retest, a search-to-answer diagnostic checklist and experiments readers can recount. The guide first appeared on <time datetime="2026-11-13">November 13, 2026</time>. The <a href="{previous}">previous guide and workbook</a> are preserved in the versioned project archive.</p>
</section>'''
    return shell(GUIDE,'Free GEO Visibility Measurement Guide & Worksheet for Solo Founders',
                 'A free GEO guide and Excel worksheet for solo founders to track AI mentions, citations, and recommendations and compare results after a change.',
                 [('../','Learning Hub'),('#start','Quick start'),('#choose','Choose a question'),('#run','Run the baseline'),
                  ('#score','Score the evidence'),('#diagnose-results','Diagnose the result'),('#change','Repeat after a change'),
                  ('#worked-example','Worked examples'),('#reproduce-a-result','Reproduce a result'),
                  ('#design-notes','Method and versions')],body,search_title='Free GEO Visibility Guide & Excel Worksheet')


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
    parser.add_argument('--guide-only', action='store_true', help='Build or check only the measurement guide')
    args = parser.parse_args()
    parts = {route: load_part(route) for route in VERSIONS}
    assert [len(p['answers']) for p in parts.values()] == [300, 120]
    example = example_data(parts['prompt-framing'])
    if args.example_json:
        print(json.dumps(example))
        return
    replication = replication_example(parts['historical-replication'])
    pages = [(GUIDE, guide(example, replication)), (str(Path(GUIDE).with_name(PROMPT_CSV)), prompt_csv())]
    if not args.guide_only:
        pages.extend(((INDEX, evidence(parts, example)), (RECORD, reader())))
    for path, content in pages:
        target = ROOT/path
        if args.check:
            assert target.read_text() == content, f'Rebuild {path}'
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
    print('Measurement guide: public worked examples, diagnostic checklist and recount.' if args.guide_only else
          'Measurement guide and evidence index: 420 selected answers, 10 worked-example rows.')

if __name__ == '__main__':
    main()
