#!/usr/bin/env python3
"""Build the redacted public Stage 2 report and data archive, without scoring answers.

Usage: python3 scripts/build_stage2_report.py [--data-dir DIR] [--output FILE]

runs.json is authoritative for six selected plan slots. selected_attempt_id
and raw_file identify a supplemental selection. attempts.json lists ALL actual
submissions, including the six original submissions; it is not added to runs.
Supporting capture files are never additional tests. Optional capture_history
or recovery_history arrays preserve repeated captures without counting queries.
protocol.findings accepts [{"title": "...", "detail": "..."}].

Optional hand-reviewed assessment (also accepted under verdict):
  {"outcome": "pass|fail|indeterminate|technical_failure",
   "x_post_content_access": {"verdict": "pass", "evidence": "..."},
   "exact_discovery": "not_assessed",
   "unprompted_discovery": "fail",
   "github_only": false, "rationale": "...", "evidence": ["..."]}
Metric values may be booleans, verdict strings, or objects with verdict/status/
value plus evidence/notes. A scalar run.verdict applies only to that condition's
primary outcome. Missing judgments are never inferred from keywords or links.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import html
import json
import os
import zipfile
from pathlib import Path
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "stages/02-post-discovery"
SITE_URL = "https://helen-bird.github.io/geo-platform-observation/stages/02-post-discovery/"


PLATFORMS = ("ChatGPT Search", "Grok")
CONDITIONS = {"A": "Direct URL access", "B": "Exact-excerpt discovery", "C": "Natural discovery"}
PRIMARY = {"A": "x_post_content_access", "B": "exact_discovery", "C": "unprompted_discovery"}
METRICS = {
    "x_post_content_access": "X post content access",
    "exact_discovery": "Exact discovery",
    "unprompted_discovery": "Unprompted discovery",
    "github_only": "GitHub only",
}
STATUS_LABELS = {
    "completed": "Completed", "technical_failure": "Technical failure",
    "pending": "Pending", "submitted": "Submitted / capture pending",
    "incomplete": "Incomplete capture", "capture_incomplete": "Body capture incomplete",
    "recovered": "Recovered capture", "blocked": "Blocked",
    "not_started": "Not started", "failed": "Failed — see evidence",
}
SLOTS = [(f"S2-{'CHATGPT' if p == 'ChatGPT Search' else 'GROK'}-{c}", p, c)
         for c in CONDITIONS for p in PLATFORMS]


def esc(value):
    return html.escape(str(value), quote=True)


def text_value(value):
    if value is None:
        return "Not recorded"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def pre(value, empty="Not recorded."):
    value = text_value(value) if value is not None else ""
    # Keep captured spaces visible while avoiding trailing whitespace in HTML source.
    encoded = esc(value if value else empty).replace(' \n', '&#32;\n')
    return f'<pre>{encoded}</pre>'


def read_json(path, warnings, default):
    if not path.exists():
        warnings.append(f"Missing input: {path.name}")
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        warnings.append(f"Could not read {path.name}: {error}")
        return default


def record_path(root, value, default):
    path = Path(value) if isinstance(value, str) and value else default
    return path if path.is_absolute() else root / path


def raw_record(path, expected_id, warnings):
    data = read_json(path, warnings, {}) if path.exists() else {}
    if not isinstance(data, dict):
        warnings.append(f"Ignored non-object raw record: {path.name}")
        return {}
    if data.get("id") not in (None, expected_id):
        warnings.append(f"Raw ID mismatch in {path.name}; raw fallback was ignored.")
        return {}
    return data


def prepare_record(record, protocol, origin, raw_path=None):
    record["_origin"] = origin
    record["_recorded"] = origin != "No record"
    record["_raw_capture"] = str(raw_path) if raw_path else None
    record.setdefault("status", "pending")
    record["_prompt_from_protocol"] = record.get("_prompt_from_protocol", not bool(record.get("prompt")))
    if record["_prompt_from_protocol"]:
        record["prompt"] = protocol.get("prompts", {}).get(record["condition"], "")
    return record


def load_attempts(root, protocol, warnings):
    path = root / "attempts.json"
    if not path.exists():
        return None
    records = read_json(path, warnings, [])
    if isinstance(records, dict):
        records = records.get("attempts", [])
    if not isinstance(records, list):
        warnings.append("attempts.json must be an array or an object containing an attempts array.")
        return None
    slots = {item[0]: item[1:] for item in SLOTS}
    indexed = {}
    for record in records:
        if not isinstance(record, dict) or not (record.get("id") or record.get("attempt_id")):
            warnings.append("Ignored an attempt without an ID.")
            continue
        attempt_id = record.get("attempt_id") or record["id"]
        slot = record.get("slot_id") or next((key for key in slots if attempt_id == key or attempt_id.startswith(key + "-")), None)
        if slot not in slots:
            warnings.append(f"Ignored attempt with an unrecognized plan slot: {attempt_id}")
            continue
        if attempt_id in indexed:
            warnings.append(f"Duplicate actual submission {attempt_id}; counted once, using its last entry.")
        path = record_path(root, record.get("raw_file"), Path("records") / f"{attempt_id}.json")
        raw = raw_record(path, attempt_id, warnings)
        merged = {**raw, **record, "id": attempt_id, "slot_id": slot,
                  "platform": slots[slot][0], "condition": slots[slot][1]}
        indexed[attempt_id] = prepare_record(merged, protocol, "attempts.json + public record" if raw else "attempts.json",
                                               os.path.relpath(path, root) if raw else None)
    return list(indexed.values())


def load_data(root):
    warnings = []
    protocol = read_json(root / "protocol.json", warnings, {})
    if not isinstance(protocol, dict):
        warnings.append("protocol.json is not an object; its content was not interpreted.")
        protocol = {}
    attempts = load_attempts(root, protocol, warnings)
    attempt_index = {record["id"]: record for record in attempts or []}
    records = read_json(root / "runs.json", warnings, [])
    if isinstance(records, dict):
        records = records.get("runs", [])
    if not isinstance(records, list):
        warnings.append("runs.json must be an array or an object containing a runs array.")
        records = []
    expected = {item[0] for item in SLOTS}
    indexed = {}
    for record in records:
        if not isinstance(record, dict):
            warnings.append("Ignored a run entry that is not an object.")
            continue
        run_id = record.get("id") or record.get("slot_id")
        if run_id not in expected:
            warnings.append(f"Ignored unrecognized plan slot: {run_id!r}")
            continue
        if run_id in indexed:
            warnings.append(f"Duplicate slot {run_id} in runs.json; the last entry is displayed.")
        indexed[run_id] = record
    runs = []
    for run_id, platform, condition in SLOTS:
        main = indexed.get(run_id, {})
        selected_id = main.get("selected_attempt_id") or run_id
        selected = attempt_index.get(selected_id, {})
        raw_path = record_path(root, main.get("raw_file") or selected.get("raw_file"), Path("records") / f"{selected_id}.json")
        raw = raw_record(raw_path, selected_id, warnings)
        record = {**raw, **selected, **main}
        record.update(id=run_id, platform=platform, condition=condition, selected_attempt_id=selected_id)
        record["_prompt_from_protocol"] = not bool(main.get("prompt") or raw.get("prompt") or (
            selected.get("prompt") if not selected.get("_prompt_from_protocol") else None))
        origin = ("runs.json + selected public record" if main and (raw or selected) else
                  "runs.json" if main else "attempts.json / public-record fallback" if selected or raw else "No record")
        prepare_record(record, protocol, origin, os.path.relpath(raw_path, root) if raw else None)
        runs.append(record)
    return protocol, runs, attempts, warnings


def date_label(value, zone):
    if value is None or value == "":
        return "Not recorded"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return f"{value} (time zone not recorded)"
        try:
            target_zone = ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            target_zone = timezone.utc
            zone = "UTC"
        local = parsed.astimezone(target_zone)
        return local.strftime("%Y-%m-%d %H:%M:%S") + f" {zone} (UTC{local.strftime('%z')[:3]}:{local.strftime('%z')[3:]})"
    except (ValueError, TypeError):
        return str(value)


def time_html(value, zone):
    return f'<span title="{esc(value or "No original timestamp")}">{esc(date_label(value, zone))}</span>'


def external_link(url, label=None):
    url = str(url or "")
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("https", "http") or not parsed.netloc:
        return esc(label or url or "No URL recorded")
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label or url)}</a>'


def file_link(value, root, output_dir):
    if not isinstance(value, (str, Path)) or not str(value):
        return esc(text_value(value))
    value = str(value)
    if value.startswith(("http://", "https://")):
        return external_link(value)
    path = Path(value)
    path = path if path.is_absolute() else root / path
    href = quote(os.path.relpath(path, output_dir).replace(os.sep, "/"), safe="/.-_")
    missing = ' <span class="muted">(file unavailable)</span>' if not path.is_file() else ""
    return f'<a href="{esc(href)}">{esc(value)}</a>{missing}'


def recorded_status(record):
    return str(record.get("status") or "pending").lower()


def status_badge(record):
    status = recorded_status(record)
    style = "good" if complete_capture(record) else "bad" if status == "technical_failure" else "neutral"
    label = STATUS_LABELS.get(status, status)
    if status == "recovered":
        label += " · complete" if record.get("body_complete") is True else " · completeness unconfirmed"
    return f'<span class="badge {style}">{esc(label)}</span>'


def complete_capture(record):
    status = recorded_status(record)
    return ((status == "completed" and record.get("body_complete") is not False)
            or (status == "recovered" and record.get("body_complete") is True))


def assessment(record):
    result = {}
    for field in ("verdict", "assessment"):
        item = record.get(field)
        if isinstance(item, dict):
            result.update(item)
        elif item is not None:
            result["outcome"] = item
    return result


def metric_value(record, metric):
    reviewed = assessment(record)
    if metric in reviewed:
        return reviewed[metric]
    if metric == PRIMARY[record["condition"]] and reviewed.get("outcome") is not None:
        return reviewed["outcome"]
    if (metric == "exact_discovery" and record["condition"] != "B") or (
            metric == "unprompted_discovery" and record["condition"] != "C"):
        return "not_applicable"
    return "not_assessed"


def judgment(value, metric=None):
    if isinstance(value, dict):
        value = value.get("verdict", value.get("status", value.get("value")))
    if value is True:
        value = "pass"
    elif value is False:
        value = "fail"
    key = str(value or "not_assessed").lower().replace(" ", "_")
    labels = {
        "pass": ("Demonstrated", "good"), "fail": ("Not demonstrated", "neutral"),
        "indeterminate": ("Unclear", "neutral"), "unknown": ("Unknown", "neutral"),
        "not_assessed": ("Not assessed", "neutral"), "pending": ("Not assessed", "neutral"),
        "not_applicable": ("N/A", "muted"), "n/a": ("N/A", "muted"),
        "technical_failure": ("Technical failure", "bad"),
    }
    label, style = labels.get(key, (text_value(value), "neutral"))
    if metric == "github_only" and key in ("pass", "fail"):
        label = "GitHub only" if key == "pass" else "No"
    return label, style


def judgment_badge(value, metric=None):
    label, style = judgment(value, metric)
    return f'<span class="badge {style}">{esc(label)}</span>'


def search_value(record):
    for key in ("search_observed", "actual_search_observed"):
        if key in record and record[key] is not None:
            return record[key]
    return None


def search_label(record):
    value = search_value(record)
    if value is True:
        return "Observed"
    if value is False:
        return "Not observed"
    return "Not recorded" if value is None else text_value(value)


def key_table(data):
    if not isinstance(data, dict) or not data:
        return '<p class="muted">Not recorded.</p>'
    return '<dl class="keytable">' + "".join(
        f'<dt>{esc(str(k).replace("_", " "))}</dt><dd>{pre(v) if isinstance(v, (list, dict)) else esc(text_value(v))}</dd>'
        for k, v in data.items()) + '</dl>'


def list_notes(value):
    if value is None or value == "" or value == []:
        return '<p class="muted">No notes recorded.</p>'
    if isinstance(value, list):
        return '<ul>' + ''.join(f'<li>{esc(text_value(item))}</li>' for item in value) + '</ul>'
    return f'<p class="preserve">{esc(text_value(value))}</p>'


def link_table(items):
    if not isinstance(items, list) or not items:
        return '<p class="muted">No links recorded in this field.</p>'
    rows = []
    for item in items:
        if isinstance(item, str):
            item = {"url": item}
        if not isinstance(item, dict):
            rows.append(f'<tr><td colspan="4">{esc(text_value(item))}</td></tr>')
            continue
        url = item.get("url") or item.get("href") or ""
        label = item.get("title") or item.get("text") or item.get("label") or "Untitled source"
        domain = item.get("domain") or urlparse(str(url)).netloc or "Not recorded"
        kind = item.get("kind") or item.get("type") or "Not recorded"
        details = {k: v for k, v in item.items() if k not in {"url", "href", "title", "text", "label", "domain", "kind", "type"}}
        rows.append(f'<tr><td>{esc(label)}{pre(details) if details else ""}</td><td>{external_link(url)}</td><td>{esc(domain)}</td><td>{esc(kind)}</td></tr>')
    return '<div class="table-scroll"><table><thead><tr><th>Label / evidence</th><th>URL</th><th>Domain</th><th>Recorded role</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


def capture_links(record, root, output_dir):
    links = []
    for field in ("_raw_capture", "raw_file"):
        value = record.get(field)
        if isinstance(value, str) and value and value not in links:
            links.append(value)
    return ('<ul>' + ''.join(f'<li>{file_link(path, root, output_dir)}</li>' for path in links) + '</ul>'
            if links else '<p class="muted">No separate public record is available.</p>')


def capture_history(record):
    history = []
    for key in ("capture_history", "recovery_history", "captures"):
        items = record.get(key, [])
        if isinstance(items, dict):
            items = items.get("captures", items.get("events", [items]))
        if not isinstance(items, list):
            items = [items]
        history.extend(items)
    return history


def history_table(history, zone, root, output_dir):
    if not history:
        return '<p class="muted">No capture or recovery events recorded in this field.</p>'
    rows = []
    for event in history:
        if isinstance(event, str):
            rows.append(f'<tr><td colspan="5">{file_link(event, root, output_dir)}</td></tr>')
            continue
        if not isinstance(event, dict):
            rows.append(f'<tr><td colspan="5">{esc(text_value(event))}</td></tr>')
            continue
        when = event.get("captured_at") or event.get("recorded_at") or event.get("timestamp") or event.get("date")
        method = event.get("method") or event.get("capture_method") or "Not recorded"
        status = event.get("status") or "Not recorded"
        file = event.get("file") or event.get("raw_file") or event.get("capture_file")
        rest = {key: value for key, value in event.items() if key not in {
            "captured_at", "timestamp", "date", "method", "capture_method", "status", "file", "raw_file", "capture_file"}}
        rows.append(f'<tr><td>{time_html(when, zone)}</td><td>{esc(method)}</td><td>{esc(status)}</td><td>{file_link(file, root, output_dir) if file else "Not recorded"}</td><td>{pre(rest) if rest else "No additional notes."}</td></tr>')
    return '<div class="table-scroll"><table><thead><tr><th>Capture time</th><th>Method</th><th>Capture status</th><th>File</th><th>Evidence and notes</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


def source_sections(record):
    groups = {"cited": [], "retrieved": [], "unspecified": []}
    for key in ("cited_sources", "answer_citations"):
        if isinstance(record.get(key), list):
            groups["cited"].extend(record[key])
    for key in ("retrieval_sources", "source_panel_urls", "retrieval_panel_urls"):
        if isinstance(record.get(key), list):
            groups["retrieved"].extend(record[key])
    sources = record.get("sources", [])
    if isinstance(sources, dict):
        for key, items in sources.items():
            if not isinstance(items, list):
                continue
            group = "cited" if key in {"cited", "answer_citations", "body_citations"} else "retrieved" if key in {"retrieved", "retrieval", "panel", "retrieval_panel"} else "unspecified"
            groups[group].extend(items)
    elif isinstance(sources, list):
        for item in sources:
            role = item.get("role", item.get("kind", "")) if isinstance(item, dict) else ""
            group = "cited" if role in {"citation", "answer_citation", "body_citation", "citation_panel_match"} else "retrieved" if role in {"retrieval", "retrieved", "retrieval_panel", "source_panel"} else "unspecified"
            groups[group].append(item)
    answer_links = record.get("answer_links", record.get("links", []))
    answer_urls = {item.get("url") for item in answer_links if isinstance(item, dict)}
    cited_urls = {item.get("url") for item in groups["cited"] if isinstance(item, dict)}
    citation_html = (f'<p>The same {len(cited_urls)} URLs are listed above and explicitly recorded as citations. Their inclusion or exclusion roles are preserved per link.</p>'
                     if cited_urls and cited_urls == answer_urls else link_table(groups["cited"]))
    return ('<h4>Links in the answer</h4>' + link_table(answer_links)
            + '<h4>Explicitly recorded answer citations</h4>' + citation_html
            + '<h4>Retrieval-panel sources · not automatically answer citations</h4>' + link_table(groups["retrieved"])
            + ('<h4>Source-inventory scope</h4><blockquote>' + list_notes(record['source_inventory_notes']) + '</blockquote>' if record.get('source_inventory_notes') else '')
            + ('<h4>Other source records · role unspecified</h4>' + link_table(groups["unspecified"]) if groups["unspecified"] else ''))


def render_run(record, protocol, root, output_dir, anchor=None):
    run_id = record["id"]
    anchor = anchor or run_id
    zone = protocol.get("timezone", "UTC")
    metadata = {key: record[key] for key in (
        "model_label", "model_evidence", "reasoning_effort", "mode_label", "search_mode",
        "model", "reasoning", "mode", "search_enabled", "search_selection", "fresh_session", "personalization_disabled",
        "search_enabled_ui", "temporary", "private", "personalization", "personalize_using_x",
        "personalize_using_history", "custom_styles", "body_complete", "error",
        "main_page_error", "copy_result", "tool_activity", "selected_attempt_id", "attempt_number", "replacement_for",
        "capture_method", "capture_provenance", "memory_evidence", "settings_restored",
        "collector", "submitted_time_reported", "source_turn_started_at", "source_turn_completed_at",
        "condition_verification", "source_inventory_complete", "source_inventory_scope") if key in record}
    rows = []
    for metric, label in METRICS.items():
        value = metric_value(record, metric)
        details = {k: v for k, v in value.items() if k not in {"verdict", "status", "value"}} if isinstance(value, dict) else {}
        rows.append(f'<tr><th>{esc(label)}</th><td>{judgment_badge(value, metric)}</td><td>{pre(details) if details else "No supporting assessment recorded."}</td></tr>')
    reviewed = assessment(record)
    other_assessment = {k: v for k, v in reviewed.items() if k not in METRICS}
    prompt_note = "Planned prompt from protocol; a submitted prompt is not recorded." if record["_prompt_from_protocol"] else "Recorded prompt; retained verbatim."
    search_evidence = {k: record[k] for k in ("search_evidence", "search_queries", "search_query_labels", "source_panel_declared_hits", "searched_websites_reported", "search_status") if k in record}
    body = record.get("answer_text")
    submitted = record.get("submitted_at") or record.get("started_at") or record.get("submitted_time_reported")
    captured = record.get("captured_at") or record.get("finished_at")
    history = capture_history(record)
    incomplete_note = ('<blockquote><p><strong>Capture limitation:</strong> The response body is incomplete or unavailable. This does not establish that retrieval failed or that the target was not found.</p></blockquote>'
                       if recorded_status(record) in {"capture_incomplete", "incomplete", "technical_failure"} or record.get("body_complete") is False else '')
    return f'''<details class="run" id="{esc(anchor)}" open>
<summary><span>{esc(run_id)} · {esc(record['platform'])} · {esc(CONDITIONS[record['condition']])}</span>{status_badge(record)}</summary>
<div class="detail-body"><p class="muted">Input: {esc(record['_origin'])}. Submitted: {time_html(submitted, zone)}. Captured: {time_html(captured, zone)}.</p>
{incomplete_note}<blockquote>{list_notes(record.get('notes'))}</blockquote>
<h3>Recorded assessment</h3><div class="table-scroll"><table><thead><tr><th>Dimension</th><th>Judgment</th><th>Evidence / qualification</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
{key_table(other_assessment) if other_assessment else ''}
<details open><summary>Full prompt</summary><div class="detail-body"><p class="muted">{esc(prompt_note)}</p>{pre(record.get('prompt'), 'No prompt recorded.')}
{('<h4>Observed composer text</h4>' + pre(record['observed_composer_text'])) if record.get('observed_composer_text') is not None else ''}</div></details>
<details open><summary>Captured answer</summary><div class="detail-body">{pre(body, 'No assistant answer text captured. This is not evidence of no discovery.')}</div></details>
<details open><summary>Model, mode, search, and capture evidence</summary><div class="detail-body"><p><strong>Actual search:</strong> {esc(search_label(record))}</p>{key_table(metadata)}{key_table(search_evidence) if search_evidence else ''}
<p><strong>Original timestamps:</strong> {esc(text_value({'submitted_at': submitted, 'captured_at': captured}))}</p>
{('<p>Conversation: ' + external_link(record['conversation_url']) + '</p>') if record.get('conversation_url') else ''}
{capture_links(record, root, output_dir)}</div></details>
<details open><summary>Capture and recovery history</summary><div class="detail-body">{history_table(history, zone, root, output_dir)}</div></details>
<details open><summary>Returned answer links and recorded sources</summary><div class="detail-body"><blockquote><p>Answer links and retrieved sources have different roles. A URL appearing in either list does not by itself establish access to the X post or satisfy an assessment.</p></blockquote>
{source_sections(record)}</div></details>
</div></details>'''


def render_attempts(attempts, runs, protocol, root, output_dir):
    zone = protocol.get("timezone", "UTC")
    if attempts is None:
        return '<blockquote><p>attempts.json is not available. The actual submission total and supplemental-attempt history are not asserted from supporting capture files.</p></blockquote>'
    selected = {run["selected_attempt_id"]: run["id"] for run in runs if run["_recorded"]}
    rows, retained = [], []
    for attempt in attempts:
        attempt_id = attempt["id"]
        slot = selected.get(attempt_id)
        anchor = slot or f"attempt-{attempt_id}"
        disposition = "Selected for main comparison" if slot else "Historical / not selected"
        rows.append(f'<tr><th><a href="#{esc(anchor)}">{esc(attempt_id)}</a></th><td>{esc(attempt["slot_id"])}</td><td>{esc(disposition)}</td><td>{status_badge(attempt)}</td><td>{time_html(attempt.get("submitted_at") or attempt.get("started_at") or attempt.get("submitted_time_reported"), zone)}</td><td>{esc(search_label(attempt))}</td><td>{capture_links(attempt, root, output_dir)}</td></tr>')
        if slot:
            events = capture_history(attempt)
            if events:
                retained.append(f'<details open><summary>{esc(attempt_id)} · attempt-ledger capture history</summary><div class="detail-body">{history_table(events, zone, root, output_dir)}</div></details>')
        else:
            retained.append(render_run(attempt, protocol, root, output_dir, anchor=anchor))
    return ('<blockquote><p>attempts.json lists all actual submissions, including those selected for the six main slots. Its entries are counted once; they are not added to the six-slot count. Capturing, copying, reopening, or recovering an existing answer is not a new submission. Full records of non-selected attempts remain below; selected attempts link to their full records above.</p><p>Technical failure and incomplete body capture describe observation limits, not retrieval failure. A recovered capture is counted as complete only when body_complete is explicitly true.</p></blockquote>'
            + '<div class="table-scroll"><table><thead><tr><th>Actual submission</th><th>Plan slot</th><th>Selection</th><th>Status</th><th>Submitted</th><th>Search</th><th>Public record</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table></div>' + ''.join(retained))


CSS = '''
:root{--ink:#182b36;--muted:#5e717c;--line:#dce5e9;--bg:#f3f6f8;--paper:#fff;--accent:#176a76;--soft:#eaf4f4;--bad:#a94635}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:20px}body{margin:0;color:var(--ink);background:var(--bg);font:15px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--accent);text-decoration-thickness:1px;text-underline-offset:3px;overflow-wrap:anywhere}.layout{display:grid;grid-template-columns:235px minmax(0,1fr);min-height:100vh}nav{position:sticky;top:0;height:100vh;overflow:auto;background:#17343d;color:#edf7f7;padding:30px 22px}nav strong{display:block;font-size:19px;line-height:1.3;margin:0 0 12px}nav p{font-size:12px;color:#bed4db}nav a{display:block;color:#e0eeee;text-decoration:none;padding:7px 0;font-size:14px}nav .sub{padding-left:12px;font-size:12px;color:#b7d3db}main{max-width:1450px;width:100%;padding:36px 4vw 72px;min-width:0}h1{font-size:clamp(27px,3vw,42px);line-height:1.17;letter-spacing:-.035em;margin:8px 0 18px}h2{font-size:23px;line-height:1.3;margin:0 0 20px}h3{font-size:18px;margin:25px 0 12px}h4{font-size:15px;margin:18px 0 8px}p{margin:10px 0}section,.hero{background:var(--paper);border:1px solid var(--line);border-radius:15px;margin-bottom:24px;padding:26px;min-width:0}.eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);font-weight:750}.lead{font-size:17px;max-width:950px}.conclusions{padding-left:23px;margin:16px 0}.conclusions li{padding:4px 0}.counts{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:24px 0 4px}.count{padding:15px;background:var(--bg);border-radius:10px}.count strong{display:block;font-size:28px;line-height:1.25}.count span{font-size:12px;color:var(--muted)}blockquote{border-left:3px solid #7bafb5;background:var(--soft);margin:17px 0;padding:11px 17px;font-size:14px;color:#385560}blockquote p:first-child{margin-top:0}blockquote p:last-child{margin-bottom:0}.muted{color:var(--muted);font-size:13px}.preserve{white-space:pre-wrap}.table-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:9px}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}td,th{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}thead th{background:#edf3f5;white-space:nowrap}tbody tr:last-child>*{border-bottom:0}.matrix{min-width:1050px}.matrix td{min-width:105px}.badge{display:inline-block;white-space:normal;line-height:1.3;font-size:11px;font-weight:700;padding:5px 7px;border-radius:5px;background:#eef1f3;color:#52656f}.badge.good{background:#def1e8;color:#226246}.badge.bad{background:#fae7e2;color:var(--bad)}.badge.neutral{background:#edf0f3;color:#52656f}.badge.muted{background:transparent;color:#829099}.run{background:var(--paper);border:1px solid var(--line);border-radius:12px;margin:16px 0;overflow:hidden}details{border:1px solid var(--line);border-radius:8px;margin:15px 0}summary{cursor:pointer;font-weight:700;padding:15px 17px;background:#f7fafb;line-height:1.45}summary .badge{margin-left:13px}.detail-body{padding:3px 18px 18px}pre{font:13px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;margin:10px 0;padding:14px;background:#f4f7f8;border:1px solid #e5ecef;border-radius:7px;max-width:100%}.keytable{display:grid;grid-template-columns:minmax(160px,23%) minmax(0,1fr);font-size:13px;margin:14px 0}.keytable dt,.keytable dd{border-bottom:1px solid var(--line);padding:9px 11px;margin:0;overflow-wrap:anywhere}.keytable dt{font-weight:650;background:#f5f8f9}.keytable dd pre{margin:0}ul{padding-left:21px}.definitions{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.definition{background:var(--bg);border-radius:9px;padding:14px}.definition strong{display:block}.definition p{font-size:13px;margin-bottom:0}.footer{font-size:12px;color:var(--muted)}
@media(max-width:950px){.layout{grid-template-columns:190px minmax(0,1fr)}nav{padding:25px 17px}main{padding:24px}section,.hero{padding:20px}.counts{grid-template-columns:repeat(2,1fr)}.definitions{grid-template-columns:1fr}.keytable{grid-template-columns:145px minmax(0,1fr)}}
@media(max-width:650px){.layout{display:block}nav{position:static;height:auto;padding:16px 20px}nav strong{margin-bottom:6px}nav p{margin:5px 0}nav .links{display:flex;flex-wrap:wrap;gap:2px 17px}nav a{font-size:12px;padding:3px 0}nav .sub{display:none}main{padding:18px 12px 45px}section,.hero{padding:18px 15px;border-radius:11px}h1{font-size:30px}h2{font-size:22px}.lead{font-size:15px}.keytable{grid-template-columns:1fr}.keytable dt{border-bottom:0;padding-bottom:3px}.keytable dd{padding-top:3px}.detail-body{padding:2px 12px 14px}summary{padding:12px}.run summary .badge{margin-top:6px;margin-left:0;display:table}pre{font-size:12px;padding:11px}}
@media print{nav{display:none}.layout{display:block}main{max-width:none;padding:0}body{background:#fff}section,.hero,.run{break-inside:avoid;border-color:#bbb}a{color:inherit}summary{list-style:none}.table-scroll{overflow:visible}.matrix{min-width:0}table{font-size:9px}td,th{padding:5px}.counts{grid-template-columns:repeat(4,1fr)}}
'''


def build_report(protocol, runs, warnings, root, output, attempts=None):
    title = protocol.get("title") or "Stage 2: X post discovery and access"
    counts = Counter(recorded_status(run) for run in runs)
    completed = sum(complete_capture(run) for run in runs)
    failures = counts["technical_failure"]
    incomplete = counts["capture_incomplete"] + counts["incomplete"]
    recorded = sum(run["_recorded"] for run in runs)
    remaining = 6 - completed - failures
    attempt_count = len(attempts) if attempts is not None else None
    attempt_label = str(attempt_count) if attempt_count is not None else "Unknown"
    attempt_failures = sum(recorded_status(attempt) == "technical_failure" for attempt in attempts) if attempts is not None else None
    zone = protocol.get("timezone", "UTC")
    authored_findings = []
    for finding in protocol.get("findings", []) or []:
        if isinstance(finding, dict):
            authored_findings.append(f'<li><strong>{esc(finding.get("title", "Recorded finding"))}</strong> {esc(finding.get("detail", ""))}</li>')
        elif isinstance(finding, str):
            authored_findings.append(f'<li>{esc(finding)}</li>')
    authored_html = '<ul class="conclusions">' + ''.join(authored_findings) + '</ul>' if authored_findings else ''
    attempt_note = (f'{attempt_count} actual submissions are recorded across the six planned cells, including {attempt_failures} technical failure(s) in the attempt history.'
                    if attempt_count is not None else 'The actual submission total is not recorded in attempts.json.')
    conclusions = [f'<li><strong>{completed} of 6 selected records have complete captures; {failures} have a technical failure.</strong> {remaining} remain pending, submitted, incompletely captured, or otherwise unresolved. {esc(attempt_note)} These are collection counts, not retrieval success rates.</li>']
    for condition, label in CONDITIONS.items():
        comparisons = []
        for run in runs:
            if run["condition"] != condition:
                continue
            verdict, _ = judgment(metric_value(run, PRIMARY[condition]))
            if recorded_status(run) == "technical_failure":
                verdict = "technical failure; no retrieval conclusion"
            elif recorded_status(run) in {"capture_incomplete", "incomplete"} and verdict in {"Not assessed", "Unknown", "Unclear"}:
                verdict = "body capture incomplete; retrieval outcome unresolved"
            comparisons.append(f'{esc(run["platform"])}: {esc(verdict)}')
        conclusions.append(f'<li><strong>{esc(condition + " · " + label)}.</strong> {"; ".join(comparisons)}.</li>')
    matrix_rows = []
    for run in runs:
        cells = ''.join(f'<td>{judgment_badge(metric_value(run, metric), metric)}</td>' for metric in METRICS)
        selected_note = f'<br><span class="muted">Selected: {esc(run["selected_attempt_id"])}</span>' if run.get("selected_attempt_id") != run["id"] else ''
        matrix_rows.append(f'<tr><th><a href="#{esc(run["id"])}">{esc(run["condition"])} · {esc(run["platform"])}</a>{selected_note}</th><td>{status_badge(run)}</td>{cells}<td>{esc(search_label(run))}</td></tr>')
    design = protocol.get("design", {})
    target = protocol.get("target", {})
    preflight = protocol.get("preflight", {})
    preflight_html = ''.join(f'<h3>{esc(name.replace("_", " "))}</h3>{key_table(settings) if isinstance(settings, dict) else pre(settings)}' for name, settings in preflight.items()) if isinstance(preflight, dict) else pre(preflight)
    scoring = protocol.get("scoring", {})
    scoring_html = ''.join(f'<h3>{esc(condition)} · {esc(CONDITIONS[condition])}</h3><blockquote>{list_notes(scoring.get(condition, "No condition-specific rule recorded."))}</blockquote>' for condition in CONDITIONS)
    warnings_html = f'<blockquote><strong>Input warnings</strong>{list_notes(warnings)}</blockquote>' if warnings else ''
    facts = protocol.get("reference_facts", [])
    facts_html = '<ul>' + ''.join(f'<li><strong>{esc(item.get("id", "Reference"))}:</strong> {esc(item.get("fact", ""))}</li>' if isinstance(item, dict) else f'<li>{esc(item)}</li>' for item in facts) + '</ul>' if isinstance(facts, list) else pre(facts)
    restoration = protocol.get("restoration", protocol.get("postflight", protocol.get("settings_restoration")))
    restoration_html = key_table(restoration) if isinstance(restoration, dict) else list_notes(restoration) if restoration is not None else '<p class="muted">No separate post-test restoration confirmation is recorded. A planned restoration instruction is not confirmation that it happened.</p>'
    input_files = ''.join(f'<li>{file_link(name, root, output.parent)}</li>' for name in ("protocol.json", "runs.json", "attempts.json"))
    target_evidence = target.get("ground_truth_evidence")
    public_edition = protocol.get("public_edition", {})
    publication = protocol.get("publication", {})
    generated = (protocol.get("publication_date")
                 or (public_edition.get("published_on") if isinstance(public_edition, dict) else None)
                 or ((publication.get("published_on") or publication.get("date")) if isinstance(publication, dict) else None)
                 or protocol.get("test_date", "Not recorded"))
    nav_records = ''.join(f'<a class="sub" href="#{esc(run["id"])}">{esc(run["condition"])} · {esc(run["platform"])}</a>' for run in runs)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>{esc(title)}</title><link rel="canonical" href="{SITE_URL}"><meta name="description" content="GEO Learning Log Stage 2: six ChatGPT Search and Grok tests of direct URL access, exact-excerpt retrieval, and natural discovery, with redacted answers and all ten submissions."><meta property="og:type" content="website"><meta property="og:title" content="GEO Learning Log | Stage 2: Post discovery"><meta property="og:url" content="{SITE_URL}"><style>{CSS}</style></head>
<body><div class="layout"><nav aria-label="Report contents"><strong>GEO Learning Log</strong><p>Stage 2 · Public record<br>{esc(protocol.get('test_date', 'Date not recorded'))}</p><div class="links"><a href="#overview">Findings first</a><a href="#comparison">Six-cell comparison</a><a href="#conditions">Test conditions</a><a href="#method">Method and boundaries</a><a href="#records">Prompts and answers</a>{nav_records}<a href="#attempts">Attempts and recovery</a><a href="#inputs">Inputs and provenance</a><a href="../../index.html">Stage 1 report</a><a href="../02-post-discovery.md">Stage 2 data guide</a><a href="../03-question-sensitivity/">Stage 3: Question sensitivity</a><a href="https://github.com/helen-bird/geo-platform-observation">GitHub learning log</a></div></nav>
<main><header class="hero" id="overview"><div class="eyebrow">Stage 2 · Six planned cells · {esc(attempt_label)} actual submissions</div><h1>{esc(title)}</h1><p class="lead">A public record of direct access, exact-excerpt discovery, and unprompted discovery across ChatGPT Search and Grok.</p>
{authored_html}<ul class="conclusions">{''.join(conclusions)}</ul><blockquote><p><strong>Scope:</strong> The comparison contains six planned cells. Actual submissions and supplemental attempts are tracked separately below; a recovered capture is not a new query. There is no generalizable success rate. A supplied URL, a repeated excerpt, or facts recovered from GitHub do not demonstrate access to the X post.</p><p>Results below display recorded reviewer judgments. The generator does not classify answers from keywords, links, or a model's claims of verification. Missing assessments remain explicit.</p></blockquote>
<blockquote><p><strong>Redacted public edition:</strong> Questions, observed outcomes, returned source URLs, and failure history are preserved. Private conversation and share links, screenshots, account-interface material, local paths, and original diagnostic captures are excluded. Complete originals remain local. Captured non-English UI tokens are preserved as Unicode escape sequences.</p><p><a href="public-data.zip">Download Stage 2 public data</a> · <a href="data/publication-notes.json">Publication scope</a> · <a href="../02-post-discovery.md">Learning notes and data guide</a></p></blockquote>
<div class="counts"><div class="count"><strong>6</strong><span>Planned cells · {recorded} recorded</span></div><div class="count"><strong>{esc(attempt_label)}</strong><span>Actual submissions</span></div><div class="count"><strong>{completed}</strong><span>Complete selected captures</span></div><div class="count"><strong>{incomplete}</strong><span>Incomplete selected captures</span></div></div>{warnings_html}</header>
<section id="comparison"><h2>Six-cell comparison</h2><div class="definitions"><div class="definition"><strong>A · Direct URL</strong><p>The URL is supplied. The test concerns demonstrated access to the post's content.</p></div><div class="definition"><strong>B · Exact excerpt</strong><p>An exact continuous excerpt is supplied. Discovery requires the original post and matching retrieved content.</p></div><div class="definition"><strong>C · Natural query</strong><p>No target identity, URL, or excerpt is supplied. Other experiments and GitHub-only results are separate outcomes.</p></div></div>
<div class="table-scroll" style="margin-top:18px"><table class="matrix"><thead><tr><th>Condition · platform</th><th>Collection status</th>{''.join(f'<th>{esc(label)}</th>' for label in METRICS.values())}<th>Actual search</th></tr></thead><tbody>{''.join(matrix_rows)}</tbody></table></div>
<blockquote><p><strong>Reading the matrix:</strong> Demonstrated / Not demonstrated are explicit recorded judgments, not automatic scores. N/A marks a discovery task that the condition did not test. Unknown, Not assessed, and technical failure are not negative discovery evidence. “GitHub only” applies only when explicitly coded; it is never inferred from a GitHub URL.</p><p>Search enabled in the interface and search actually observed are different fields. External experiments described as “verified” inside an answer are still platform claims unless a separate assessment records verification.</p></blockquote></section>
<section id="conditions"><h2>Test conditions and account controls</h2><p>Protocol registered: {time_html(protocol.get('registered_at'), zone)}.</p>{preflight_html}<h3>Recorded post-test restoration</h3>{restoration_html}<blockquote><p>Temporary/private conversations and visible personalization controls reduce known account-context paths. They do not establish audited backend isolation or complete independence. See each run for its actual model, mode, search evidence, and any contamination evidence.</p></blockquote></section>
<section id="method"><h2>Method and interpretation limits</h2><h3>Design and execution order</h3>{key_table(design)}<blockquote><p><strong>Exact-excerpt verification:</strong> The B prompt calls the quotation a sentence. It is an 86-character continuous passage from the latter part of a longer sentence, verified character for character against the captured public post, including case, spaces, numbers, and punctuation. The question is preserved unchanged. No transcription mismatch was observed.</p></blockquote>{scoring_html}
<blockquote>{list_notes(scoring.get('capture_failure', 'Missing or incomplete capture is not coded as no discovery.'))}</blockquote><h3>Target and reference facts</h3><p>{external_link(target.get('url'), target.get('url', 'Target URL not recorded'))}</p>{key_table({k:v for k,v in target.items() if k not in ('url','ground_truth_evidence')})}
{('<p>Ground-truth evidence: ' + file_link(target_evidence, root, output.parent) + '</p>') if target_evidence else ''}{facts_html}<h3>Boundaries</h3><blockquote>{list_notes(protocol.get('limitations'))}<p>These tests cannot establish causal GEO effectiveness, stable indexing or retrieval rates, a platform's inherent superiority, or that an undiscovered post does not exist. The conditions provide different amounts of identifying information and should not be treated as equivalent tasks.</p></blockquote></section>
<section id="records"><h2>Full prompts, answers, and evidence</h2><blockquote><p>All sections are expanded initially. Public prompt and answer copies are escaped and preserve their wording apart from marked privacy edits. Original private capture files are excluded. A planned protocol prompt is identified when no submitted prompt was recorded.</p></blockquote>{''.join(render_run(run, protocol, root, output.parent) for run in runs)}</section>
<section id="attempts"><h2>All submissions, failures, and recovery history</h2>{render_attempts(attempts, runs, protocol, root, output.parent)}<h3>Stage-level capture and recovery events</h3>{history_table(capture_history(protocol), zone, root, output.parent)}</section>
<section id="inputs"><h2>Inputs and provenance</h2><ul>{input_files}</ul><blockquote><p>runs.json selects six planned slots. Each selected_attempt_id/raw_file points to that slot's actual submission in the public records; the selected attempt can supply missing fields. Original failures remain in attempts.json. That ledger contains all actual submissions and is not added to the six main rows. Supporting capture and recovery events are never counted as additional tests. Private screenshots, DOM and native-tool dumps are not included in this public edition. No network requests are made by this report or its generator.</p><p>Timestamps with an explicit offset are displayed in {esc(zone)} and their original values are preserved in each record. Capture time is not asserted to be the server's answer-completion time.</p></blockquote><p class="footer">Public edition date: {esc(generated)}. Rebuilt offline from versioned public records; the generator does not submit questions or publish changes.</p></section>
</main></div></body></html>'''


def write_public_archive(root, output_dir):
    """Package only the allowlisted public JSON tree with stable ZIP metadata."""
    archive_path = output_dir / "public-data.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*.json")):
            relative = path.relative_to(root)
            info = zipfile.ZipInfo("data/" + relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return archive_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=STAGE / "data")
    parser.add_argument("--output", type=Path, default=STAGE / "index.html")
    args = parser.parse_args()
    root = args.data_dir.resolve()
    output = args.output.resolve()
    protocol, runs, attempts, warnings = load_data(root)
    if warnings:
        raise ValueError("Public report inputs must be complete: " + "; ".join(warnings))
    document = build_report(protocol, runs, warnings, root, output, attempts=attempts)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    archive = write_public_archive(root, output.parent)
    total = len(attempts) if attempts is not None else "unknown"
    print(f"Wrote {output.relative_to(ROOT)} and {archive.relative_to(ROOT)}; "
          f"6 planned cells; {total} actual submissions; {len(warnings)} input warnings.")


if __name__ == "__main__":
    main()
