#!/usr/bin/env python3
"""Render the public distribution field report and its reviewed evidence."""
import csv
from html import escape
import json
from pathlib import Path
import re

from build_learning_hub import CSS
from build_stage5_report import EXTRA, note, table
from report_series import finish_page, series_navigation
from site_metadata import finalize_page

ROOT = Path(__file__).resolve().parents[1]
ROUTE = 'stages/08-distribution'
FOLDER = ROOT / ROUTE
READER_NAV = [('findings', 'Findings'), ('finding-1', 'X and Reddit'),
              ('finding-2', 'Free directories'), ('finding-3', 'Traffic and QA'),
              ('weekly-plan', 'One-week test'), ('methods', 'Methods and evidence')]
APPENDIX_NAV = [('community', 'Community and X'), ('submissions', 'Directory status'),
                ('traffic', 'Website and repository traffic'), ('rules', 'Measurement rules')]
LOCAL_CSS = '''
.finding{margin:25px 0 0;padding:0 0 12px}.finding h3{font-size:22px;line-height:1.25}
.finding p+p{margin-top:14px}.step-list li{padding-left:4px}.step-list li::marker{font-weight:700;color:var(--accent)}
.lab-utility-links{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:22px}
#findings h2,#weekly-plan h2,#methods h2{max-width:36ch}
@media(max-width:650px){.finding h3{font-size:20px}}
'''


def inline(line):
    value = escape(line)
    value = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', value)
    value = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', value)
    value = re.sub(r'`([^`]+)`', r'<code>\1</code>', value)
    return value


def reader():
    # The report source uses prose blocks, named headings, notes and one ordered list.
    title, source = (FOLDER / 'distribution-report.md').read_text().split('\n', 1)
    ids = iter(['findings', 'weekly-plan', 'methods'])
    parts = []
    in_section = in_finding = False
    for block in source.strip().split('\n\n'):
        if block.startswith('## '):
            if in_finding:
                parts.append('</article>')
                in_finding = False
            if in_section:
                parts.append('</section>')
            parts.append(f'<section id="{next(ids)}"><h2>{inline(block[3:])}</h2>')
            in_section = True
        elif block.startswith('### '):
            if in_finding:
                parts.append('</article>')
            label = block[4:]
            parts.append(f'<article class="finding" id="finding-{label[0]}"><h3>{inline(label)}</h3>')
            in_finding = True
        elif block.startswith('> '):
            parts.append(note(inline(block[2:])))
        elif block.startswith('*') and not block.startswith('**') and block.endswith('*'):
            parts.append(f'<p class="lead">{inline(block[1:-1])}</p>')
        elif block.startswith('1. '):
            items = ''.join(f'<li>{inline(line.split(". ", 1)[1])}</li>' for line in block.splitlines())
            parts.append(f'<ol class="step-list">{items}</ol>')
        else:
            parts.append(f'<p>{inline(block)}</p>')
    assert in_section and next(ids, None) is None
    parts.append('</section>')
    return document(
        title[2:], 'An indie creator shares GEO research on X and Reddit, screens 15 directories, and tracks real clicks, website measurement limits and unconfirmed public listings.',
        READER_NAV, '\n'.join(parts), 'reader',
    )


def out(label, url):
    return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'


