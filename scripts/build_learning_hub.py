#!/usr/bin/env python3
"""Build the question-oriented public learning index, offline and without model calls."""
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
import sys
from urllib.parse import unquote, urlsplit

from report_series import INTERIM_LABEL, INTERIM_PART2_LABEL, INTERIM_PART2_READER, INTERIM_READER

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://helen-bird.github.io/geo-platform-observation/'
DATE = '2026-11-03'
UPDATED = '2026-11-13'
QUESTIONS = {
    1: ('How do AI search engines choose sources?',
        'Repeated GEO questions to ChatGPT Search and Grok show differences in recommended entities, cited sources and repeat overlap. Citation, mention and recommendation are separate observations.',
        '12 selected answers; three questions, two consumer interfaces, two repeats. Model and timing changes limit repeat comparisons.'),
    2: ("Why can’t AI find my public content?",
        'Direct URL access, exact-quotation search and unbranded natural discovery test different retrieval tasks. A successful direct read does not imply successful natural discovery.',
        'Six selected A/B/C answers; all ten submissions and technical/capture failures preserved. A qualified manual replacement and later native-search observations remain separate.'),
    3: ('How reliable are GEO measurements?',
        'Repeated and reworded questions explore how measurement advice, cited domains and recommended tools change. Matched comparisons and normalization sensitivity clarify the limits of one-shot scores.',
        '24 selected answers; two intents, two wordings, two environments, three repeats. OpenAI Responses API + web search is not consumer ChatGPT Search.'),
    5: ('What can technical checks prove about discoverability?',
        'A technical learning record separates Google indexing, Bing information queries, OpenAI crawl eligibility and IndexNow notifications. Successful access or API queries do not establish AI recommendations.',
        'Reviewed aggregates only: no new AI-answer experiment. Private raw engine/account evidence is excluded; the earlier snapshots cover 10 or 70 URLs, before these new pages were published.'),
    4: ('Which independent GEO creators get recommended?',
        'New answers test three historically selected creator families. Actual cited-page audits separate content organization, author attribution, evidence quality and untested practices.',
        '18 selected answers, three candidate creators and eight cited-page audits. Question-level n=3 results are primary; personal-name visibility is separate from associated content assets.'),
    6: ('Which content changes are worth making for AI search?',
        'An evidence review for indie developers and solo founders compares seven GEO studies on relevance, product facts, rewriting, and formatting.',
        'The review distinguishes citation in controlled tests, real-world associations, and the limited evidence for lasting gains from live webpage edits.'),
    7: ('What makes a creator worth recommending?',
        'Compare which creators get recommended for tutorials or reproducible experiments, then use the evidence to choose improvements a solo builder can make.',
        '60 existing ChatGPT and Grok web answers; three questions and ten answers per question and interface. The release was verified, but its effect on AI recommendations has not been measured.'),
}
CSS = '''
:root{--ink:#182b36;--muted:#4f6873;--line:#dce5e9;--accent:#176a76;--soft:#eaf4f4}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:20px;scrollbar-color:#7b9da5 #edf3f5}body{margin:0;color:var(--ink);background:white;font:16px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}::selection{background:#b8dedf;color:#12383f}a{color:var(--accent);text-underline-offset:3px;overflow-wrap:anywhere}a:hover{text-decoration-thickness:2px}:focus-visible{outline:3px solid var(--accent);outline-offset:4px}.layout{display:grid;grid-template-columns:235px minmax(0,1fr);min-height:100vh}nav{position:sticky;top:0;height:100vh;overflow:auto;background:#17343d;color:#edf7f7;padding:30px 22px}nav strong{display:block;font-size:19px;line-height:1.35;margin-bottom:18px}nav a{display:block;color:#e0eeee;text-decoration:none;padding:8px 0;font-size:14px}nav p{font-size:12px;color:#bed4db}.nav-group{border-top:1px solid #385660;margin-top:20px;padding-top:16px}main{min-width:0;max-width:1260px;padding:44px 5vw 80px}h1{font-size:clamp(30px,3vw,42px);line-height:1.17;letter-spacing:-.035em;margin:0 0 22px;max-width:24ch}h2{font-size:26px;line-height:1.3;margin:0 0 12px;max-width:30ch}h3{font-size:18px;margin:28px 0 12px}h1,h2,h3{text-wrap:balance}p,li,blockquote{max-width:72ch}p{margin:10px 0}.lead{font-size:18px}.author{font-size:14px;color:var(--muted);margin-bottom:24px}.lessons{margin-top:38px}.lesson{padding:30px 0 34px;border-top:1px solid var(--line)}.lesson-name{font-size:15px;font-weight:700;margin:0 0 7px}.links{display:flex;flex-wrap:wrap;gap:8px 22px;margin-top:18px}.links a{font-size:15px;font-weight:650}blockquote{border-left:1px solid #7bafb5;background:var(--soft);margin:18px 0;padding:12px 17px;color:#385560;font-size:14px}blockquote p:first-child{margin-top:0}blockquote p:last-child{margin-bottom:0}.dates{font-size:13px;font-variant-numeric:tabular-nums}.afterword{border-top:1px solid var(--line);padding-top:28px;margin-top:20px}.footer{font-size:13px;color:var(--muted);border-top:1px solid var(--line);padding-top:20px;margin-top:34px}.skip{position:absolute;left:12px;top:-80px;background:white;padding:10px;z-index:5}.skip:focus{top:12px}
@media(max-width:950px){.layout{grid-template-columns:190px minmax(0,1fr)}nav{padding:25px 17px}main{padding:30px}}
@media(max-width:650px){.layout{display:block}nav{position:static;height:auto;padding:18px 20px}nav strong{margin-bottom:10px;font-size:18px}.nav-links{display:flex;flex-wrap:wrap;gap:3px 18px}nav a{font-size:12px;padding:5px 0}nav .nav-group{margin-top:12px;padding-top:10px}nav p{margin:5px 0}main{padding:28px 20px 54px}h1{font-size:31px}h2{font-size:24px}.lead{font-size:16px}.lesson{padding:26px 0}.links{gap:9px 18px}.links a{font-size:14px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}@media print{nav{display:none}.layout{display:block}main{max-width:none;padding:0}a{color:inherit}.lesson{break-inside:avoid}}
'''


