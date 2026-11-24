"""Install the consent gate on public research reading pages."""
from functools import lru_cache
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'assets/analytics-config.json'
SCRIPT = '/geo-platform-observation/assets/ga4-loader.js'
TAG = re.compile(r'<script\s+id="geo-site-analytics"(?=\s|>)[^>]*>\s*</script>', re.I)


@lru_cache(maxsize=1)
def configuration():
    if not CONFIG.exists():
        return None, frozenset()
    config = json.loads(CONFIG.read_text())
    id_ = config['measurement_id']
    if not re.fullmatch(r'G-[A-Z0-9]+',id_):
        raise ValueError('Set a valid public GA4 measurement ID')
    reports = json.loads((ROOT/'report-versions.json').read_text())['reports']
    paths = {r['path'] for r in reports} | {
        'learning-hub/index.html',
        'learning-hub/measurement/index.html',
        'learning-hub/review-evidence/index.html',
        'learning-hub/review-evidence/record.html',
        'reviews/interim-review/historical-replication/index.html',
        'reviews/interim-review/historical-replication/technical-appendix.html',
        'reviews/interim-review/prompt-framing/index.html',
        'reviews/interim-review/prompt-framing/technical-appendix.html',
        'evidence/index.html',
    }
    for r in reports:
        appendix = r.get('appendix', str(Path(r['path']).with_name('technical-appendix.html')))
        if appendix:
            paths.add(appendix)
    manifest = ROOT/'evidence/manifest.json'
    if manifest.exists():
        paths.update(r['path'] for r in json.loads(manifest.read_text())['responses'])
    return id_, paths


def decorate_head(head, path):
    head = TAG.sub('',head)
    id_, pages = configuration()
    if id_ and path in pages:
        return head + f'<script id="geo-site-analytics" defer src="{SCRIPT}" data-measurement-id="{id_}"></script>'
    return head


def refresh_static_readers():
    """Apply the head tag to reading pages, including freshly generated evidence."""
    for path in configuration()[1]:
        dest = ROOT/path
        if not dest.is_file():
            raise FileNotFoundError(dest)
        doc = dest.read_text()
        updated,n = re.subn(r'(<head\b[^>]*>)(.*?)(</head>)',
                             lambda m:m[1]+decorate_head(m[2],path)+m[3],
                             doc,count=1,flags=re.S|re.I)
        if n != 1:
            raise ValueError(f'Missing head in {path}')
        if updated != doc:
            dest.write_text(updated)


if __name__ == '__main__':
    refresh_static_readers()