def appendix():
    with (FOLDER / 'summary.csv').open() as handle:
        data = list(csv.DictReader(handle))
    values = {(r['channel_or_item'], r['metric']): r['value'] for r in data if r['metric'] != 'eligible_requests'}
    posts = [
        ('X Lab 06', 'GEO Lab #06', '2120815689904845270'),
        ('X Lab 07', 'GEO Lab #07', '2121172261180989531'),
        ('X Interim Review Part 2', 'Interim Review Part 2', '2120480868292837859'),
        ('X Lab 08 discussion', 'GEO Lab #08 discussion', '2122306566649249943'),
    ]
    post_rows = [[out(label, f'https://x.com/bird_helen67403/status/{post_id}')] +
                 [values[key, metric] or 'N/A' for metric in ('impressions', 'engagements', 'link_clicks')]
                 for key, label, post_id in posts]
    totals = [sum(int(row[col]) for row in post_rows if row[col] != 'N/A') for col in range(1, 4)]
    assert totals == [233, 30, 4]
    post_rows.append(['Total observed', *totals])
    prs = [
        ('Awesome GEO #23', 'marketingtoolslist/awesome-geo', 23, 'Open and unmerged'),
        ('Awesome AEO & SEO #14', 'discoveredlabs/awesome-aeo-seo', 14, 'Open and unmerged. Cubic recorded an automated review approval on November 17.'),
        ('Awesome GEO Tools #9', 'vibetags/awesome-geo-tools', 9, 'Open and unmerged'),
        ('Awesome Generative Engine Optimization #234', 'amplifying-ai/awesome-generative-engine-optimization', 234, 'Open and unmerged'),
    ]
    submissions = [[out(label, f'https://github.com/{repo}/pull/{pr}'), 'November 22', status]
                   for label, repo, pr, status in prs]
    submissions.extend([
        ['SEOFOMO', 'November 17', 'Delivery acknowledged. Editorial decision and public placement unconfirmed.'],
        ['PitchWall', 'November 17', 'Review in progress. Estimated wait greater than 30 days.'],
        ['Uneed', 'November 17', 'Free launch queued for July 3, 2027.'],
    ])
    daily = [(row['window_cst'], int(row['value'])) for row in data if row['metric'] == 'eligible_requests']
    assert sum(count for _, count in daily) == 49
    content = note('<strong>Public evidence.</strong> This appendix uses reviewed aggregate metrics and public project links. Private dashboards, underlying analytics exports, account receipts and Reddit identities are held outside this release. The cutoff is November 22, 2026, Beijing time.')
    content += '<section id="community"><h2>Community and X</h2>'
    content += table(['Post', 'Impressions', 'Engagements', 'Link clicks'], post_rows)
    content += note('Cumulative X Post Analytics at readback. Counts can include repeat actions. Click timestamps are unavailable. Lab #07 had a tagged report link and #06 had a clean report link. Lab #08 has no confirmed site link.')
    content += table(['Reddit discussion', 'Published (Beijing time)', 'Resource link'], [
        ['AI referrals and repeated measurement', 'November 16', 'None'],
        ['Sample size and measurement variance', 'November 16', 'None'],
        ['Evaluating evidence from paid AEO tools', 'November 16', 'None'],
    ])
    content += note('The author reported zero views, votes, replies, substantive discussion or resource requests across the three replies. Public visibility was not independently rechecked. Unpublished tracking links and their QA visits are outside the Reddit referral results.') + '</section>'
    content += '<section id="submissions"><h2>Directory status</h2><p><strong>15 screened → 7 submitted or queued → 0 verified public placements</strong></p>'
    content += table(['Placement', 'Last verified in 2026', 'Status'], submissions)
    content += note('Four PRs were rechecked on November 22. PitchWall and Uneed required sign-in at readback, so the saved November 17 receipts determine the public summary. Other candidates were deferred or skipped for eligibility, price, submission rules, reciprocal linking or creator choice. No verified GA4 referral was attributable to a directory.') + '</section>'
    content += '<section id="traffic"><h2>Website and repository traffic</h2>'
    content += table(['Beijing window', 'Raw sessions / users / views / downloads', 'After known QA'],
                     [['Nov 13–22, since activation', '11 / 7 / 16 / 7', '1 / 1 / 0 / 0'],
                      ['Nov 16–22, seven calendar days', '10 / 6 / 15 / 7', '1 / 1 / 0 / 0'],
                      ['Nov 17–22, submission window', '3 / 2 / 5 / 2', '0 / 0 / 0 / 0']])
    content += '<p>GA4 began on November 13 at 17:26 Beijing time, and coverage expanded during the study. The raw page views were 12 for the Guide, 2 for the homepage, 1 for a technical appendix, and 1 for a saved answer. All matched QA or a documented setup check.</p>'
    content += note('The seven Worksheet events matched five Reddit link tests, one GA setup test, and one PitchWall test. One direct homepage visit was excluded because it matched the deployment check. Retaining it would yield two unresolved sessions, one view, and still no confirmed reader download. The retained session had no known landing page or source and zero page views.')
    content += table(['Date (Beijing)', 'Eligible Guide requests outside marked QA'], daily)
    content += note('The counter covers a separate distribution endpoint. Forty-seven requests lacked a source label. The two with a PitchWall label were both on November 17, with actual origin unknown. Six additional marked QA requests are outside these counts. No earlier comparable daily baseline is available. November 22 is a partial day.')
    content += '<p>GitHub recorded six repository views and three unique repository visitors for November 8–21 UTC. The project website was a referrer for two repository views. These are visits to the repository.</p></section>'
    content += '''<section id="rules"><h2>Measurement rules</h2>
<ol class="step-list"><li><strong>Distribution action.</strong> Count a published post or reply, delivered form, open PR, or confirmed queue slot.</li>
<li><strong>Platform engagement.</strong> Save platform counts and separate clicks from the broader engagement total.</li>
<li><strong>Website evidence.</strong> Record source-bearing sessions and eligible document requests separately. A placement label alone leaves the origin unconfirmed.</li>
<li><strong>Resource usage signal.</strong> Count <code>file_download</code> as a click event after excluding marked QA and known diagnostics. Repeated events and actual use of the file require separate evidence.</li>
<li><strong>Independent pickup.</strong> Check the live public entry and its link. A receipt, bot review and queued date describe stages of submission.</li>
<li><strong>AI visibility.</strong> <code>NOT_MEASURED</code> in this lesson.</li></ol>
<p>To repeat the audit, keep dated Post Analytics counts, check each PR and entry at the cutoff, and use GA4 acquisition, landing pages and events by campaign. Reconcile QA against test evidence, preserve missing values, and retain owner-only raw data privately.</p>
<p class="lab-utility-links"><a href="summary.csv">Download public aggregate data</a><a href="https://support.google.com/analytics/answer/11198161">GA4 data freshness</a><a href="https://docs.github.com/en/repositories/viewing-activity-and-data-for-your-repository/viewing-traffic-to-a-repository">GitHub traffic window</a></p></section>'''
    return document('GEO Lab #08: Distribution Methods and Evidence',
                    'Reviewed X and Reddit activity, seven directory submission states, aggregate site traffic, and QA exclusions for the GEO Lab distribution study.',
                    APPENDIX_NAV, content, 'appendix')