def render():
    reports = json.loads((ROOT/'report-versions.json').read_text())['reports']
    assert [r['stage'] for r in reports] == sorted(QUESTIONS)
    def relative(path):
        value = posixpath.relpath(path, 'learning-hub')
        if value == '../index.html': return '../'
        return value[:-len('index.html')] if value.endswith('/index.html') else value
    anchors = '<a href="#measure-your-product">Measure AI recommendations</a>' + ''.join('<a href="#lab-'+str(r['stage'])+'">#'+f'{r["stage"]:02d}'+' · '+escape(r['title'])+'</a>' for r in reports)
    anchors += '<a href="#interim-review">'+escape(INTERIM_LABEL)+'</a>'
    anchors += '<a href="#interim-review-part-2">'+escape(INTERIM_PART2_LABEL)+'</a>'
    article = ('<section class="lesson" id="measure-your-product"><p class="lesson-name">Hands-on guide</p>'
               '<h2>Does AI search recommend my product?</h2><p>Choose one buyer question, record a baseline, and repeat after a documented change.</p>'
               '<div class="links"><a href="measurement/">Read the measurement guide</a>'
               '<a href="measurement/ai-recommendation-measurement.xlsx" download>Download the Excel worksheet</a>'
               '<a href="review-evidence/">Trace and recalculate review results</a></div></section>')
    for r in reports:
        number = r['stage']
        question, summary, boundary = QUESTIONS[number]
        directory = posixpath.dirname(r['path'])
        at = lambda name: relative(posixpath.join(directory, name))
        article += '<article class="lesson" id="lab-'+str(number)+'"><p class="lesson-name">GEO Lab #'+f'{number:02d}'+' · '+escape(r['title'])+'</p><h2>'+escape(question)+'</h2><p>'+escape(summary)+'</p>'
        if r.get('record_type') == 'research_review':
            url = escape(relative(r['path']), quote=True)
            links = ('<a href="'+url+'#8-data-reproduction-and-limits">Methods and reproduction</a>'
                     '<a href="'+escape(at('creator-coding.json'),quote=True)+'">Download reviewed coding</a>'
                     if number == 7 else '<a href="'+url+'#references">Browse references</a>')
            article += ('<blockquote><p>'+escape(boundary)+'</p>'
                        '<p class="dates"><strong>Research review:</strong> '+escape(r['first_published'])+'</p></blockquote>'
                        '<div class="links"><a href="'+url+'">Read the evidence review</a>'
                        +links+'</div></article>')
            continue
        article += '<blockquote><p>'+escape(boundary)+'</p><p class="dates"><strong>Author:</strong> Helen Bird · <strong>'+('Observations' if number==5 else 'Experiment')+':</strong> '+escape(r['experiment_dates'])+'<br><strong>First public report:</strong> '+escape(r['first_published'])+' · <strong>Last revised:</strong> '+escape(r['last_revised'])+' · <strong>Version:</strong> '+escape(r['version'])+'</p></blockquote>'
        article += '<div class="links"><a href="'+escape(relative(r['path']),quote=True)+'">Read '+('learning record' if number==5 else 'report')+'</a><a href="'+escape(at('public-data.zip'),quote=True)+'">Download '+('public summary' if number==5 else 'public data')+'</a><a href="'+escape(at('technical-appendix.html'),quote=True)+'">'+('Methods and source notes' if number==5 else 'Read original evidence')+'</a></div>'
        if number == 1:
            article += '<p><a href="https://x.com/bird_helen67403/status/2116080254523445676">Original GEO Lab #01 post</a></p>'
        article += '</article>'
    review = relative(INTERIM_READER)
    article += ('<article class="lesson" id="interim-review"><p class="lesson-name">GEO Lab '+escape(INTERIM_LABEL)+'</p>'
                '<h2>Which findings held up after more runs?</h2><p>A checkpoint in the ongoing GEO Lab. Part 1 revisits ten original prompts with 300 new answers and shows what changes when three or ten runs are kept.</p>'
                '<div class="links"><a href="'+review+'">Read the interim review</a><a href="'+review+'technical-appendix.html">Methods and evidence</a>'
                '<a href="'+review+'public-data.zip">Download public data</a></div></article>')
    part2 = relative(INTERIM_PART2_READER)
    article += ('<article class="lesson" id="interim-review-part-2"><p class="lesson-name">GEO Lab '+escape(INTERIM_PART2_LABEL)+'</p>'
                '<h2>How does question framing change recommendations?</h2><p>Six questions and 120 web-search answers track how resource and creator prompts change recommendations, source lists and author naming.</p>'
                '<div class="links"><a href="'+part2+'">Read the report</a><a href="'+part2+'technical-appendix.html">Methods and evidence</a>'
                '<a href="'+part2+'public-data.zip">Download public data</a></div></article>')
    document = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Helen Bird · GEO Learning Hub</title><meta name="description" content="A question-oriented index of Helen Bird's ongoing GEO learning experiments, original public data, reports and limitations."><link rel="canonical" href="'''+SITE+'''learning-hub/"><style>'''+CSS+'''</style></head><body><a class="skip" href="#main">Skip to learning questions</a><div class="layout"><nav aria-label="Learning Hub contents"><strong>GEO Learning Log</strong><div class="nav-links"><a href="#main" aria-current="page">Learning Hub</a>'''+anchors+'''<a href="#use-evidence">Use the evidence</a></div><div class="nav-group"><a href="https://github.com/helen-bird/geo-platform-observation">Repository and data guide</a><a href="../report-versions.json">Report versions</a><a href="../CHANGELOG.md">Revision history</a></div><p>An ongoing learning record.</p></nav><main id="main"><h1>Helen Bird · GEO Learning Hub</h1><p class="lead">Start with a question, then explore the research and its sources.</p><p class="author"><strong>Author:</strong> Helen Bird · <strong>Published:</strong> '''+DATE+''' · <strong>Updated:</strong> '''+DATE+'''</p><blockquote><p>The experiments, technical observations and research review document what each source measures and where its conclusions apply.</p><p>This new index is a content-organization practice suggested by the creator audit. Whether it improves AI discovery or recommendations remains untested.</p></blockquote><div class="lessons">'''+article+'''</div><section class="afterword" id="use-evidence"><h2>Use the evidence</h2><ul><li><strong>Read by user intent.</strong> Results from different tasks should not be pooled into a universal recommendation score.</li><li><strong>Keep outcomes distinct.</strong> Page citation, content-brand recommendation, personal-name mention and personal recommendation are different observations.</li><li><strong>Check the collection interface.</strong> Labs #03 and #04 use OpenAI Responses API + web search. They do not represent consumer ChatGPT Search performance.</li></ul><p>Labs #01–#05 link to methods and public data. Lab #05 publishes reviewed aggregates. Labs #06 and #07 include methods and evidence links on their report pages. Private originals and account evidence remain outside this public repository. Use GitHub’s Copy permalink to cite a fixed revision, and include the answer or observation ID.</p><p>New questions and experiments will be added as learning continues. Earlier methods, corrections and limitations remain visible in the record.</p></section><p class="footer">Helen Bird · GEO Learning Log · <a href="https://github.com/helen-bird/geo-platform-observation">GitHub repository</a></p></main></div></body></html>'''
    document = document.replace('<strong>Updated:</strong> '+DATE, '<strong>Updated:</strong> '+UPDATED)
    document = document.replace('<a href="../report-versions.json">Report versions</a>', '<a href="../evidence/">Browse original answers</a><a href="../report-versions.json">Report versions</a>')
    document = document.replace('<a href="https://github.com/helen-bird/geo-platform-observation">GitHub repository</a></p>', '<a href="https://github.com/helen-bird/geo-platform-observation">GitHub repository</a> · <a href="../sitemap.xml">Sitemap</a></p>')
    from site_metadata import finalize_page
    return finalize_page(document, 'learning-hub/index.html', kind='hub')


class HubParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.lessons = []
        self.closed_sections = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
        if tag == 'article' and attrs.get('class') == 'lesson':
            self.lessons.append(attrs.get('id'))
        if tag == 'details' and 'open' not in attrs:
            self.closed_sections += 1


def check():
    """Validate the generated public entry and its local destinations offline."""
    destination = ROOT/'learning-hub/index.html'
    document = destination.read_text()
    parser = HubParser()
    parser.feed(document)
    errors = []
    if parser.lessons != [f'lab-{n}' for n in sorted(QUESTIONS)] + ['interim-review', 'interim-review-part-2']:
        errors.append('Learning Hub must list the interim review after the ordered labs')
    if len(parser.ids) != len(set(parser.ids)):
        errors.append('Learning Hub has duplicate section IDs')
    if parser.closed_sections:
        errors.append('Learning Hub has collapsed content')
    if '<html lang="en">' not in document or re.search(r'[\u3400-\u9fff]', document):
        errors.append('Learning Hub must be English')
    for required in ['Helen Bird', 'Author:', 'Published:', 'Updated:',
                     'not represent consumer ChatGPT Search', 'remains untested']:
        if required not in document:
            errors.append('Missing provenance or limitation: '+required)
    local_links = 0
    for href in parser.links:
        url = urlsplit(href)
        if url.scheme or url.netloc:
            if url.scheme not in ('http', 'https'):
                errors.append('Unexpected link protocol: '+href)
            continue
        local_links += 1
        target = (destination.parent/unquote(url.path)).resolve() if url.path else destination
        if target.is_dir():
            target = target/'index.html'
        if not target.is_relative_to(ROOT):
            errors.append('Local link leaves the public repository: '+href)
        elif not target.is_file():
            errors.append('Missing local link destination: '+href)
        elif url.fragment and target.suffix == '.html':
            parsed_target = HubParser()
            parsed_target.feed(target.read_text())
            if unquote(url.fragment) not in parsed_target.ids:
                errors.append('Missing local link fragment: '+href)
    if errors:
        raise AssertionError('\n'.join(errors))
    return {'learning_hub':'learning-hub/index.html', 'entries':len(parser.lessons),
            'local_links_checked':local_links, 'status':'passed'}


def main():
    if '--check' in sys.argv[1:]:
        print(json.dumps(check()))
        return
    destination = ROOT/'learning-hub/index.html'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render())
    print(json.dumps({'learning_hub':str(destination.relative_to(ROOT)),'stages':len(QUESTIONS),'model_calls':0}))


if __name__ == '__main__':
    main()
