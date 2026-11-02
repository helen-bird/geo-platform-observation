#!/usr/bin/env python3
"""Build an offline GEO observation report from captured, manually coded runs.

No network requests or inferred experimental observations are made here.
Usage: python3 scripts/build_report.py [--input data/runs.json] [--attempts data/attempts.json]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
QUESTION_LABELS = {"Q1": "Discover learning resources", "Q2": "Find empirical research", "Q3": "Find practical tutorials and creators"}
STATUS_LABELS = {"completed": "Complete", "blocked": "Blocked", "incomplete": "Incomplete"}
METRICS = (("mention", "Mention · Explicitly named"), ("citation", "Citation · Own content cited"), ("recommendation", "Recommendation · Actively recommended"))


def text(value):
    if value is None or value == "":
        return "Not recorded"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def h(value):
    # Preserve raw non-English UI evidence as literal JSON Unicode escapes.
    displayed = re.sub(r"[\u3000-\u303f\u3400-\u9fff\uf900-\ufaff\uff00-\uffef]", lambda match: json.dumps(match.group(), ensure_ascii=True)[1:-1], text(value))
    return escape(displayed, quote=True)


def display_timestamp(value):
    if not value:
        return "Not recorded"
    original = str(value)
    try:
        parsed = datetime.fromisoformat(original[:-1] + "+00:00" if original.endswith("Z") else original)
    except ValueError:
        return original + " (as recorded)"
    if parsed.tzinfo is None:
        return original + " (timezone not specified)"
    return parsed.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S UTC+8")


def key(value):
    return " ".join(str(value or "").split()).casefold()


EFFORT_PATTERN = re.compile(r"\b(extra[\s_-]*high|xhigh|medium|high|low|minimal|none|max|ultra)\b|\u6781\u9ad8|\u4e2d\u7b49", re.I)
EFFORT_LABELS = {"extrahigh": "Extra High", "xhigh": "Extra High", "\u6781\u9ad8": "Extra High", "medium": "Medium", "\u4e2d\u7b49": "Medium", "high": "High", "low": "Low", "minimal": "Minimal", "none": "None", "max": "Max", "ultra": "Ultra"}


def known_condition_value(value):
    if value is None or value == "":
        return None
    value = str(value).strip()
    if value.startswith(("\u672a\u62ab\u9732", "\u672a\u8bb0\u5f55", "\u672a\u77e5")) or re.search(r"\b(?:not disclosed|not recorded|unknown)\b", key(value)) or key(value) == "n/a":
        return None
    return value


def run_conditions(run):
    """Compare recorded UI conditions, without claiming backend-model identity."""
    effort = next((known_condition_value(run.get(field)) for field in ("reasoning_effort", "thinking_effort", "effort_label", "thinking_label", "reasoning_label") if known_condition_value(run.get(field))), None)
    mode = known_condition_value(run.get("mode_label"))
    effort_from = "explicit_field" if effort else None
    if not effort and mode:
        match = EFFORT_PATTERN.search(mode)
        if match:
            effort = match.group()
            effort_from = "mode_label"
    if effort:
        normalized = re.sub(r"[\s_-]", "", effort).casefold()
        effort = EFFORT_LABELS.get(normalized, effort)
    mode_base = EFFORT_PATTERN.sub("", mode).strip(" ·•/-_") if mode else None
    model = known_condition_value(run.get("model_label"))
    model_comparison = re.sub(r"[\uff08(](?:\u754c\u9762\u9009\u62e9\u6807\u7b7e|\u754c\u9762\u6807\u7b7e|UI(?: selection)? label)[\uff09)]", "", model, flags=re.I).strip() if model else None
    date_recorded = known_condition_value(run.get("date_local"))
    date_from_submit = None
    if run.get("started_at"):
        try:
            stamp = str(run["started_at"])
            parsed = datetime.fromisoformat(stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp)
            if parsed.tzinfo is not None:
                date_from_submit = parsed.astimezone(timezone(timedelta(hours=8))).date().isoformat()
        except ValueError:
            pass
    return {"run_id": run.get("id"), "platform": run.get("platform"), "question_id": run.get("question_id"), "repeat": run.get("repeat"), "status": run.get("status"), "test_date": date_recorded or date_from_submit, "date_basis": "date_local" if date_recorded else "started_at converted to UTC+8" if date_from_submit else None, "date_from_submit": date_from_submit, "date_conflict": bool(date_recorded and date_from_submit and date_recorded != date_from_submit), "model_label": model, "model_comparison": model_comparison, "reasoning_effort": effort, "effort_basis": effort_from, "mode_label": mode, "mode_comparison": mode_base}


def compare_conditions(first, second):
    conditions = [run_conditions(first), run_conditions(second)]
    fields = (("test_date", "Test date"), ("model_comparison", "Model label"), ("reasoning_effort", "Reasoning effort"), ("mode_comparison", "UI mode"))
    differences, unknown = [], []
    for field, label in fields:
        a, b = conditions[0][field], conditions[1][field]
        if a is None or b is None:
            unknown.append(label)
        elif key(a) != key(b):
            differences.append({"field": field, "label": label, "first": a, "second": b})
    if differences:
        status, label = "different", "Different conditions; descriptive comparison only"
    elif unknown or any(c["date_conflict"] for c in conditions):
        status, label = "not_fully_observable", "Incomplete condition information; descriptive comparison only"
    else:
        status, label = "same_observed", "Recorded UI conditions match; backend conditions were not independently verified"
    return {"status": status, "label": label, "differences": differences, "unknown_fields": unknown, "runs": conditions}


def summarize_conditions(runs):
    records = [run_conditions(run) for run in runs]
    platforms = []
    for platform in sorted({str(c["platform"] or "Not recorded") for c in records}):
        selected = [c for c in records if str(c["platform"] or "Not recorded") == platform]
        values = {field: sorted({c[field] for c in selected if c[field]}, key=key) for field in ("test_date", "model_comparison", "reasoning_effort", "mode_comparison")}
        changed_fields = [field for field in ("model_comparison", "reasoning_effort", "mode_comparison") if len(values[field]) > 1]
        platforms.append({"platform": platform, "values": values, "changed_fields": changed_fields, "records": selected})
    dates = sorted({c["test_date"] for c in records if c["test_date"]})
    return {"scope": "currently selected main records, including incomplete positions; timestamps refer to submission, not recovery", "dates": dates, "cross_day": len(dates) > 1, "platforms": platforms, "date_conflict_run_ids": [c["run_id"] for c in records if c["date_conflict"]]}


def safe_url(value):
    value = str(value or "").strip()
    parsed = urlparse(value)
    if parsed.scheme.lower() in ("https", "http") and parsed.netloc:
        return value
    return None


def link(value, label=None):
    url = safe_url(value)
    if not url:
        return h(label if label is not None else value)
    return f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{h(label if label is not None else url)}</a>'


def local_link(value, label):
    if not value:
        return ""
    value = str(value)
    # Captured file paths are local references, never script/data URLs.
    if urlparse(value).scheme:
        return link(value, label)
    return f'<a href="{escape(value, quote=True)}">{h(label)}</a>'


def flag(value):
    if value is True:
        return '<span class="flag yes">Yes</span>'
    if value is False:
        return '<span class="flag no">No</span>'
    return '<span class="flag unknown">Undetermined</span>'


def mapping_label(value):
    if value is True:
        return "Confirmable citation links checked; see each observation for the matching method"
    if value is False:
        return "Incomplete: some internal citations are not mapped to URLs"
    return "Mapping completeness not recorded"


def personalization_evidence(run):
    supplied = run.get("personalization_evidence")
    if supplied:
        return str(supplied)
    return None


def capture_provenance(run):
    value = run.get("capture_provenance")
    return value if isinstance(value, dict) else {}


def uses_read_thread_preview(run):
    values = [run.get("capture_method"), capture_provenance(run), run.get("capture_history")]
    return any("read_thread" in text(value).casefold() for value in values)


def capture_method(run):
    return capture_provenance(run).get("method") or run.get("capture_method")


def memory_evidence(run):
    value = run.get("memory_evidence") or []
    return value if isinstance(value, list) else [value]


def source_partitions(run):
    """Keep retrieval evidence separate from answer links; never infer C/M/R."""
    answer, retrieval, unknown = [], list(run.get("retrieval_sources") or []), []
    retrieval_kinds = {"search_source_panel", "source_panel", "retrieved_source", "retrieval_source", "search_result", "source_panel_web_results_not_all_inline_citations"}
    answer_kinds = {"inline_citation", "answer_source_link", "text_link", "body_link", "markdown_link", "answer_link", "inline_link", "explicit_url", "answer_text_link", "citation_panel_match"}
    for source in run.get("sources") or []:
        if not isinstance(source, dict):
            unknown.append({"url": source})
            continue
        kind = str(source.get("kind") or source.get("source_kind") or "")
        if kind in retrieval_kinds:
            retrieval.append(source)
        elif kind in answer_kinds or source.get("in_answer") is True:
            answer.append(source)
        elif "retrieval_sources" in run and not kind:
            # New manifest contract: sources is answer-observed links only.
            answer.append(source)
        else:
            unknown.append(source)
    return {"answer": answer, "retrieval": retrieval, "unknown": unknown}


def normalize_capture_history(value):
    if isinstance(value, list):
        return {"captures": value, "corrections": [], "notes": []}
    if not isinstance(value, dict):
        return {"captures": [], "corrections": [], "notes": []}
    return {"captures": value.get("captures") or value.get("records") or value.get("capture_history") or [], "corrections": value.get("corrections") or value.get("diagnostic_corrections") or [], "notes": value.get("notes") or []}


def source_domain(source):
    return source.get("domain") or urlparse(str(source.get("url") or "")).hostname or "Not recorded"


def rows_for_run(run):
    """Entity presence per answer; duplicate rows never multiply frequency."""
    merged = {}
    for obs in run.get("observations") or []:
        entity_key = key(obs.get("entity"))
        if not entity_key:
            continue
        row = merged.setdefault(entity_key, {"entity": obs["entity"], "mention": None, "citation": None, "recommendation": None})
        for metric, _ in METRICS:
            value = obs.get(metric)
            if value is True:
                row[metric] = True
            elif value is False and row[metric] is None:
                row[metric] = False
    return merged


def summarize_insights(runs):
    """Count coded entity-answer observations, never retrieved pages or failed attempts."""
    completed = [r for r in runs if r.get("status") == "completed"]
    platforms = sorted({r["platform"] for r in completed})
    platform_rows, question_rows, cross_platform = [], [], []

    def counts(selected):
        observations = [o for r in selected for o in rows_for_run(r).values()]
        patterns = Counter()
        for o in observations:
            if any(o[k] is None for k in ("citation", "mention", "recommendation")):
                patterns["unknown"] += 1
            else:
                patterns["".join(k[0].upper() for k in ("citation", "mention", "recommendation") if o[k]) or "none"] += 1
        totals = {k: sum(o[k] is True for o in observations) for k in ("citation", "mention", "recommendation")}
        cited_recommendations = sum(o["recommendation"] is True and o["citation"] is True for o in observations)
        return {"answer_count": len(selected), "observation_count": len(observations), "totals": totals,
                "patterns": dict(patterns), "cited_recommendations": cited_recommendations,
                "recommendations_without_own_citation": sum(o["recommendation"] is True and o["citation"] is False for o in observations),
                "recommendations_with_unknown_citation": sum(o["recommendation"] is True and o["citation"] is None for o in observations),
                "own_citation_coverage": cited_recommendations / totals["recommendation"] if totals["recommendation"] else None}

    for platform in platforms:
        selected = [r for r in completed if r["platform"] == platform]
        platform_rows.append({"platform": platform, **counts(selected)})
    for q in QUESTION_LABELS:
        sets, names = {}, {}
        sufficient = True
        for platform in platforms:
            selected = [r for r in completed if r["platform"] == platform and r["question_id"] == q]
            question_rows.append({"platform": platform, "question_id": q, **counts(selected)})
            sufficient &= len(selected) == 2 and {r.get("repeat") for r in selected} == {1, 2}
            sets[platform] = set()
            for r in selected:
                for entity_key, o in rows_for_run(r).items():
                    names[entity_key] = o["entity"]
                    if o["recommendation"] is True:
                        sets[platform].add(entity_key)
                    elif o["recommendation"] is None:
                        sufficient = False
        if len(platforms) == 2:
            a, b = (sets[p] for p in platforms)
            union, shared = a | b, a & b
            cross_platform.append({"question_id": q, "platforms": platforms, "complete_pairs": sufficient,
                "recommendation_counts": {p: len(sets[p]) for p in platforms}, "intersection": len(shared),
                "union": len(union), "jaccard": len(shared) / len(union) if union and sufficient else None,
                "shared_entities": sorted((names[k] for k in shared), key=str.casefold)})
    return {"scope": "Completed selected main answers only; one coded entity per answer. Not a census of products, publishers or all source URLs.",
            "observation_count": sum(p["observation_count"] for p in platform_rows),
            "platforms": platform_rows, "by_question": question_rows, "cross_platform": cross_platform}


def aggregate(runs, attempts=None, capture_history=None):
    attempts = attempts or []
    completed = [r for r in runs if r.get("status") == "completed"]
    groups = defaultdict(list)
    # Preserve every planned platform/question position even when no answer is usable.
    platforms = sorted({str(r.get("platform") or "Not recorded") for r in runs})
    for platform in platforms:
        for question_id in QUESTION_LABELS:
            groups[(platform, question_id)]
    for run in completed:
        groups[(str(run.get("platform") or "Not recorded"), str(run.get("question_id") or "Not recorded"))].append(run)
    groups_out = []
    for (platform, question_id), group in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0])):
        entities = {}
        for run in group:
            for entity_key, obs in rows_for_run(run).items():
                row = entities.setdefault(entity_key, {"entity": obs["entity"], **{metric: 0 for metric, _ in METRICS}})
                for metric, _ in METRICS:
                    row[metric] += int(obs[metric] is True)
        frequencies = sorted(entities.values(), key=lambda x: (-x["recommendation"], -x["mention"], -x["citation"], key(x["entity"])))
        by_repeat = defaultdict(list)
        for run in group:
            by_repeat[str(run.get("repeat"))].append(run)
        overlap = None
        coding_incomplete = any(not (r.get("observations") or []) or any(o.get("recommendation") is not True and o.get("recommendation") is not False for o in (r.get("observations") or [])) for r in group)
        if len(by_repeat.get("1", [])) == 1 and len(by_repeat.get("2", [])) == 1:
            first, second = by_repeat["1"][0], by_repeat["2"][0]
            set_a = {k for k, v in rows_for_run(first).items() if v["recommendation"] is True}
            set_b = {k for k, v in rows_for_run(second).items() if v["recommendation"] is True}
            union = set_a | set_b
            overlap = {"run_ids": [first.get("id"), second.get("id")], "recommendation_coding_incomplete": coding_incomplete, "repeat_1_recommendations": len(set_a), "repeat_2_recommendations": len(set_b), "intersection": len(set_a & set_b), "union": len(union), "jaccard": len(set_a & set_b) / len(union) if union and not coding_incomplete else None, "shared_entities": sorted((entities[k]["entity"] for k in set_a & set_b), key=str.casefold)}
            overlap["condition_comparison"] = compare_conditions(first, second)
        groups_out.append({"platform": platform, "question_id": question_id, "completed_runs": len(group), "recommendation_coding_incomplete": coding_incomplete, "frequencies": frequencies, "repeat_overlap": overlap})
        groups_out[-1]["run_conditions"] = [run_conditions(run) for run in group]
    all_records = runs + attempts
    history = normalize_capture_history(capture_history)
    return {"planned_runs": 12, "recorded_runs": len(runs), "total_prompts": len(all_records), "historical_attempts": len(attempts), "completed_runs": len(completed), "status_counts": dict(Counter(r.get("status") or "unrecorded" for r in runs)), "attempt_status_counts": dict(Counter(r.get("status") or "unrecorded" for r in attempts)), "attempt_history": [{k: r.get(k) for k in ("id", "slot_id", "attempt_id", "platform", "question_id", "repeat", "date_local", "status", "replacement_for", "attempt_number")} for r in attempts], "capture": {"scope": "main runs and historical attempts; frequency statistics use completed main runs only; additional captures are not additional prompts", "read_thread_preview_run_ids": [r.get("id") for r in all_records if uses_read_thread_preview(r)], "provenance_run_ids": [r.get("id") for r in all_records if capture_provenance(r)], "capture_history_count": len(history["captures"]), "diagnostic_correction_count": len(history["corrections"]), "incomplete_citation_mapping_run_ids": [r.get("id") for r in all_records if r.get("citation_mapping_complete") is False], "observed_personalization": [{"run_id": r.get("id"), "evidence": personalization_evidence(r)} for r in all_records if personalization_evidence(r)], "observed_memory_evidence": [{"run_id": r.get("id"), "evidence": memory_evidence(r)} for r in all_records if memory_evidence(r)], "source_counts": [{"run_id": r.get("id"), **{kind: len(rows) for kind, rows in source_partitions(r).items()}} for r in all_records]}, "groups": groups_out}


CSS = """
:root{color-scheme:light;--ink:#132c38;--muted:#5b7078;--line:#d9e1e4;--surface:#f2f6f6;--accent:#176b62;--light:#d4ebe5;--blue:#547997;--warm:#ab7c35}
*{box-sizing:border-box}body{margin:0;background:#fff;color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}main{max-width:1200px;margin:auto;padding:52px 36px 72px}h1{font-size:36px;line-height:1.2;letter-spacing:-.04em;font-weight:650;margin:14px 0 18px}h2{font-size:24px;font-weight:600;margin:0 0 16px}h3{font-size:18px;font-weight:600;margin:0 0 10px}p{margin:0 0 14px}a{color:var(--accent);text-underline-offset:3px;overflow-wrap:anywhere}header{border-bottom:2px solid var(--ink);padding-bottom:25px}.eyebrow{font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);font-weight:650}.lede{max-width:880px;font-size:18px}.meta,.muted{color:var(--muted)}.meta{font-size:14px}.section{margin-top:40px}.notice{margin-top:22px;padding:18px 20px;background:var(--surface);border-left:4px solid var(--accent)}.note{font-size:14px;color:var(--muted)}.stats{display:flex;flex-wrap:wrap;gap:30px;margin:26px 0 0}.stat{min-width:130px}.stat strong{font-size:30px;line-height:1.1;display:block;font-weight:600;font-variant-numeric:tabular-nums}.stat span{font-size:13px;color:var(--muted)}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;text-align:left;font-size:14px}th{font-weight:600;color:var(--muted);background:var(--surface)}th,td{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top}td{overflow-wrap:anywhere}.compact th,.compact td{padding:8px 10px}.nowrap{white-space:nowrap}.flag{display:inline-block;font-size:12px;white-space:nowrap;border-radius:4px;padding:1px 6px}.yes{background:var(--light);color:#134a43}.no{background:#edf0f1;color:#58666d}.unknown{background:#f8eddb;color:#805c24}.status{font-size:12px;border:1px solid var(--line);border-radius:5px;padding:3px 8px;white-space:nowrap}.done{color:var(--accent);border-color:#a1c8bd}.blocked{color:#895f20;border-color:#dec491}.chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:32px}.chart-panel{min-width:0;border-top:1px solid var(--line);padding-top:18px}.chart-row{display:grid;grid-template-columns:minmax(100px,1fr) minmax(85px,1fr) 36px;gap:10px;align-items:center;margin:10px 0;font-size:14px}.bar-track{height:12px;background:var(--surface)}.bar-fill{height:100%;background:var(--accent)}.bar-value{text-align:right;font-variant-numeric:tabular-nums}.legend{display:flex;flex-wrap:wrap;gap:18px;font-size:13px;color:var(--muted);margin-bottom:14px}.dot{display:inline-block;width:9px;height:9px;background:var(--accent);margin-right:5px}.chart-caption{font-size:13px;color:var(--muted)}details{margin:16px 0;border-top:1px solid var(--line);padding-top:16px}summary{cursor:pointer;font-weight:600;list-style-position:outside;margin-left:18px}summary .muted{font-weight:400;font-size:13px;margin-left:10px}.run-body{padding:16px 0 12px}.run-meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px 20px;margin:0 0 20px}.run-meta div{min-width:0;overflow-wrap:anywhere}.run-meta dt{font-size:12px;color:var(--muted)}.run-meta dd{margin:0;font-size:14px}.question{padding:16px 18px;background:var(--surface);font-size:15px;margin-bottom:18px;white-space:pre-wrap;overflow-wrap:anywhere}.raw-answer{white-space:pre-wrap;overflow-wrap:anywhere;font-family:inherit;line-height:1.65;font-size:14px;padding:16px 18px;background:var(--surface);margin:12px 0 0}.links{display:flex;gap:18px;flex-wrap:wrap;font-size:14px;margin:10px 0 16px}.evidence{white-space:pre-wrap;font-size:13px}.source-list{margin:0;padding-left:20px}.source-list li{margin:7px 0}.empty{color:var(--muted);padding:12px 0}.cmr-table th:first-child{min-width:150px}.cmr-table th:nth-last-child(2){min-width:220px}.small{font-size:13px}footer{margin-top:45px;padding-top:20px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
@media(max-width:760px){main{padding:28px 18px 48px}h1{font-size:29px}.lede{font-size:16px}.chart-grid{grid-template-columns:1fr;gap:22px}.run-meta{grid-template-columns:repeat(2,minmax(0,1fr))}.stats{gap:20px}.stat{min-width:100px}.stat strong{font-size:25px}th,td{padding:9px}.section{margin-top:32px}.chart-row{grid-template-columns:minmax(100px,1.15fr) minmax(70px,1fr) 28px;font-size:13px}.notice{padding:14px 16px}}
@media print{main{max-width:none;padding:15px}details{break-inside:avoid}.chart-panel{break-inside:avoid}a{color:inherit}details:not([open])>.run-body{display:block}.table-wrap{overflow:visible}header{break-after:avoid}.section{margin-top:25px}}
.overlap-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}.overlap-item{margin:16px 0 0}.overlap-label{display:flex;justify-content:space-between;gap:12px;font-size:14px;margin-bottom:6px}.overlap-label strong{font-size:18px;font-variant-numeric:tabular-nums}.overlap-item .bar-track{height:10px}.overlap-detail{font-size:12px;color:var(--muted);margin-top:4px}.compact-notice{margin-top:18px;padding:12px 16px;font-size:14px}.compact-notice p{margin:0}.detail-section>summary{font-size:18px}.detail-content{padding-top:16px}.section-lead{max-width:900px}
@media(max-width:760px){.overlap-grid{grid-template-columns:1fr;gap:8px}.overlap-grid .chart-panel{padding-top:12px}.overlap-item{margin-top:10px}}
.report-nav{display:flex;gap:16px;flex-wrap:wrap;margin:24px 0 0;font-size:14px}.finding-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}.finding-panel{border-top:2px solid var(--accent);padding-top:16px;min-width:0}.finding-number{font-size:36px;line-height:1.2;font-weight:650;font-variant-numeric:tabular-nums;margin:12px 0}.compare-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;margin-top:24px}.compare-panel{padding:20px;background:var(--surface);min-width:0}.compare-panel .bar-track{background:#dce6e6}.metric-defs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin:20px 0}.metric-defs dt{font-weight:650}.metric-defs dd{margin:6px 0 0;font-size:14px;color:var(--muted)}.cmr-legend{display:flex;gap:12px 20px;flex-wrap:wrap;font-size:13px;margin:18px 0}.cmr-swatch{display:inline-block;width:12px;height:12px;margin-right:6px;vertical-align:-1px}.cmr-stack{display:flex;height:32px;overflow:hidden;background:var(--surface);margin:10px 0}.cmr-segment{display:flex;justify-content:center;align-items:center;font-size:12px;font-weight:600;color:white;min-width:0;overflow:hidden}.distribution-row{margin:24px 0}.distribution-label{display:flex;justify-content:space-between;gap:16px;font-size:15px}.distribution-counts{font-size:13px;color:var(--muted);margin:0}.interpretation{border-left:4px solid var(--warm);background:#faf5eb;padding:20px 22px;margin-top:28px}.interpretation h3{color:#75511c}.comparison-table th{white-space:nowrap}.case-table td:first-child{min-width:95px}.case-table td:last-child{min-width:230px}html{scroll-behavior:auto}section[id]{scroll-margin-top:24px}
@media(max-width:760px){.finding-grid,.compare-grid,.metric-defs{grid-template-columns:1fr;gap:16px}.finding-number{font-size:30px}.compare-panel{padding:16px}.report-nav{gap:10px 16px}.interpretation{padding:16px}.distribution-label{font-size:14px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
/* Editorial layout: a persistent outline, conclusions first, quoted notes. */
body{background:#f5f7f8}.report-shell{display:grid;grid-template-columns:232px minmax(0,1fr);max-width:1540px;margin:auto;background:white;min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;overflow-y:auto;padding:34px 18px 24px 24px;border-right:1px solid var(--line);background:#f7f9f9;scrollbar-width:thin}.sidebar-brand{display:block;color:var(--ink);font-size:21px;font-weight:750;text-decoration:none;letter-spacing:.02em;margin-bottom:30px}.sidebar-brand span{font-size:13px;font-weight:500;color:var(--muted);margin-left:8px}.toc-label{font-size:11px;font-weight:700;letter-spacing:.12em;color:#728087;margin:24px 10px 10px}.sidebar nav a{display:block;padding:8px 10px;margin:2px 0;border-radius:5px;text-decoration:none;font-size:13px;line-height:1.45;color:#475e67;border-left:2px solid transparent}.sidebar nav a:hover{background:#edf2f2;color:var(--ink)}.sidebar nav a[aria-current="location"]{background:#e5f0ed;color:#145e55;border-left-color:var(--accent);font-weight:700}.sidebar nav .record-link{font-size:11px;padding:5px 10px 5px 19px;color:#687a81}.record-links{border-left:1px solid var(--line);margin:8px 0 12px 10px}.sidebar-foot{font-size:11px;color:#7d8b90;margin:28px 10px 0;line-height:1.7}main{width:100%;max-width:1120px;margin:0;padding:48px clamp(24px,4vw,64px)80px;min-width:0}header{border-bottom:0;padding-bottom:0}h1{font-size:36px;letter-spacing:-.035em;margin:12px 0 14px}.lede{font-size:16px;color:var(--muted);max-width:800px}h2{font-size:25px;letter-spacing:-.025em;line-height:1.4}h3{line-height:1.45}.section{margin-top:58px;padding-top:26px;border-top:1px solid var(--line)}.section-kicker{font-size:11px;letter-spacing:.12em;color:var(--accent);font-weight:750;margin-bottom:8px}.executive-summary{border-top:0;margin-top:30px;padding-top:0}.executive-summary h2{font-size:29px;margin-bottom:20px}.conclusion-list{padding-left:22px;margin:0 0 24px;max-width:880px}.conclusion-list li{padding:0 0 0 6px;margin:0 0 18px;font-size:16px;line-height:1.85}.conclusion-list li::marker{color:var(--accent)}.conclusion-list strong{font-weight:750;color:var(--ink)}.section-conclusions{padding-left:22px;margin:0 0 24px}.section-conclusions li{margin:10px 0;padding-left:4px;line-height:1.8}.report-note,blockquote{margin:18px 0;padding:12px 16px;border-left:3px solid #c6d7d3;background:#f5f8f7;color:#5d7077;font-size:13px;line-height:1.75;font-style:normal;overflow-wrap:anywhere}.report-note p:last-child,blockquote p:last-child{margin-bottom:0}.report-note p{margin-bottom:8px}.report-note strong{color:#3e595f}.report-note.note{font-size:13px}.report-note.evidence{font-size:13px;color:#465d64}.report-note.notice{border-left-color:#9dbcb3;margin:18px 0}.report-note.interpretation{border-left-color:var(--warm);background:#faf7ef;color:#635c4e;padding:20px}.report-note.interpretation h3{color:#75511c}.report-note.interpretation strong{color:#5f4827}.experiment-meta{font-size:12px;margin:24px 0 0}.stats{gap:24px;margin:0}.stat strong{font-size:24px}.stat span{font-size:12px}.finding-number{font-size:34px}.finding-panel{border-top:2px solid #9ab8af;padding-top:16px}.compare-panel{background:#f4f7f6;border-top:2px solid #d7e4df}.compare-panel h3{font-size:16px}.finding-grid{gap:22px}.chart-caption.report-note{margin:10px 0 16px}.chart-panel{padding-top:20px}.chart-panel .note.report-note{font-size:12px}.chart-row{font-size:13px}.metric-defs{margin:0}.metric-defs dd{font-size:13px}.report-note.definition-note{padding:16px 18px}.distribution-row{margin:28px 0}.distribution-counts{font-size:12px}.cmr-stack{height:30px}.table-wrap{margin:18px 0 24px;border:1px solid #e0e7e6;border-radius:5px}table{font-size:13px}th{background:#f3f6f5;color:#49626b;font-size:12px}td,th{padding:12px 13px}.table-wrap tr:last-child td,.table-wrap tr:last-child th{border-bottom:0}td blockquote.report-note{font-size:11px;margin:8px 0 0;padding:7px 10px;border-left-width:2px;background:#f8faf9}details{margin:22px 0;border-top:1px solid #e0e7e6;padding-top:18px}summary{font-size:15px;color:var(--ink);margin-left:18px;padding-right:10px;line-height:1.6}summary::marker{color:#7b928c}.detail-section>summary{font-size:23px;letter-spacing:-.02em}.detail-content{padding-top:20px}.run-body{padding-top:20px}.run-meta{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 24px}.run-meta dd{font-size:12px}.raw-answer{font-size:13px;line-height:1.85;background:#fafbfb;border:1px solid #e6ecea;padding:20px}.links{font-size:12px}.question{font-size:14px;border-left:3px solid #96b6ac;background:#f2f7f5}.empty{font-size:13px}details[id],section[id],aside[id],blockquote[id]{scroll-margin-top:24px}.source-list{font-size:13px}footer{font-size:11px}
@media(max-width:1200px){.report-shell{grid-template-columns:200px minmax(0,1fr)}.sidebar{padding-left:16px;padding-right:12px}main{padding:34px 28px 64px}.finding-grid,.overlap-grid{grid-template-columns:1fr;gap:22px}.finding-number{font-size:30px}.chart-grid{grid-template-columns:1fr}.finding-panel>details{margin-top:12px}.finding-panel>p{margin-bottom:10px}h1{font-size:32px}}
@media(max-width:1000px){.report-shell{grid-template-columns:184px minmax(0,1fr)}.compare-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.metric-defs{grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.sidebar nav a{font-size:12px;padding:7px 8px}.sidebar nav .record-link{font-size:10px}.sidebar-brand{font-size:18px}.sidebar-brand span{display:block;margin-left:0;margin-top:3px}main{padding:32px 24px 60px}.run-meta{grid-template-columns:1fr}.conclusion-list li{font-size:15px}h1{font-size:29px}h2{font-size:23px}}
@media(max-width:700px){.compare-grid,.metric-defs{grid-template-columns:1fr}.report-shell{display:block}.sidebar{position:relative;height:auto;max-height:none;border-right:0;border-bottom:1px solid var(--line);padding:20px}.sidebar-brand{margin-bottom:12px}.sidebar-brand span{display:inline;margin-left:8px}.sidebar nav{display:grid;grid-template-columns:1fr 1fr;gap:3px 10px}.sidebar nav .toc-label{grid-column:1/-1;margin:14px 8px 6px}.sidebar nav .record-links{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr;margin-left:8px}.sidebar nav .record-link{font-size:10px}.sidebar-foot{display:none}main{padding:28px 20px 48px}h1{font-size:28px}.executive-summary h2{font-size:25px}.section{margin-top:40px;padding-top:22px}.executive-summary{margin-top:28px;padding-top:0}.conclusion-list{padding-left:18px}.conclusion-list li{padding-left:2px}.report-note{padding:11px 13px}.stats{gap:18px}.table-wrap{border-radius:0}.detail-section>summary{font-size:20px}}
@media print{.report-shell{display:block}.sidebar{display:none}main{padding:16px;max-width:none}.section{break-before:auto}blockquote{break-inside:avoid}.report-note{background:#fafafa}.raw-answer{white-space:pre-wrap}}
"""


class ReportDocumentFormatter(HTMLParser):
    """Apply report-wide editorial defaults without changing captured content."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output, self.stack = [], []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        in_quote = any(item[1] == "blockquote" for item in self.stack)
        method_context = any("method-notes" in item[2] for item in self.stack)
        is_note = bool(classes & {"note", "notice", "chart-caption", "evidence", "interpretation"}) or (tag == "p" and "small" in classes)
        safe_note_tag = tag in {"p", "div", "aside"} or (tag == "span" and self.stack and self.stack[-1][1] in {"td", "th", "div"})
        quote = not in_quote and ((safe_note_tag and is_note) or (tag == "p" and method_context))
        rendered = "blockquote" if quote else tag
        if quote:
            values["class"] = " ".join(filter(None, [values.get("class"), "report-note"]))
        if tag == "details":
            values["open"] = None
        attributes = "".join(f' {k}' if v is None else f' {k}="{escape(v, quote=True)}"' for k, v in values.items())
        self.output.append(f'<{rendered}{attributes}>')
        if tag not in self.VOID:
            self.stack.append((tag, rendered, classes))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            _, rendered, _ = self.stack.pop()
        else:
            rendered = tag
        self.output.append(f'</{rendered}>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        self.output.append(data)

    def handle_entityref(self, name):
        self.output.append(f'&{name};')

    def handle_charref(self, name):
        self.output.append(f'&#{name};')

    def handle_decl(self, decl):
        self.output.append(f'<!{decl}>')

    def handle_comment(self, data):
        self.output.append(f'<!--{data}-->')


def format_report_document(document):
    formatter = ReportDocumentFormatter()
    formatter.feed(document)
    formatter.close()
    if formatter.stack:
        raise ValueError(f'Unclosed report markup: {formatter.stack[-3:]}')
    return "".join(formatter.output)


def render_sidebar(runs):
    sections = [("conclusions", "Key findings"), ("main-findings", "Platform differences"),
                ("repeat-stability", "Observed repeat overlap"), ("cmr-distribution", "C/M/R distribution"),
                ("effect-limits", "Limits on GEO claims"), ("recommendation-frequency", "Recommendation frequency")]
    references = [("method", "Methods and limitations"), ("conditions", "Models and conditions"),
                  ("run-matrix", "Test record overview"), ("raw-records", "12 answer records"),
                  ("attempt-history", "Submission history"), ("capture-history", "Captures and corrections"),
                  ("reading-boundaries", "Interpretation limits")]
    def links(items):
        return "".join(f'<a href="#{target}">{h(label)}</a>' for target, label in items)
    records = "".join(f'<a class="record-link" href="#run-{i}">{"ChatGPT" if r.get("platform") == "ChatGPT Search" else h(r.get("platform"))} · {h(r.get("question_id"))} · Repeat {h(r.get("repeat"))}</a>' for i, r in enumerate(runs, 1))
    return f'<aside class="sidebar"><a class="sidebar-brand" href="#conclusions">GEO <span>Learning Log</span></a><nav aria-label="Report contents"><p class="toc-label">Main findings</p>{links(sections)}<p class="toc-label">Methods and evidence</p>{links(references)}<div class="record-links" aria-label="Answer record index">{records}</div></nav><p class="sidebar-foot">Findings with supporting charts<br>All sections expanded by default</p></aside>'


def render_executive_summary(findings):
    insights = findings["insights"]
    platforms = {p["platform"]: p for p in insights["platforms"]}
    q3 = next((q for q in insights["cross_platform"] if q["question_id"] == "Q3"), None)
    bullets = []
    if q3 and q3["jaccard"] is not None:
        bullets.append(f'<li><strong>The platforms differed most on Q3 recommended entities/resources.</strong> After combining both repeats for each platform, only {q3["intersection"]} / {q3["union"]} entities were shared, giving a cross-platform overlap of <b>{q3["jaccard"]:.1%}</b>. These are mixed entities/resources, not 20 individual creators: the shared items were GEO research (Aggarwal et al.) and The GEO Community.</li>')
    if all(p in platforms for p in ("ChatGPT Search", "Grok")):
        a, b = platforms["ChatGPT Search"], platforms["Grok"]
        bullets.append(f'<li><strong>The observed own-content citation proportions differed among coded recommendation records.</strong> ChatGPT: <b>{a["cited_recommendations"]}/{a["totals"]["recommendation"]} ({a["own_citation_coverage"]:.1%})</b>; Grok: <b>{b["cited_recommendations"]}/{b["totals"]["recommendation"]} ({b["own_citation_coverage"]:.1%})</b>. These are entity-by-answer records, limited to the coded entities and captured citations; third-party support is excluded. They do not establish inherent platform preferences or answer accuracy.</li>')
    bullets.append('<li><strong>Neither platform was more consistent across all three questions.</strong> Grok’s two answers were closer on empirical research; the gaps were smaller for learning resources and Q3 resources.</li>')
    bullets.append('<li><strong>These differences cannot establish whether a brand’s GEO work is effective.</strong> This study measures visibility under specific prompts and conditions. It does not test the effect of an optimization intervention or measure clicks, purchases, or conversions.</li>')
    scope = f'The main sample contains {findings["completed_runs"]} / {findings["planned_runs"]} complete answers and {insights["observation_count"]} coded entity-by-answer observations. There were {findings["total_prompts"]} actual submissions and {findings["capture"]["capture_history_count"]} captures. The {findings["historical_attempts"]} submissions outside the main sample are retained in the history and excluded from its statistics.'
    return '<section class="section executive-summary" id="conclusions"><div class="section-kicker">Key findings</div><h2>Four key findings</h2><ul class="conclusion-list">' + "".join(bullets) + f'</ul><blockquote class="report-note"><strong>Scope and interpretation</strong><p>{h(scope)}</p><p>There are only two repeats per question and platform. Tests span multiple dates, reasoning effort varies, and account memory was observed. With no pre-optimization baseline, intervention, or control group, this study cannot support causal claims or rank the platforms’ inherent quality.</p></blockquote></section>'


def render_insight_sections(runs, findings):
    insights = findings["insights"]
    cross_panels = []
    for row in insights["cross_platform"]:
        ratio = row["jaccard"]
        label = f'{ratio:.1%}' if ratio is not None else "Awaiting complete data"
        counts = "; ".join(f'{p}: {n} entities' for p, n in row["recommendation_counts"].items())
        shared = ", ".join(row["shared_entities"]) or "No confirmed shared recommendations"
        cross_panels.append(f'<article class="finding-panel"><h3>{h(row["question_id"])} · {h(QUESTION_LABELS[row["question_id"]])}</h3><div class="finding-number">{label}</div><p>{row["intersection"]} shared / {row["union"]} total entities</p><p class="note">{h(counts)}</p><details><summary>Shared recommendations</summary><p class="small">{h(shared)}</p></details></article>')
    stable = []
    for group in findings["groups"]:
        if group["question_id"] == "Q3" and group.get("repeat_overlap"):
            shared = ", ".join(group["repeat_overlap"]["shared_entities"]) or "No shared entities"
            stable.append(f'<article class="compare-panel"><h3>{h(group["platform"])} · Recommended in both repeats</h3><p>{h(shared)}</p></article>')
    resource_counts = []
    for group in findings["groups"]:
        overlap = group.get("repeat_overlap")
        if group["question_id"] == "Q1" and overlap:
            resource_counts.append(f'{group["platform"]} {overlap["repeat_1_recommendations"]} / {overlap["repeat_2_recommendations"]} entities')
    cross_section = f'''<section class="section" id="main-findings"><h2>How different were the platforms’ recommendations?</h2><ul class="section-conclusions"><li><strong>The largest cross-platform difference was in Q3 recommended entities/resources.</strong> The platforms selected different resources. The overlap for each question below shows the extent of that difference.</li><li><strong>The recommendations repeated within each platform also differed.</strong> For Q3, each platform had its own set of entities recommended in both repeats. This observation does not establish a lasting platform preference.</li></ul><p class="note">For each platform, recommendations from both repeats are combined before comparing the two sets. Cross-platform overlap = shared entities ÷ the union of both platforms’ sets. Each group contains 2 complete answers. The next section compares repeats within each platform, using different sets; these are separate measures.</p><div class="finding-grid">{"".join(cross_panels)}</div><h3 style="margin-top:28px">Q3 · Entities/resources recommended in both repeats</h3><div class="compare-grid">{"".join(stable)}</div><p class="note" style="margin-top:18px">Q1 recommendation counts by repeat: {h("; ".join(resource_counts))}. Grok produced longer lists for learning resources. List length alone does not measure answer quality or consistency. The repeated Q3 recommendations describe only these two answers and do not establish a lasting platform preference.</p></section>'''

    coverage = []
    for row in insights["platforms"]:
        numerator, denominator = row["cited_recommendations"], row["totals"]["recommendation"]
        value = row["own_citation_coverage"]
        ratio = f'{value:.1%}' if value is not None else "Not applicable"
        bar = f'<div class="bar-track" role="img" aria-label="{h(row["platform"])}: {numerator}/{denominator} recommendations also cite the entity’s own content"><div class="bar-fill" style="width:{(value or 0)*100:.4f}%"></div></div>'
        coverage.append(f'<article class="compare-panel"><h3>{h(row["platform"])}</h3><div class="finding-number">{ratio}</div>{bar}<p style="margin-top:12px">{numerator} / {denominator} recommendations also cite the entity’s own or bylined content</p><p class="note">This type of citation was not observed for {row["recommendations_without_own_citation"]} other recommendations; {row["recommendations_with_unknown_citation"]} remain undetermined.</p></article>')

    pattern_labels = [("CMR", "C + M + R", "#176b62"), ("MR", "M + R, no own-content C", "#547997"), ("CM", "C + M, no R", "#866a9c"), ("C", "C only", "#9a6d23"), ("M", "M only", "#66747e"), ("CR", "C + R, no M", "#496f48"), ("R", "R only", "#83534f"), ("none", "All three No", "#69777a"), ("unknown", "Includes undetermined values", "#666666")]
    used = [item for item in pattern_labels if any(p["patterns"].get(item[0]) for p in insights["platforms"])]
    legend = "".join(f'<span><span class="cmr-swatch" style="background:{color}"></span>{h(label)}</span>' for _, label, color in used)
    stacks = []
    for row in insights["platforms"]:
        n = row["observation_count"]
        labels, segments = [], []
        for pattern, label, color in used:
            count = row["patterns"].get(pattern, 0)
            labels.append(f'{label} {count}')
            if count and n:
                segments.append(f'<span class="cmr-segment" style="width:{count/n*100:.6f}%;background:{color}" title="{h(label)}: {count} / {n}">{count if count/n >= .06 else ""}</span>')
        caption = "; ".join(labels)
        stacks.append(f'<div class="distribution-row"><div class="distribution-label"><strong>{h(row["platform"])}</strong><span>{n} entity-by-answer observations</span></div><div class="cmr-stack" role="img" aria-label="{h(row["platform"])}: {h(caption)}">{"".join(segments)}</div><p class="distribution-counts">{h(caption)}</p></div>')
    matrix_rows = []
    by_question = {(r["question_id"], r["platform"]): r for r in insights["by_question"]}
    for q in QUESTION_LABELS:
        cells = []
        for platform in ("ChatGPT Search", "Grok"):
            row = by_question.get((q, platform))
            if row:
                totals = row["totals"]
                cells.append(f'<td>{totals["citation"]} / {totals["mention"]} / {totals["recommendation"]}<div class="note">{row["observation_count"]} observations, {row["answer_count"]} answers</div></td>')
            else:
                cells.append('<td>Not recorded</td>')
        matrix_rows.append(f'<tr><th scope="row">{h(q)} · {h(QUESTION_LABELS[q])}</th>{"".join(cells)}</tr>')
    examples = [
        ("All three", "C-Q1-R1-A2", "Ahrefs", "Its own tutorial is cited, its name appears explicitly, and it is actively recommended."),
        ("Citation and mention", "C-Q2-R2-A3", "Axios", "Its reporting supports a point about measurement variability; it is not actively recommended as a learning resource."),
        ("Citation only", "C-Q3-R2-A3", "Relevance", "The text recommends Seer, while the actual link points to Relevance. The cited publisher is neither named nor recommended."),
        ("Mention only", "C-Q2-R2-A3", "Muck Rack", "It is named as a research organization, while the citation points to third-party reporting by Axios."),
        ("Recommendation without own-content citation", "G-Q1-R1", "Bing Webmaster Tools", "It is explicitly recommended, but no direct citation of its own content was observed."),
    ]
    example_rows = []
    for label, run_id, entity, explanation in examples:
        match = next(((i, r, o) for i, r in enumerate(runs, 1) if r.get("id") == run_id for o in r.get("observations") or [] if o.get("entity") == entity), None)
        if match:
            index, run, obs = match
            example_rows.append(f'<tr><td>{h(label)}</td><td><strong>{h(entity)}</strong><div class="note">{h(run["platform"])} · {h(run["question_id"])}</div></td><td>{flag(obs["citation"])}</td><td>{flag(obs["mention"])}</td><td>{flag(obs["recommendation"])}</td><td>{h(explanation)} <a href="#run-{index}">View coding and answer</a></td></tr>')
    cmr_section = f'''<section class="section" id="cmr-distribution"><h2>Citations, mentions, and recommendations can occur separately</h2><ul class="section-conclusions"><li><strong>The observed own-content citation proportions differed among coded recommendation records.</strong> The comparison below uses the same definition, with each platform’s recommendation records as its denominator.</li><li><strong>Citations, mentions, and recommendations can occur separately.</strong> Content can support an answer without naming its publisher. A recommendation can also be supported by third-party content.</li></ul><blockquote class="report-note definition-note"><dl class="metric-defs"><div><dt>C · Citation</dt><dd>The answer cites content published or bylined by the entity.</dd></div><div><dt>M · Mention</dt><dd>The answer text explicitly names the entity.</dd></div><div><dt>R · Recommendation</dt><dd>The answer actively suggests using, reading, or following the entity.</dd></div></dl></blockquote><p class="note">C/M/R are assessed separately, rather than as a strict funnel. An entity can satisfy multiple criteria. No observed citation of its own content does not mean the answer has no supporting evidence.</p><h3>How many recommendations also cite the entity’s own content?</h3><div class="compare-grid">{"".join(coverage)}</div><p class="note" style="margin-top:14px">The denominator is coded Recommendation=true entity-by-answer records. Citation counts only observed content published or bylined by that entity; third-party support does not count. This comparison is limited to coded entities and captured citations. Uneven source capture and assistant coding limit it; it cannot establish inherent platform citation preferences, answer accuracy or a brand’s probability of being recommended.</p><h3 style="margin-top:28px">Distribution of C/M/R combinations</h3><p class="note">There are {insights["observation_count"]} entity-by-answer records. The same entity in two answers counts twice. Bar widths are normalized to each platform’s observation count; labels show absolute counts. Omitted letters mean “No.” Entities include brands, organizations, creators, and studies, not only products.</p><div class="cmr-legend">{legend}</div>{"".join(stacks)}<p class="note"><strong>Coding scope: </strong> Counts cover the coded main recommendations and substantive discussion subjects, not every source publisher. Source-only entities were not exhaustively coded for Grok, so zero citation-only records does not establish that Grok never cites without naming. The prompts themselves request recommendations; a high recommendation share does not represent a market average.</p><h3>By question: C / M / R counts</h3><p class="note">The three counts can overlap and must not be added to obtain an entity total.</p><div class="table-wrap"><table class="comparison-table"><thead><tr><th>Question</th><th>ChatGPT · C / M / R</th><th>Grok · C / M / R</th></tr></thead><tbody>{"".join(matrix_rows)}</tbody></table></div><details><summary>Five observed combinations and their evidence</summary><div class="table-wrap"><table class="case-table compact"><thead><tr><th>Case</th><th>Entity and answer</th><th>C</th><th>M</th><th>R</th><th>Explanation and evidence</th></tr></thead><tbody>{"".join(example_rows)}</tbody></table></div></details><aside class="interpretation" id="effect-limits"><h3>These results cannot establish whether a brand’s GEO work is effective</h3><p>The comparison shows how often entities were cited, mentioned, and recommended for these prompts, dates, accounts, and modes. It does not rank optimization effectiveness, content quality, or inherent platform quality, and it does not measure clicks, purchases, or conversions.</p><p>There was no predefined list of brands to evaluate, no optimization intervention, and no pre-optimization baseline or control group. There are only two repeats per question and platform. Tests span multiple dates, reasoning effort varies, and account memory was observed. An absent entity cannot simply be judged to have poor GEO.</p><p class="note">Evaluating optimization effects would require fixed brands, prompts, and conditions, a pre-optimization baseline, controls, and more repeats, while tracking C/M/R separately. Multiple tutorials citing the same GEO paper are not multiple independent experiments. The supplemental audit checks a purposive selection of sources only; it does not independently replicate external studies or verify effectiveness claims.</p></aside></section>'''
    return cross_section, cmr_section


def render_frequency(group):
    denominator = group["completed_runs"]
    if denominator == 0:
        return f'<div class="chart-panel"><h3>{h(group["platform"])} · {h(group["question_id"])}</h3><p class="chart-caption">{h(QUESTION_LABELS.get(group["question_id"], ""))}</p><p class="empty"><strong>No complete answer available for analysis</strong><br>Recommendation frequency was not calculated. This does not mean there were no recommendations.</p></div>'
    rows = [x for x in group["frequencies"] if x["recommendation"] > 0]
    def render_bar(row):
        return f'<div class="chart-row"><span>{h(row["entity"])}</span><div class="bar-track" role="img" aria-label="{h(row["entity"])}: {row["recommendation"]} / {denominator} answers actively recommend this entity"><div class="bar-fill" style="width:{row["recommendation"] / denominator * 100:.4f}%"></div></div><span class="bar-value">{row["recommendation"]}/{denominator}</span></div>'
    bars = "".join(render_bar(row) for row in rows[:8])
    if len(rows) > 8:
        bars += f'<details><summary>{len(rows) - 8} more recommended entities</summary>' + "".join(render_bar(row) for row in rows[8:]) + '</details>'
    if not bars:
        bars = '<p class="empty">The answer has been captured, but coding is pending completion or review. This does not mean there were no recommendations.</p>' if group["recommendation_coding_incomplete"] else '<p class="empty">No entities are coded as actively recommended.</p>'
    coding_note = '<p class="note">Some recommendation records are undetermined or uncoded. Bars show only confirmed recommendation counts.</p>' if group["recommendation_coding_incomplete"] else ""
    comparison = (group.get("repeat_overlap") or {}).get("condition_comparison")
    condition_note = render_condition_comparison(comparison) if comparison and comparison["status"] == "different" else ""
    return f'<div class="chart-panel"><h3>{h(group["platform"])} · {h(group["question_id"])}</h3><p class="chart-caption">{h(QUESTION_LABELS.get(group["question_id"], ""))} · {denominator} complete answers</p>{coding_note}{condition_note}{bars}</div>'


def render_condition_comparison(comparison):
    if not comparison:
        return ""
    details = [f'{d["label"]}: {d["first"]} → {d["second"]}' for d in comparison["differences"]]
    if comparison["unknown_fields"]:
        details.append("Not fully recorded: " + ", ".join(comparison["unknown_fields"]))
    if any(c["date_conflict"] for c in comparison["runs"]):
        details.append("The date field conflicts with the submission timestamp; check the original evidence.")
    detail_html = f'<br>{h("; ".join(details))}' if details else ""
    return f'<p class="note"><strong>{h(comparison["label"])}</strong> {detail_html}</p>'


def render_condition_overview(summary):
    rows = []
    for platform in summary["platforms"]:
        for condition in platform["records"]:
            conflict = '<div class="note">The date field differs from the submission timestamp.</div>' if condition["date_conflict"] else ""
            rows.append(f'<tr><td>{h(condition["run_id"])}</td><td>{h(platform["platform"])}<br>{h(condition["question_id"])} · Repeat {h(condition["repeat"])}</td><td>{h(condition["test_date"])}{conflict}</td><td>{h(condition["model_label"] or "Exact version not disclosed")}</td><td>{h(condition["reasoning_effort"] or "Not disclosed")}</td><td>{h(condition["mode_label"])}</td><td>{h(STATUS_LABELS.get(condition["status"], condition["status"]))}</td></tr>')
    table = '<div class="table-wrap"><table class="compact"><thead><tr><th>Main record</th><th>Platform / repeat</th><th>Submission date</th><th>Model UI label</th><th>Reasoning effort</th><th>Full mode label</th><th>Answer status</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>' if rows else '<p class="empty">No main-record conditions are available.</p>'
    return '<details class="section detail-section" id="conditions"><summary>Main-record dates, models, and reasoning effort</summary><div class="detail-content"><p class="note">This table shows the currently selected main records, including incomplete slots. Frequency and overlap use only completed samples. Dates refer to actual submissions, not recovery or later work. Reasoning effort comes first from explicit fields, then from UI mode labels; undisclosed values are not inferred. Different reasoning effort counts as a different condition even when model labels match. A shared UI label does not guarantee identical backend routing.</p>' + table + '</div></details>'


def render_overlap(groups):
    by_question = defaultdict(list)
    for group in groups:
        by_question[group["question_id"]].append(group)
    panels = []
    for question_id, question_groups in sorted(by_question.items()):
        rows = []
        for group in sorted(question_groups, key=lambda x: x["platform"]):
            overlap = group["repeat_overlap"]
            value = overlap.get("jaccard") if overlap else None
            if group["completed_runs"] == 0:
                label, detail = "Missing", "No complete answer available for analysis"
            elif overlap is None:
                label, detail = "—", "Both repeats are not yet complete"
            elif overlap["recommendation_coding_incomplete"]:
                label, detail = "Coding pending", "Recommendation coding is incomplete"
            elif value is None:
                label, detail = "Not applicable", "Neither repeat has an actively recommended entity"
            else:
                label = f"{value:.1%}"
                detail = f'{overlap["intersection"]} shared / {overlap["union"]} total entities'
            bar = f'<div class="bar-track" role="img" aria-label="{h(group["platform"])} {h(question_id)} Recommendation overlap {h(label)}"><div class="bar-fill" style="width:{value * 100:.4f}%"></div></div>' if value is not None else ""
            comparison_note = render_condition_comparison(overlap.get("condition_comparison")) if overlap else ""
            rows.append(f'<div class="overlap-item"><div class="overlap-label"><span>{h(group["platform"])}</span><strong>{h(label)}</strong></div>{bar}<div class="overlap-detail">{h(detail)}</div>{comparison_note}</div>')
        panels.append(f'<div class="chart-panel"><h3>{h(question_id)} · {h(QUESTION_LABELS.get(question_id))}</h3>{"".join(rows)}</div>')
    return '<div class="overlap-grid">' + "".join(panels) + '</div>' if panels else '<p class="empty">No records are available for overlap calculation.</p>'


def render_observations(run):
    rows = []
    for obs in run.get("observations") or []:
        urls = obs.get("source_urls") or []
        if isinstance(urls, str):
            urls = [urls]
        source_links = "<br>".join(link(url) for url in urls) or "Not recorded"
        notes = f'<div class="note">{h(obs["notes"])}</div>' if obs.get("notes") else ""
        rows.append(f'<tr><td><strong>{h(obs.get("entity"))}</strong><div class="note">{h(obs.get("entity_type"))}</div></td><td>{flag(obs.get("citation"))}</td><td>{flag(obs.get("mention"))}</td><td>{flag(obs.get("recommendation"))}</td><td><div class="evidence">{h(obs.get("evidence"))}</div>{notes}</td><td class="small">{source_links}</td></tr>')
    if not rows:
        return '<p class="empty">No entity-level coding is available for this answer.</p>'
    return '<div class="table-wrap"><table class="cmr-table compact"><thead><tr><th>Entity</th><th>Citation</th><th>Mention</th><th>Recommendation</th><th>Coding evidence / notes</th><th>Related source URLs</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'


def render_sources(run):
    partitions = source_partitions(run)
    mapping_note = '<p class="note"><strong>Answer citation mapping is incomplete.</strong> Observed answer links are not a complete citation inventory. Unmapped markers are retained in the underlying evidence.</p>' if run.get("citation_mapping_complete") is False else ""
    labels = {"answer": ("Answer citation links (including manual matches)", "These links come from explicit answer links, an answer’s Sources list, or manual matching of citation labels to the source panel. Per-entity coding records the matching method and citation attribution."), "retrieval": ("Retrieval source panel", "These are retrieval or source-panel records. They are not necessarily citations in the answer and do not by themselves add a Mention, Citation, or Recommendation."), "unknown": ("Unclassified sources", "Earlier records did not fully identify where these links appeared. They are retained for traceability and are not automatically classified as answer citations.")}
    output = [mapping_note]
    for kind, sources in partitions.items():
        if not sources and kind != "answer":
            continue
        title, explanation = labels[kind]
        rows = []
        for index, source in enumerate(sources, 1):
            s = source if isinstance(source, dict) else {"url": source}
            context_html = "".join(f'<div class="note">{h(s[field])}</div>' for field in ("context", "evidence") if s.get(field))
            if s.get("evidence_files"):
                context_html += f'<div class="small">Matching evidence: {render_evidence_files(s["evidence_files"])}</div>'
            rows.append(f'<tr><td>{index}</td><td>{h(s.get("title_en") or s.get("title") or s.get("text"))}<br>{link(s.get("url"))}{context_html}</td><td>{h(source_domain(s))}</td><td>{h(s.get("kind") or s.get("source_kind") or kind)}</td></tr>')
        table = '<div class="table-wrap"><table class="compact"><thead><tr><th>#</th><th>Source and exact URL</th><th>Domain</th><th>Record type</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>' if rows else '<p class="empty">No observable answer links were captured. This does not mean the answer had no citations.</p>'
        output.append(f'<details><summary>{title} · {len(sources)} records</summary><p class="note">{explanation}</p>{table}</details>')
    return "".join(output)


def render_evidence_files(value):
    values = value if isinstance(value, list) else [value] if value else []
    links = []
    seen = set()
    for item in values:
        if isinstance(item, dict):
            path = item.get("file") or item.get("path")
            label = item.get("label") or item.get("title") or path
        else:
            path, label = item, item
        if path and str(path) not in seen:
            seen.add(str(path))
            links.append(local_link(path, label))
    return "<br>".join(links) or "Not recorded"


def metadata_corrections(run):
    value = run.get("metadata_corrections") or capture_provenance(run).get("metadata_corrections") or []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict) and "field" in value:
        return [value]
    if isinstance(value, dict):
        return [{"field": field, **(details if isinstance(details, dict) else {"value": details})} for field, details in value.items()]
    return []


def render_metadata_corrections(run):
    corrections = metadata_corrections(run)
    if not corrections:
        return ""
    labels = {"started_at": "Submission time", "finished_at": "Capture time", "date_local": "Submission date", "model_label": "Model label", "mode_label": "Mode label", "model_evidence": "Model evidence"}
    rows = []
    for correction in corrections:
        field = correction.get("field")
        original = correction.get("original_value")
        previous = correction.get("previous_effective_value")
        previous_note = f'<div class="note">Previous derived value: {h(previous)}</div>' if "previous_effective_value" in correction and previous != original else ""
        files = render_evidence_files(correction.get("evidence_files"))
        rows.append(f'<tr><td>{h(labels.get(field, field))}<br><code>{h(field)}</code></td><td><code>{h(original)}</code>{previous_note}</td><td><code>{h(correction.get("value"))}</code></td><td><div class="evidence">{h(correction.get("evidence"))}</div>{files}</td></tr>')
    return f'<details><summary>Metadata corrections · {len(corrections)} fields</summary><p class="note">Corrections apply to derived records and this report’s display. The underlying raw files retain their original values. Timestamps here retain their original ISO notation for exact comparison with saved evidence.</p><div class="table-wrap"><table class="compact"><thead><tr><th>Field</th><th>Original value</th><th>Corrected value</th><th>Basis and evidence files</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></details>'


def render_submitted_prompt(run):
    if not any(field in run for field in ("submitted_prompt", "observed_submitted_prompt", "normalized_submitted_prompt")):
        return ""
    provenance = run.get("submitted_prompt_provenance")
    if "observed_submitted_prompt" in run:
        observed = run.get("observed_submitted_prompt")
    else:
        observed = None if provenance == "inferred_from_recorded_prompt_and_mode" else run.get("submitted_prompt")
    canonical = run.get("prompt")
    normalized = run.get("normalized_submitted_prompt")
    if observed is not None:
        observed_html = f'<p class="small">Observed submission text (JSON string notation, preserving whitespace)</p><pre class="raw-answer" lang="en">{h(json.dumps(observed, ensure_ascii=True))}</pre>'
    else:
        observed_html = '<p class="note">No observed submission text was saved. A derived representation cannot substitute for original evidence.</p>'
        if run.get("submitted_prompt") is not None:
            observed_html += f'<p class="small">Derived submission representation (not an original observation)</p><pre class="raw-answer" lang="en">{h(json.dumps(run["submitted_prompt"], ensure_ascii=True))}</pre>'
    if normalized is None:
        check_note = "No submission-format normalization check is recorded. The original text is retained unchanged."
    elif normalized == canonical:
        check_note = "The assembly check records an exact match to the canonical English prompt after submission-format normalization. "
        if "chatgpt" in str(run.get("platform") or "").casefold():
            check_note += "The search-tool chip’s position at the beginning or end, the @ symbol, and adjacent spaces are submission-format differences. The English question was not rewritten and no English steering was added."
    else:
        check_note = "The normalized submission does not match the canonical English prompt and requires review. The prompt cannot be treated as unchanged on this evidence."
    return f'<details><summary>Observed submission and canonical English prompt</summary><p class="small">Canonical English prompt (unchanged)</p><div class="question" lang="en">{h(canonical)}</div>{observed_html}<p class="note">{h(check_note)}</p><p class="note">Submission text provenance: {h(provenance or "Not separately specified in the original record")}</p></details>'


def render_provenance(run):
    provenance = capture_provenance(run)
    correction_html = render_metadata_corrections(run)
    submitted_html = render_submitted_prompt(run)
    if not provenance and not correction_html and not submitted_html:
        return ""
    fields = [("Original record status", provenance.get("original_status")), ("Current capture ID", provenance.get("selected_capture_id") or run.get("capture_id")), ("Selected evidence method", provenance.get("method")), ("Evidence capture time", display_timestamp(provenance.get("captured_at"))), ("Same conversation", "Yes" if provenance.get("same_conversation") is True else "No" if provenance.get("same_conversation") is False else "Undetermined"), ("Answer completeness review", provenance.get("body_completeness") or provenance.get("completeness_status")), ("Review notes", provenance.get("review_notes"))]
    metadata = "".join(f'<div><dt>{h(label)}</dt><dd>{h(value)}</dd></div>' for label, value in fields)
    files = [("Original capture evidence", provenance.get("original_raw_file")), ("Currently selected evidence", provenance.get("selected_capture_file")), ("Supporting evidence", provenance.get("evidence_files"))]
    file_html = "".join(f'<p class="small">{label}: {render_evidence_files(value)}</p>' for label, value in files if value)
    history_refs = f'<p class="note">This submission has {len(run["capture_history"])} retained captures. See the capture history below or the <a href="data/capture-history.json">complete capture log</a>.</p>' if run.get("capture_history") else ""
    public_note = '<p class="note">Captured through the share-dialog preview without creating a public conversation link.</p>' if provenance.get("public_share_created") is False else ""
    return f'<details><summary>Capture provenance and recovery</summary><dl class="run-meta">{metadata}</dl>{file_html}{history_refs}{public_note}{correction_html}{submitted_html}<p class="note">Recapturing an existing conversation is distinct from submitting a new prompt. Statistics use the final record status; additional captures do not increase the test sample.</p></details>'


def render_memory_evidence(run):
    evidence = memory_evidence(run)
    if not evidence:
        return ""
    rows = []
    for item in evidence:
        item = item if isinstance(item, dict) else {"evidence": item}
        files = render_evidence_files(item.get("file") or item.get("evidence_files"))
        chat_link = link(item["conversation_url"], "Related conversation") if item.get("conversation_url") else ""
        rows.append(f'<p class="evidence">{h(item.get("evidence"))}</p><p class="small">{h(item.get("kind"))} · {files} {chat_link}</p>')
    return '<div class="notice"><p><strong>Cross-test memory contamination was observed.</strong> Earlier questions or conversations from this batch appeared in this answer’s retrieval evidence. This limits the independence of the test conversations, but does not establish that memory caused a particular recommendation.</p>' + "".join(rows) + '</div>'


def render_corrections(corrections):
    output = []
    for correction in corrections or []:
        c = correction if isinstance(correction, dict) else {"corrected_claim": correction}
        previous = f'<p><span class="muted">Previous interpretation: </span>{h(c["previous_claim"])}</p>' if c.get("previous_claim") else ""
        evidence = render_evidence_files(c.get("evidence_files") or c.get("file"))
        output.append(f'<div><h3>{h(c.get("id") or c.get("title") or "Diagnostic correction")}</h3>{previous}<p><strong>Correction: </strong> {h(c.get("corrected_claim") or c.get("notes"))}</p><p class="small">Related records: {h(c.get("run_ids") or c.get("attempt_ids"))}<br>Evidence: {evidence}</p></div>')
    return "".join(output)


def render_capture_history(value):
    history = normalize_capture_history(value)
    rows = []
    for item in history["captures"]:
        c = item if isinstance(item, dict) else {"capture_id": item}
        file_refs = [c.get("file") or c.get("raw_file")]
        for field in ("artifacts", "supporting_artifacts", "evidence_files"):
            value = c.get(field) or []
            file_refs.extend(value if isinstance(value, list) else [value])
        files = render_evidence_files(file_refs)
        selected_note = " · Currently selected" if c.get("selected") is True else ""
        scope_note = " · Submission in the main sample" if c.get("attempt_in_main_sample") is True else ""
        rows.append(f'<tr><td>{h(c.get("capture_id"))}<br><span class="note">{h(c.get("attempt_id") or c.get("run_id"))}{selected_note}{scope_note}</span></td><td>{h(display_timestamp(c.get("captured_at") or c.get("capturedAt")))}</td><td>{h(c.get("method"))}<br><span class="note">{h(c.get("capture_kind"))}</span></td><td>{h(c.get("status"))}<br><span class="note">{h(c.get("body_completeness"))}</span></td><td>{files}</td><td>{h(c.get("notes") or c.get("review_notes"))}</td></tr>')
    if not rows and not history["corrections"]:
        return ""
    table = '<div class="table-wrap"><table class="compact"><thead><tr><th>Capture / original submission</th><th>Capture time</th><th>Method</th><th>Result / answer status</th><th>Evidence files</th><th>Notes</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>' if rows else ""
    corrections = render_corrections(history["corrections"])
    notes = history["notes"] if isinstance(history["notes"], list) else [history["notes"]]
    notes_html = "".join(f'<p class="note">{h(note)}</p>' for note in notes if note)
    return f'<details class="section detail-section" id="capture-history"><summary>Capture failures, recovery, and diagnostic corrections · {len(rows)} captures</summary><div class="detail-content"><p class="note">This history retains multiple captures, failures, and corrections for each actual submission without increasing the submission count. A read_thread summary or preview does not establish the full server-stored answer. A single empty snapshot of an asynchronously loaded source panel does not establish that no sources were retrieved.</p>{notes_html}{corrections}{table}</div></details>'


def render_run(run, index):
    status = str(run.get("status") or "Not recorded")
    badge_class = "done" if status == "completed" else "blocked" if status == "blocked" else ""
    meta = [("Date", run.get("date_local")), ("Submission time", display_timestamp(run.get("started_at"))), ("Capture time", display_timestamp(run.get("finished_at"))), ("UI mode", run.get("mode_label")), ("Model label", run.get("model_label")), ("Search status", run.get("search_status")), ("Model evidence", run.get("model_evidence")), ("Search evidence", run.get("search_evidence")), ("Answer capture method", capture_method(run)), ("Citation link review", mapping_label(run.get("citation_mapping_complete")))]
    condition = run_conditions(run)
    meta.insert(5, ("Reasoning effort (recorded UI)", condition["reasoning_effort"] or "Not disclosed"))
    if condition["date_conflict"]:
        meta.append(("Date conflict", f'date_local={condition["test_date"]}; Submission time converted to UTC+8={condition["date_from_submit"]}'))
    for field, label in (("slot_id", "Planned slot"), ("attempt_id", "Actual submission ID"), ("capture_id", "Selected capture ID")):
        if run.get(field):
            meta.append((label, run[field]))
    if "selected_eligible" in run:
        meta.append(("Selected capture eligible", "Yes" if run["selected_eligible"] is True else "No" if run["selected_eligible"] is False else "Undetermined"))
    if run.get("selection_reason"):
        meta.append(("Current selection rationale", run["selection_reason"]))
    if "coding_reviewed_for_capture" in run:
        meta.append(("Coding reviewed against current capture", "Reviewed" if run["coding_reviewed_for_capture"] is True else "Pending review"))
    if run.get("attempt_number") is not None:
        meta.append(("Submission count for this slot", run.get("attempt_number")))
    if run.get("replacement_for"):
        meta.append(("Original record for this retest", run.get("replacement_for")))
    metadata = "".join(f'<div><dt>{h(label)}</dt><dd>{h(value)}</dd></div>' for label, value in meta)
    links = "".join(x for x in [link(run["conversation_url"], "Conversation reference") if run.get("conversation_url") else "", local_link(run.get("raw_file"), "Public record"), local_link(run.get("screenshot_file"), "UI screenshot")] if x)
    notes = f'<p class="note">Record notes: {h(run["notes"])}</p>' if run.get("notes") else ""
    recovery_note = '<p><strong>The interpretation of read_thread evidence has been corrected.</strong> This tool returns summaries or previews, not the complete server-stored answer. A preview’s ending alone cannot establish that the original answer was truncated. The capture provenance section identifies the currently selected answer; earlier evidence is retained for traceability.</p>' if uses_read_thread_preview(run) else ""
    citation_note = '<p><strong>Internal citation mapping is incomplete.</strong> Not all citation URLs were exported for this record. Unmapped internal citations are not treated as absent citations. Answer recovery and citation mapping are recorded separately.</p>' if run.get("citation_mapping_complete") is False else ""
    limitations = f'<div class="notice">{recovery_note}{citation_note}</div>' if recovery_note or citation_note else ""
    personal = personalization_evidence(run)
    personal_note = f'<div class="notice"><p><strong>Personalization was observed as a confounding factor.</strong> The answer referred to personal creative context that was absent from the original prompt:</p><p class="evidence" lang="en">{h(personal)}</p><p class="note">A fresh conversation did not remove this influence. This answer was not collected under verified personalization-free conditions.</p></div>' if personal else ""
    mapping_badge = '<span class="status blocked">Incomplete citation mapping</span>' if run.get("citation_mapping_complete") is False else ""
    corrections = render_corrections(run.get("diagnostic_corrections") or [])
    correction_section = f'<details><summary>Diagnostic corrections for this record</summary>{corrections}</details>' if corrections else ""
    return f'''<details id="run-{index}"><summary>{h(run.get("id"))} · {h(run.get("platform"))} · {h(run.get("question_id"))} · Repeat {h(run.get("repeat"))} <span class="status {badge_class}">{h(STATUS_LABELS.get(status, status))}</span> {mapping_badge}</summary><div class="run-body"><dl class="run-meta">{metadata}</dl>{limitations}{personal_note}{render_memory_evidence(run)}{render_provenance(run)}{correction_section}<div class="question" lang="en">{h(run.get("prompt"))}</div><div class="links">{links}</div>{notes}<h3>Entity observations</h3>{render_observations(run)}<details><summary>Answer links and retrieval sources</summary>{render_sources(run)}</details><details><summary>Answer text · public edited copy</summary><pre class="raw-answer" lang="en">{h(run.get("answer_text"))}</pre></details></div></details>'''


def render(runs, findings, attempts=None, capture_history=None):
    attempts = attempts or []
    if "insights" not in findings:
        findings["insights"] = summarize_insights(runs)
    platform_findings, cmr_findings = render_insight_sections(runs, findings)
    sidebar = render_sidebar(runs)
    executive_summary = render_executive_summary(findings)
    complete = findings["completed_runs"]
    dates = sorted({str(r["date_local"]) for r in runs + attempts if r.get("date_local")})
    date_label = " / ".join(dates) or "No test dates recorded"
    condition_summary = summarize_conditions(runs)
    platform_labels = []
    for platform in condition_summary["platforms"]:
        values = platform["values"]
        models = " / ".join(values["model_comparison"]) or "Exact model version not disclosed"
        efforts = " / ".join(values["reasoning_effort"]) or "Not disclosed"
        test_dates = " / ".join(values["test_date"]) or "Date not recorded"
        modes = " / ".join(values["mode_comparison"]) or "Mode not recorded"
        platform_labels.append(f'{platform["platform"]}: {models} · Reasoning effort {efforts} · {modes} · {test_dates}')
    condition_header = "<br>".join(h(label) for label in platform_labels) or "No main-record conditions recorded"
    condition_overview = render_condition_overview(condition_summary)
    matrix = "".join(f'<tr><td>{h(run.get("platform"))}</td><td>{h(run.get("question_id"))}</td><td>{h(run.get("repeat"))}</td><td>{h(run.get("date_local"))}</td><td>{h(run.get("mode_label"))}<br><span class="note">{h(run.get("model_label"))}</span></td><td>{h(run.get("search_status"))}</td><td>{h(capture_method(run))}<br><span class="note">{h(mapping_label(run.get("citation_mapping_complete")))}</span></td><td><a href="#run-{i}">{h(STATUS_LABELS.get(run.get("status"), run.get("status")))}</a></td></tr>' for i, run in enumerate(runs, 1))
    if not matrix:
        matrix = '<tr><td colspan="8" class="empty">No test records are available.</td></tr>'
    overlaps = []
    for group in findings["groups"]:
        overlap = group["repeat_overlap"]
        if overlap is None:
            reason = "No complete answer available for analysis" if group["completed_runs"] == 0 else "Both repeats are not yet complete, or repeat numbers are not unique"
            a, b, both, union, ratio, entities = ["—"] * 5 + [reason]
        else:
            a, b, both, union = [str(overlap[k]) for k in ("repeat_1_recommendations", "repeat_2_recommendations", "intersection", "union")]
            ratio = "Coding pending" if overlap["recommendation_coding_incomplete"] else f'{overlap["jaccard"]:.1%}' if overlap["jaccard"] is not None else "Not applicable"
            entities = ", ".join(overlap["shared_entities"]) or "No shared recommendations"
        comparison_note = render_condition_comparison(overlap.get("condition_comparison")) if overlap else "Awaiting two complete answers"
        overlaps.append(f'<tr><td>{h(group["platform"])} · {h(group["question_id"])}</td><td>{a}</td><td>{b}</td><td>{both}</td><td>{union}</td><td>{ratio}</td><td>{h(entities)}</td><td>{comparison_note}</td></tr>')
    overlap_table = '<div class="table-wrap"><table class="compact"><thead><tr><th>Platform / question</th><th>Repeat 1</th><th>Repeat 2</th><th>Intersection</th><th>Union</th><th>Overlap</th><th>Shared recommendations</th><th>Condition notes</th></tr></thead><tbody>' + ("".join(overlaps) or '<tr><td colspan="8" class="empty">No results are available to summarize.</td></tr>') + '</tbody></table></div>'
    overlap_chart = render_overlap(findings["groups"])
    chart = "".join(render_frequency(group) for group in findings["groups"]) or '<p class="empty">Charts will be generated after actual answers are complete and coded.</p>'
    pending = max(0, 12 - complete)
    records = "".join(render_run(run, index) for index, run in enumerate(runs, 1)) or '<p class="empty">No answer records are available.</p>'
    history = "".join(render_run(run, f"history-{index}") for index, run in enumerate(attempts, 1))
    history_section = f'<details class="section detail-section" id="attempt-history"><summary>Other actual submissions · {len(attempts)} records</summary><div class="detail-content"><p class="note">These prompts were actually submitted but are not currently selected for the 12 planned slots. Their answers, failures, and capture evidence are retained and excluded from main-sample frequency and overlap statistics. Restoring an existing conversation can change the selected record without overwriting its history.</p>{history}</div></details>' if attempts else ""
    capture_history_section = render_capture_history(capture_history)
    previews = findings["capture"]["read_thread_preview_run_ids"]
    provenance_ids = findings["capture"]["provenance_run_ids"]
    partial = findings["capture"]["incomplete_citation_mapping_run_ids"]
    personalized = findings["capture"]["observed_personalization"]
    memory = findings["capture"]["observed_memory_evidence"]
    method_parts = ['<p><strong>Test conditions are recorded separately.</strong> Conditions are compared using each actual submission’s date, model UI label, reasoning effort, and UI mode. Recovery or later work dates are not test dates. Any recorded difference marks repeat overlap as “Different conditions; descriptive comparison only.” Undisclosed fields do not establish identical conditions. Changes in conditions cannot be attributed to a GEO tactic.</p>']
    if attempts:
        retest_dates = sorted({str(r["date_local"]) for r in runs if r.get("date_local") and (r.get("replacement_for") or str(r.get("attempt_number") or "1") != "1")})
        retest_date_label = ", ".join(retest_dates) or "Retest dates are not separately labeled; see each submission timestamp."
        method_parts.append(f'<p><strong>Retest policy: </strong> Additional submissions were authorized, with failures retained. The main table shows the actual submission currently selected for each of the 12 planned slots. The other {len(attempts)} submissions are kept separately in the history. Total submissions = {len(runs)} main records + {len(attempts)} historical submissions = {findings["total_prompts"]}. Recapturing a conversation does not add a submission.</p><p><strong>Retest dates: </strong> {h(retest_date_label)}. Charts include only completed samples in the main table, excluding historical submissions. A recovered answer can be selected again, while earlier capture failures and diagnostic corrections remain in the history.</p>')
    if previews:
        method_parts.append(f'<p><strong>Correction to read_thread evidence interpretation: </strong> {h(", ".join(map(str, previews)))} used this tool during capture. It returns summaries or previews, not the complete server-stored answer. An incomplete preview ending alone does not establish a truncated original answer. Each record’s selected capture determines the current answer text; earlier tool output remains capture history.</p>')
    if provenance_ids:
        method_parts.append(f'<p><strong>Recovery provenance: </strong> {h(", ".join(map(str, provenance_ids)))} record the original status and file, selected capture ID and file, method, and time. The completed status follows the final answer review. The generator does not mark an answer complete merely because a recovery file or source panel exists.</p>')
    if any(source_partitions(r)["retrieval"] for r in runs + attempts):
        method_parts.append('<p><strong>Answer links and retrieval panels are recorded separately.</strong> Source panels can load asynchronously, so one empty snapshot does not establish that sources are absent. Web pages and memory entries listed in a panel are not automatically answer citations. Only links observed in the answer or verifiable inline markers are listed as answer links. Citation attribution is still coded entity by entity.</p>')
    if partial:
        method_parts.append(f'<p><strong>Incomplete internal citation mapping: </strong> {h(", ".join(map(str, partial)))}. The report lists explicit answer URLs and recovered links. Unmapped internal citation markers remain in the underlying records, so the source table is not a complete citation inventory. Citation coding uses each row’s evidence and uncertainty; a missing link does not automatically mean “No.”</p>')
    for item in personalized:
        method_parts.append(f'<p><strong>Observed personalization: </strong> {h(item["run_id"])} contains personal creative context absent from the original prompt.</p><p class="evidence" lang="en">{h(item["evidence"])}</p><p>A fresh conversation therefore did not ensure the absence of personalization, limiting interpretation of cross-platform differences.</p>')
    if memory:
        method_parts.append(f'<p><strong>Observed cross-test memory contamination: </strong> {h(", ".join(str(item["run_id"]) for item in memory))} have retrieval evidence containing earlier questions or conversations from this batch. New conversations did not isolate account memory, so these repeats cannot be treated as independent trials. Per-record memory evidence and related-conversation references are retained, but do not establish that memory caused a specific recommendation.</p>')
    method_section = '<details class="section detail-section" id="method"><summary>Capture methods, retests, and limitations</summary><div class="detail-content method-notes">' + "".join(method_parts) + '</div></details>' if method_parts else ""
    limits = []
    if condition_summary["cross_day"]:
        limits.append("Main records span multiple dates (" + " / ".join(condition_summary["dates"]) + ")")
    condition_field_labels = {"model_comparison": "Model label", "reasoning_effort": "Reasoning effort", "mode_comparison": "UI mode"}
    for platform in condition_summary["platforms"]:
        for field in platform["changed_fields"]:
            limits.append(f'{platform["platform"]} has varying {condition_field_labels[field]} values: ' + " / ".join(platform["values"][field]) + " (conditions differ)")
    if condition_summary["date_conflict_run_ids"]:
        limits.append("Some date fields conflict with submission timestamps and require review")
    if previews or provenance_ids:
        limits.append("Some ChatGPT answer captures failed; read_thread provides only summaries or previews")
    if personalized:
        limits.append("Personalization was observed")
    if partial:
        limits.append("Some main-record citations are not mapped to URLs" if any(r.get("citation_mapping_complete") is False for r in runs) else "Unmapped citations from historical captures are retained in the evidence")
    if memory:
        limits.append("Cross-test memory contamination was observed")
    short_limits = "; ".join(limits)
    if short_limits:
        short_limits += ". "
    document = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>GEO Learning Log · Stage 1</title><style>{CSS}</style></head><body><div class="report-shell">{sidebar}<main>
<header><div class="eyebrow">GEO / Learning experiments</div><h1>GEO Learning Log</h1><p class="lede">An ongoing record of questions, experiments, data, and lessons from learning GEO.</p><div id="stage-1"><h2>Stage 1 · Who does AI recommend, and whose content does it cite?</h2><p class="lede">An observation of recommendations, sources, and answer differences in ChatGPT Search and Grok. This report records Stage 1; the learning log links to later stages and their evidence.</p></div></header>
{executive_summary}
{platform_findings}
<section class="section" id="repeat-stability"><h2>Observed Repeat Overlap</h2><blockquote class="report-note"><strong>Repeat comparisons are descriptive.</strong> Some runs differed in date or reasoning effort, and identical backend conditions could not be independently verified. ChatGPT Q2 spans October 29–30; Q3 also changes Extra High to Medium. Grok’s backend version and reasoning effort were not disclosed. Two repeats cannot estimate a stable consistency level.</blockquote><ul class="section-conclusions"><li><strong>Neither platform was more consistent across all questions in this batch.</strong> Grok’s two answers were closer on empirical research; the gaps were smaller for the other two questions.</li><li><strong>These values describe observed recommendation-set overlap only.</strong> Dates, reasoning effort, and account context were not fully controlled, so these values cannot rank inherent platform quality.</li></ul><p class="note section-lead">Recommendation overlap (Jaccard) = shared recommendations ÷ entities recommended at least once. It does not measure accuracy or effectiveness. Condition differences and unknown fields are listed for each group below.</p>{overlap_chart}<details><summary>View intersections, unions, and shared entities</summary>{overlap_table}</details></section>
{cmr_findings}
<section class="section" id="recommendation-frequency"><h2>Frequency of active recommendations</h2><ul class="section-conclusions"><li><strong>An entity’s visibility varies by question and platform.</strong> The charts compare recommendation counts by question and platform, showing which kinds of answers include each entity.</li></ul><p class="note section-lead">Each entity counts at most once per answer. The denominator is the number of complete answers in that group. All entities are expanded by default. Full C/M/R coding and evidence are retained in the public records.</p><div class="chart-grid">{chart}</div></section>
<div class="section-kicker" style="margin-top:64px">Methods and supporting records</div>
<blockquote class="report-note"><p>All submission dates: {h(date_label)} · Time zone: Asia/Shanghai</p><p>{condition_header}</p><p><strong>This small observational sample cannot establish GEO effectiveness. </strong> {h(short_limits) if short_limits else ''}Only completed main-sample answers are counted; historical attempts are excluded.</p></blockquote>
{method_section}
{condition_overview}
<details class="section detail-section" id="run-matrix"><summary>Test record overview · {len(runs)} / 12 planned slots</summary><div class="detail-content"><p class="note">The design uses 3 original English prompts × 2 platforms × 2 repeats. Each submission starts a fresh conversation and sends only the original prompt, without additional steering.</p><div class="table-wrap"><table><thead><tr><th>Platform</th><th>Question</th><th>Repeat</th><th>Date</th><th>Mode / model</th><th>Search status</th><th>Answer capture / citation mapping</th><th>Record status</th></tr></thead><tbody>{matrix}</tbody></table></div></div></details>
<details class="section detail-section" id="raw-records"><summary>Answer records and entity-level observations · {len(runs)} records</summary><div class="detail-content"><p class="note">The assistant read and coded each answer; there was no independent human double-coding review. Citation means the answer cites content published or bylined by the entity. Mention means the answer explicitly names it. Recommendation means the answer actively suggests using, reading, or following it. The three criteria are assessed separately: appearing in a source list does not automatically count as a recommendation. Evidence and notes explain borderline cases. Submission and capture times are displayed in UTC+8. Capture time is not the server’s generation-completion time; original ISO timestamps are retained in the data. Aggregation ignores only whitespace and case in entity names, otherwise using the coded names without additional automatic alias merging.</p>{records}</div></details>
{history_section}
{capture_history_section}
<details class="section detail-section" id="reading-boundaries"><summary>Interpretation limits</summary><div class="detail-content method-notes"><p>These records reflect answers under the account, region, UI mode, and visible search state at test time. A new conversation is not an independent account and does not guarantee that memory or personalization is disabled. A UI mode label alone cannot confirm the underlying model version.</p><p>Two repeats are a very small sample. Recommendations and citations may vary because of retrieval results, generation randomness, index updates, or account context. Experimental claims and recommendation rationales in the answers are retained as platform output, not independently verified findings of this report. Undetermined values are not counted as “No.” Citation-mapping completeness and answer status are recorded separately.</p></div></details>
<footer>This report is generated from public edited answer copies and entity-level observation records and can be read offline. Private conversation links and local raw evidence are not published. External source links may require access. All summaries can be recalculated from the published data.</footer>
</main></div><script>
function revealRecord(){{let id;try{{id=decodeURIComponent(location.hash.slice(1));}}catch{{return;}}let target=document.getElementById(id);if(!target)return;let node=target;while(node){{if(node.tagName==='DETAILS')node.open=true;node=node.parentElement;}}target.scrollIntoView({{block:'start'}});}}
addEventListener('hashchange',revealRecord);if(location.hash)revealRecord();
const tocLinks=[...document.querySelectorAll('.sidebar nav a')];
const tocTargets=tocLinks.map(link=>({{link,target:document.getElementById(link.hash.slice(1))}})).filter(item=>item.target).sort((a,b)=>a.target===b.target?0:(a.target.compareDocumentPosition(b.target)&Node.DOCUMENT_POSITION_FOLLOWING?-1:1));
let tocPending=false;
function updateToc(){{let current=tocTargets[0];for(const item of tocTargets){{if(item.target.getBoundingClientRect().top<=160)current=item;}}for(const item of tocTargets){{if(item===current)item.link.setAttribute('aria-current','location');else item.link.removeAttribute('aria-current');}}tocPending=false;}}
addEventListener('scroll',()=>{{if(!tocPending){{tocPending=true;requestAnimationFrame(updateToc);}}}},{{passive:true}});updateToc();
</script></body></html>'''
    return format_report_document(document)


def supplemental_review():
    """Read the declared post-hoc audit; never change the original C/M/R labels."""
    read = lambda name: json.loads((ROOT / 'data' / name).read_text()) if (ROOT / 'data' / name).exists() else None
    types, audit = read('stage1-entity-types.json'), read('stage1-source-audit.json')
    parts = ['<section class="section" id="supplemental-review"><h2>Supplemental resource review</h2>'
             '<blockquote class="report-note">Added after the original experiment. Entity types and the source audit are assistant judgments, not independent human validation. They do not replace strict entity names, C/M/R coding, or the original 2/20 Q3 overlap.</blockquote>']
    if types:
        labels = {x['id']:x['label'] for x in types.get('categories', [])}
        rows = []
        for platform in types.get('summary', []):
            for category in platform.get('categories', []):
                rows.append(f'<tr><td>{h(platform.get("scope","all_questions"))}</td><td>{h(platform["platform"])}</td><td>{h(labels.get(category["category"], category["category"]))}</td><td>{h(category["unique_entities"])}</td><td>{h(category["entity_answer_records"])}</td></tr>')
        parts.append('<h3>Recommended entities by declared primary type</h3><blockquote class="report-note">Rows labeled all_questions pool all three questions; Q3 rows use only that question’s two selected answers per platform. A strict entity name is assigned one primary type for this supplementary lens; overlapping roles are retained in the mapping rationale. Unique entities and entity-by-answer records have different denominators. A longer candidate list or a larger count of one type does not establish recommendation quality.</blockquote>')
        parts.append('<div class="table-wrap"><table><thead><tr><th>Scope</th><th>Platform</th><th>Entity type</th><th>Unique recommended entities</th><th>Recommendation records</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')
        parts.append('<p><a href="data/stage1-entity-types.json">Declared type mapping, definitions, counts and limitations</a></p>')
    if audit:
        rows = []
        for case in audit.get('cases', []):
            fields = ('existence', 'original_experiments', 'method_sample_reporting', 'indie_builder_fit', 'assessment')
            cells = ''.join(f'<td>{h(case.get(field))}</td>' for field in fields)
            rows.append(f'<tr><th scope="row">{h(case.get("entity"))}</th><td>{h(", ".join(case.get("selected_for_platforms", case.get("platforms", []))))}</td>{cells}</tr>')
        parts.append('<h3>Representative Q3 resource checks</h3><blockquote class="report-note">Five Q3 recommendations per platform were selected purposively, including shared resources and contrasting individual/organizational resources. This is not a random quality sample or a platform ranking. Checking that a page exists or describes a method does not replicate its experiments, verify every claim, or establish free access to every service.</blockquote>')
        parts.append('<div class="table-wrap"><table><thead><tr><th>Entity/resource</th><th>Selected for audit from</th><th>Existence</th><th>Original experiments</th><th>Methods and samples</th><th>Fit for independent builders</th><th>Assessment</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')
        parts.append('<p><a href="data/stage1-source-audit.md">Source-audit notes and checked links</a> · <a href="data/stage1-source-audit.json">Structured audit and access limits</a></p>')
    parts.append('</section>')
    return ''.join(parts)


READER_CSS = """
/* The concise report retains the established editorial identity. */
.reader-page main{max-width:1080px}.reader-page h1{max-width:26ch;font-size:38px;line-height:1.16}
.reader-page .lede{max-width:72ch}.reader-page p,.reader-page li{max-width:75ch}
.reader-page .sidebar-brand{margin-bottom:20px}.reader-page .sidebar nav a{font-size:14px}
.reader-page .section{margin-top:42px;padding-top:24px}.reader-page .executive-summary{margin-top:26px;padding-top:0}
.reader-page .conclusion-list li{font-size:16px;line-height:1.75;margin-bottom:20px}
.reader-page .finding-grid{gap:20px}.reader-page .finding-panel{border-top:1px solid var(--line)}
.reader-page .finding-number{font-size:28px}.reader-page .section-kicker,.reader-page .eyebrow{display:none}
.reader-page .report-note{border:1px solid #d3dfdc;border-left-width:1px;background:#f4f8f6;color:#465e65}
.reader-page .sidebar nav a{border-left-width:1px}.reader-page .compare-panel{border-top-width:1px}
a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:4px}
::selection{background:#d4ebe5;color:#132c38}*{scrollbar-color:#8aa8a0 #f2f6f6}
@media(max-width:760px){.reader-page h1{font-size:30px}.reader-page .conclusion-list{padding-left:20px}.reader-page .finding-grid{grid-template-columns:1fr}.reader-page .sidebar-brand{margin-bottom:12px}.reader-page .section{margin-top:32px}}
"""


def render_reader(runs, findings, appendix):
    """A small authored reading surface; all verbatim evidence stays in the appendix."""
    insights = findings['insights']
    q3 = next(x for x in insights['cross_platform'] if x['question_id'] == 'Q3')
    platforms = {x['platform']:x for x in insights['platforms']}
    a, b = platforms['ChatGPT Search'], platforms['Grok']
    nav = [('conclusions', 'Three findings'), ('main-findings', 'Recommended entity overlap'),
           ('repeat-stability', 'Observed repeat overlap'), ('cmr-distribution', 'C/M/R and citation scope'),
           ('supplemental-review', 'Resource review'), ('reading-boundaries', 'What this cannot show'),
           ('evidence', 'Methods and evidence')]
    sidebar = '<aside class="sidebar"><a class="sidebar-brand" href="#conclusions">GEO <span>Learning Log</span></a><nav aria-label="Report contents">' + ''.join(f'<a href="#{target}">{h(label)}</a>' for target,label in nav) + '<a href="technical-appendix.html">Full technical appendix</a></nav><p class="sidebar-foot">All sections expanded<br>Original answers and failures retained</p></aside>'
    panels = []
    for row in insights['cross_platform']:
        value = row['jaccard']
        panels.append(f'<article class="finding-panel"><h3>{h(row["question_id"])} · {h(QUESTION_LABELS[row["question_id"]])}</h3><p class="finding-number">{value:.1%}</p><div class="bar-track" role="img" aria-label="{h(row["question_id"])}: {row["intersection"]} shared of {row["union"]} recommended entities"><div class="bar-fill" style="width:{value*100:.4f}%"></div></div><p>{row["intersection"]} shared / {row["union"]} unique entities</p><blockquote class="report-note">{h("; ".join(f"{p}: {n}" for p,n in row["recommendation_counts"].items()))}</blockquote></article>')
    cmr_rows = ''.join(f'<tr><th scope="row">{h(x["platform"])}</th><td>{x["cited_recommendations"]}/{x["totals"]["recommendation"]}</td><td>{x["own_citation_coverage"]:.1%}</td><td>{x["recommendations_without_own_citation"]}</td></tr>' for x in insights['platforms'])
    pattern_rows = ''.join(f'<tr><th scope="row">{h(x["platform"])}</th><td>{x["observation_count"]}</td><td>{h("; ".join(f"{k}: {v}" for k,v in x["patterns"].items()))}</td></tr>' for x in insights['platforms'])
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>AI recommendations · GEO Learning Log</title><style>{CSS}{READER_CSS}</style></head><body class="reader-page"><div class="report-shell">{sidebar}<main>
<header><h1>Who does AI recommend, and whose content does it cite?</h1><p class="lede">A small repeated-query comparison of ChatGPT Search and Grok, covering learning resources, empirical research and practical GEO tutorials.</p></header>
<section id="conclusions" class="section executive-summary"><ul class="conclusion-list">
<li><strong>Q3 recommendations shared only 2 of 20 unique entities/resources.</strong> The {q3['jaccard']:.0%} overlap pools two answers per platform. The shared resources were <strong>GEO research (Aggarwal et al.)</strong> and <strong>The GEO Community</strong>. The lists mix papers, communities, organizations and individual creators; this is not a comparison of 20 creators.</li>
<li><strong>Observed own-content citations accompanied {a['cited_recommendations']}/{a['totals']['recommendation']} ChatGPT Search and {b['cited_recommendations']}/{b['totals']['recommendation']} Grok recommendation records.</strong> These {a['own_citation_coverage']:.1%} and {b['own_citation_coverage']:.1%} figures cover coded entity-by-answer records and captured citations only. They do not measure answer accuracy or inherent platform citation preferences.</li>
<li><strong>Two repeats produced different recommendation sets, with important condition differences.</strong> Neither platform had the greater overlap on every question. ChatGPT Q2 spans dates; Q3 also changes reasoning effort. Account memory was observed, and Grok’s backend conditions were undisclosed. These are descriptive overlaps, not estimates of stable consistency.</li>
</ul><blockquote class="report-note">3 original questions × 2 platforms × 2 repeats = <strong>12 selected complete answers</strong>. The archive also retains 10 other submissions and 37 captures; captures are not extra prompts. There was no optimization intervention, baseline or control group, so these observations cannot establish GEO effectiveness.</blockquote></section>
<section id="main-findings" class="section"><h2>Recommended entity overlap</h2><p>The selected recommendation sets differed for all three questions. Q3 had the lowest pooled cross-platform overlap in this batch.</p><div class="finding-grid">{''.join(panels)}</div><blockquote class="report-note">For each platform, pool the Recommendation=true names from both selected answers, ignoring only case and whitespace. Jaccard = shared names ÷ the union. This pooled statistic differs from the repeat-pair statistic below. Original prompts and strict labels are unchanged. Longer candidate lists do not establish higher recommendation quality.</blockquote></section>
<section id="repeat-stability" class="section"><h2>Observed Repeat Overlap</h2><blockquote class="report-note"><strong>Repeat comparisons are descriptive.</strong> Some runs differed in date or reasoning effort, and identical backend conditions could not be independently verified. ChatGPT Q2 spans October 29–30; Q3 changes both date and Extra High → Medium effort. Grok’s backend model version and reasoning effort were not disclosed. Two repeats cannot estimate a stable consistency level.</blockquote>{render_overlap(findings['groups'])}<blockquote class="report-note">Each bar compares one pair of selected answers to the identical original question, using Jaccard recommendation-set overlap. Recorded UI conditions matching does not verify matching backend conditions. Memory evidence and all six condition comparisons are preserved in the appendix.</blockquote><p><a href="technical-appendix.html#conditions">Dates, UI model labels and reasoning effort for every selected answer</a></p></section>
<section id="cmr-distribution" class="section"><h2>Citations, mentions and recommendations are separate observations</h2><p><strong>A citation does not automatically mean a recommendation.</strong> C records a citation to content published or bylined by the entity; M records an explicit name in the answer; R records an active suggestion to use, read or follow it.</p><div class="table-wrap"><table><thead><tr><th>Platform</th><th>Own/bylined citation among R records</th><th>Observed proportion</th><th>R without observed own-content C</th></tr></thead><tbody>{cmr_rows}</tbody></table></div><blockquote class="report-note">The denominator is coded Recommendation=true entity × answer records. The same entity in two answers counts twice. Third-party support is excluded from this own-content indicator. Missing own-content C does not mean the answer lacks supporting evidence. Source capture and assistant coding coverage limit this comparison.</blockquote><h3>Combinations among coded entities</h3><div class="table-wrap"><table><thead><tr><th>Platform</th><th>Entity-by-answer observations</th><th>Observed combinations</th></tr></thead><tbody>{pattern_rows}</tbody></table></div><blockquote class="report-note">These are conditional inventories of coded main recommendations and substantive discussion subjects, not every brand or source publisher. Grok source-only publishers were not exhaustively coded. Omitted letters mean false under the original coding rules; the counts cannot estimate market-wide mention rates.</blockquote><p><a href="technical-appendix.html#cmr-distribution">Complete C/M/R tables, examples and evidence</a></p></section>
<section id="supplemental-review" class="section"><h2>Resource types and a bounded source review</h2><p>The recommendations include several resource types. A declared post-hoc classification separates individual creators, papers/studies, communities, organizations and tools rather than treating them all as products or creators.</p><p>A purposive audit checks five Q3 recommendations per platform for existence, original experiments, reported methods/sample sizes and fit for independent builders. All ten selected pages were readable at the check.</p><p><strong>Relevance and original evidence are different checks.</strong> The selected Seer page interprets an academic study rather than establishing a Seer-run experiment. The selected GEO Lab manual describes a Perplexity experiment but reports inconsistent sample denominators and significance wording. These are page-specific qualifications, not judgments of either entity’s entire work.</p><blockquote class="report-note">This assistant audit is supplementary, not independent human validation or a representative quality ranking. An accessible page with a stated method does not verify all claims or reproduce the study. Original names, recommendation labels and the 2/20 overlap remain unchanged.</blockquote><p><a href="technical-appendix.html#supplemental-review">Type counts and the source-audit table</a> · <a href="data/stage1-entity-types.json">Type mapping</a> · <a href="data/stage1-source-audit.md">Audit notes</a></p></section>
<section id="reading-boundaries" class="section"><h2>What this cannot show</h2><ul><li><strong>No causal GEO conclusion:</strong> there is no content intervention, pre-optimization baseline, control group, predefined brand panel or conversion measure.</li><li><strong>No inherent platform ranking:</strong> dates, reasoning effort, account context, source capture and undisclosed backend conditions limit the comparison.</li><li><strong>No finding that an absent brand has poor GEO:</strong> answers depend on the sampled questions and conditions, and the mixed recommendation inventories are not a brand census.</li></ul><blockquote class="report-note">The assistant coded the answers; no independent human double-coding review was completed. The separate source spot-check does not remove coding subjectivity or validate every external experiment. Multiple tutorials citing the same study are not independent replications.</blockquote></section>
<section id="evidence" class="section"><h2>Methods and evidence</h2><p><a href="technical-appendix.html">Read the full technical appendix</a> for original prompts, all 12 selected answers, the 10 other submissions, capture corrections and entity-level evidence. All appendix headings remain expanded.</p><p><a href="public-data.zip">Download redacted Stage 1 data</a> · <a href="findings.json">Computed findings</a> · <a href="data/publication-notes.json">Publication scope</a> · <a href="https://github.com/helen-bird/geo-platform-observation">Repository and learning log</a></p><blockquote class="report-note">Unrelated personal-context passages are omitted and marked. Private conversations, screenshots and complete local evidence are excluded. Original prompts, recommended entities, citation attribution and numerical results are preserved. Public annotations are English; verbatim answers retain only marked privacy edits.</blockquote></section>
<footer>Stage 1 remains at its original website address. The technical appendix and versioned data preserve the evidence behind this shorter reader.</footer></main></div></body></html>'''
    # Old deep links route only to a fixed, known appendix ID; no arbitrary URL destination.
    reader_ids = set(re.findall(r'\bid="([^"]+)"', document))
    appendix_ids = set(re.findall(r'\bid="([^"]+)"', appendix))
    routed = sorted(appendix_ids - reader_ids)
    router = '<script>(()=>{const known=new Set(' + json.dumps(routed) + ');function route(){let id;try{id=decodeURIComponent(location.hash.slice(1));}catch{return;}if(known.has(id))location.replace("technical-appendix.html#"+encodeURIComponent(id));}addEventListener("hashchange",route);route();})();</script>'
    document = document.replace('</body>', '<noscript><p><a href="technical-appendix.html">For older evidence links, open the full technical appendix.</a></p></noscript>' + router + '</body>')
    return format_report_document(document)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/runs.json")
    parser.add_argument("--attempts", type=Path, default=ROOT / "data/attempts.json", help="Optional array of real submissions not selected in main runs; do not duplicate main runs here.")
    parser.add_argument("--capture-history", type=Path, default=ROOT / "data/capture-history.json", help="Optional capture attempts and diagnostic corrections; these are not new prompts.")
    parser.add_argument("--output", type=Path, default=ROOT / "report.html")
    parser.add_argument("--findings", type=Path, default=ROOT / "findings.json")
    args = parser.parse_args()
    runs = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(runs, list) or any(not isinstance(run, dict) for run in runs):
        raise SystemExit("Expected runs.json to contain an array of run objects.")
    attempts = json.loads(args.attempts.read_text(encoding="utf-8")) if args.attempts.exists() else []
    if not isinstance(attempts, list) or any(not isinstance(run, dict) for run in attempts):
        raise SystemExit("Expected attempts.json to contain an array of historical attempt objects.")
    history = json.loads(args.capture_history.read_text(encoding="utf-8")) if args.capture_history.exists() else None
    run_ids = [str(run.get("id")) for run in runs if run.get("id")]
    if len(set(run_ids)) != len(run_ids):
        raise SystemExit("Duplicate run IDs found; resolve duplicate records before reporting.")
    findings = aggregate(runs, attempts, history)
    findings["insights"] = summarize_insights(runs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.findings.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(runs, findings, attempts, history), encoding="utf-8")
    args.findings.write_text(json.dumps(findings, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "findings": str(args.findings), "completed_runs": findings["completed_runs"], "recorded_runs": len(runs), "historical_attempts": len(attempts), "total_prompts": findings["total_prompts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