def document(title, description, items, content, kind):
    nav = ''.join(f'<a href="#{key}">{label}</a>' for key, label in items)
    utility = (out('Methods and evidence', 'technical-appendix.html') if kind == 'reader'
               else out('Return to the report', './'))
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(description, quote=True)}">
<style>{CSS}{EXTRA}{LOCAL_CSS}</style></head>
<body><a class="skip" href="#main">Skip to report</a><div class="layout">
<nav aria-label="GEO Lab 08 contents"><strong>On this page</strong><div class="nav-links">{nav}</div>
<div class="nav-group">{utility}{out('Public aggregate data', 'summary.csv')}</div></nav>
<main id="main"><p class="lesson-name">GEO Lab #08 · Distribution</p><h1>{escape(title)}</h1>
<p class="author">Helen Bird · November 22, 2026</p>
{content}
<p class="footer">Helen Bird · GEO Learning Log · <a href="https://github.com/helen-bird/geo-platform-observation">GitHub repository</a></p>
</main></div></body></html>
'''
    return finish_page(html, 8, kind)


def refresh_static_readers():
    """Refresh the series selector and metadata on the two hand-authored readers."""
    reports = json.loads((ROOT / 'report-versions.json').read_text())['reports']
    for record in reports:
        if record['stage'] not in (6, 7):
            continue
        path = record['path']
        target = ROOT / path
        navigation = series_navigation(reports, str(Path(path).parent), path)
        page, matches = re.subn(r'<div class="experiment-series"[^>]*>.*?</div>', lambda _: navigation,
                                target.read_text(), count=1, flags=re.S)
        assert matches == 1, path
        target.write_text(finalize_page(page, path, 'reader', record['stage']))


def main():
    (FOLDER / 'index.html').write_text(reader())
    (FOLDER / 'technical-appendix.html').write_text(appendix())
    refresh_static_readers()


if __name__ == '__main__':
    main()
