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
QUESTION_LABELS = {"Q1": "学习资源发现", "Q2": "寻找实证研究", "Q3": "寻找内容创作者"}
STATUS_LABELS = {"completed": "已完成", "blocked": "受阻", "incomplete": "未完成"}
METRICS = (("mention", "Mention · 明确提及"), ("citation", "Citation · 引用其内容"), ("recommendation", "Recommendation · 主动推荐"))


def text(value):
    if value is None or value == "":
        return "未记录"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def h(value):
    return escape(text(value), quote=True)


def display_timestamp(value):
    if not value:
        return "未记录"
    original = str(value)
    try:
        parsed = datetime.fromisoformat(original[:-1] + "+00:00" if original.endswith("Z") else original)
    except ValueError:
        return original + "（按原记录显示）"
    if parsed.tzinfo is None:
        return original + "（时区未标注）"
    return parsed.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S UTC+8")


def key(value):
    return " ".join(str(value or "").split()).casefold()


EFFORT_PATTERN = re.compile(r"\b(extra[\s_-]*high|xhigh|medium|high|low|minimal|none|max|ultra)\b|极高|中等", re.I)
EFFORT_LABELS = {"extrahigh": "Extra High", "xhigh": "Extra High", "极高": "Extra High", "medium": "Medium", "中等": "Medium", "high": "High", "low": "Low", "minimal": "Minimal", "none": "None", "max": "Max", "ultra": "Ultra"}


def known_condition_value(value):
    if value is None or value == "":
        return None
    value = str(value).strip()
    if value.startswith(("未披露", "未记录", "未知")) or key(value) in {"unknown", "not disclosed", "not recorded", "n/a"}:
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
    model_comparison = re.sub(r"[（(](?:界面选择标签|界面标签|UI label)[）)]", "", model, flags=re.I).strip() if model else None
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
    fields = (("test_date", "测试日期"), ("model_comparison", "模型标签"), ("reasoning_effort", "思考强度"), ("mode_comparison", "界面模式"))
    differences, unknown = [], []
    for field, label in fields:
        a, b = conditions[0][field], conditions[1][field]
        if a is None or b is None:
            unknown.append(label)
        elif key(a) != key(b):
            differences.append({"field": field, "label": label, "first": a, "second": b})
    if differences:
        status, label = "different", "条件不同，仅描述性比较"
    elif unknown or any(c["date_conflict"] for c in conditions):
        status, label = "not_fully_observable", "条件信息不全，仅描述性比较"
    else:
        status, label = "same_observed", "已记录界面条件一致；后端条件未经独立核实"
    return {"status": status, "label": label, "differences": differences, "unknown_fields": unknown, "runs": conditions}


def summarize_conditions(runs):
    records = [run_conditions(run) for run in runs]
    platforms = []
    for platform in sorted({str(c["platform"] or "未记录") for c in records}):
        selected = [c for c in records if str(c["platform"] or "未记录") == platform]
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
        return '<span class="flag yes">是</span>'
    if value is False:
        return '<span class="flag no">否</span>'
    return '<span class="flag unknown">未判定</span>'


def mapping_label(value):
    if value is True:
        return "已核对可确认的引用链接；对应方法见逐项证据"
    if value is False:
        return "不完整：部分内部引用未映射为 URL"
    return "未记录映射完整性"


def personalization_evidence(run):
    supplied = run.get("personalization_evidence")
    if supplied:
        return str(supplied)
    answer = str(run.get("answer_text") or "")
    # Show only the specific observed personalization, not a guessed profile.
    plain = re.sub(r"[*_`]", "", answer)
    start = plain.casefold().find("given your focus")
    if start >= 0 and "original content on x" in plain[start:start + 650].casefold():
        end = plain.find("\n\n", start)
        if end < 0 or end > start + 650:
            end = min(len(plain), start + 650)
        return plain[start:end].strip()
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
    return source.get("domain") or urlparse(str(source.get("url") or "")).hostname or "未记录"


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
    platforms = sorted({str(r.get("platform") or "未记录") for r in runs})
    for platform in platforms:
        for question_id in QUESTION_LABELS:
            groups[(platform, question_id)]
    for run in completed:
        groups[(str(run.get("platform") or "未记录"), str(run.get("question_id") or "未记录"))].append(run)
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
    sections = [("conclusions", "先看结论"), ("main-findings", "两平台推荐差异"),
                ("repeat-stability", "两次回答稳定性"), ("cmr-distribution", "C/M/R 分布"),
                ("effect-limits", "GEO 效果判断边界"), ("recommendation-frequency", "对象推荐频次")]
    references = [("method", "采集方法与限制"), ("conditions", "模型与测试条件"),
                  ("run-matrix", "测试记录总表"), ("raw-records", "12 份原始回答"),
                  ("attempt-history", "失败提问历史"), ("capture-history", "采集与更正记录"),
                  ("reading-boundaries", "阅读边界")]
    def links(items):
        return "".join(f'<a href="#{target}">{h(label)}</a>' for target, label in items)
    records = "".join(f'<a class="record-link" href="#run-{i}">{"ChatGPT" if r.get("platform") == "ChatGPT Search" else h(r.get("platform"))} · {h(r.get("question_id"))} · 第 {h(r.get("repeat"))} 次</a>' for i, r in enumerate(runs, 1))
    return f'<aside class="sidebar"><a class="sidebar-brand" href="#conclusions">GEO <span>观察实验</span></a><nav aria-label="报告目录"><p class="toc-label">主要发现</p>{links(sections)}<p class="toc-label">方法与证据</p>{links(references)}<div class="record-links" aria-label="原始回答索引">{records}</div></nav><p class="sidebar-foot">结论先行 · 图表佐证<br>所有章节默认展开</p></aside>'


def render_executive_summary(findings):
    insights = findings["insights"]
    platforms = {p["platform"]: p for p in insights["platforms"]}
    q3 = next((q for q in insights["cross_platform"] if q["question_id"] == "Q3"), None)
    bullets = []
    if q3 and q3["jaccard"] is not None:
        bullets.append(f'<li><strong>创作者题中，两平台选出的推荐对象差异最大。</strong>合并各自两轮名单后，共同对象仅 {q3["intersection"]} / {q3["union"]}，跨平台重合度为 <b>{q3["jaccard"]:.1%}</b>。</li>')
    if all(p in platforms for p in ("ChatGPT Search", "Grok")):
        a, b = platforms["ChatGPT Search"], platforms["Grok"]
        bullets.append(f'<li><strong>本批 ChatGPT 的推荐更常伴随对象自有内容引用。</strong>ChatGPT 为 <b>{a["cited_recommendations"]}/{a["totals"]["recommendation"]}（{a["own_citation_coverage"]:.1%}）</b>，Grok 为 <b>{b["cited_recommendations"]}/{b["totals"]["recommendation"]}（{b["own_citation_coverage"]:.1%}）</b>。被推荐、被提及和被引用可以分开出现。</li>')
    bullets.append('<li><strong>没有一个平台在三类问题上都更稳定。</strong>本批实证研究题中 Grok 两轮更接近；学习资源题和创作者题则没有同样明显的差距。</li>')
    bullets.append('<li><strong>这些差异不能说明某个品牌的 GEO 优化做得好或差。</strong>本次衡量的是特定问题与条件下的可见性，未验证优化干预带来的效果，也不代表点击、购买或转化。</li>')
    scope = f'当前 {findings["completed_runs"]} / {findings["planned_runs"]} 份主回答完整，共 {insights["observation_count"]} 条已编码“主体×回答”观察。实际提交 {findings["total_prompts"]} 次、采集 {findings["capture"]["capture_history_count"]} 次；另有 {findings["historical_attempts"]} 次未纳入主样本的提问，完整保留且不并入统计。'
    return '<section class="section executive-summary" id="conclusions"><div class="section-kicker">先看结论</div><h2>四个主要发现</h2><ul class="conclusion-list">' + "".join(bullets) + f'</ul><blockquote class="report-note"><strong>阅读口径</strong><p>{h(scope)}</p><p>每题每平台只有两次重复，测试跨日、思考强度存在变化，并观察到账户记忆影响。实验没有优化前基线、干预或对照组，因此不能作因果判断或平台固有优劣排名。</p></blockquote></section>'


def render_insight_sections(runs, findings):
    insights = findings["insights"]
    cross_panels = []
    for row in insights["cross_platform"]:
        ratio = row["jaccard"]
        label = f'{ratio:.1%}' if ratio is not None else "待完整数据"
        counts = "；".join(f'{p} {n} 个' for p, n in row["recommendation_counts"].items())
        shared = "、".join(row["shared_entities"]) or "无已确认共同推荐"
        cross_panels.append(f'<article class="finding-panel"><h3>{h(row["question_id"])} · {h(QUESTION_LABELS[row["question_id"]])}</h3><div class="finding-number">{label}</div><p>共同 {row["intersection"]} / 合计 {row["union"]} 个对象</p><p class="note">{h(counts)}</p><details><summary>共同推荐对象</summary><p class="small">{h(shared)}</p></details></article>')
    stable = []
    for group in findings["groups"]:
        if group["question_id"] == "Q3" and group.get("repeat_overlap"):
            shared = "、".join(group["repeat_overlap"]["shared_entities"]) or "无共同对象"
            stable.append(f'<article class="compare-panel"><h3>{h(group["platform"])} · 两轮都推荐</h3><p>{h(shared)}</p></article>')
    resource_counts = []
    for group in findings["groups"]:
        overlap = group.get("repeat_overlap")
        if group["question_id"] == "Q1" and overlap:
            resource_counts.append(f'{group["platform"]} {overlap["repeat_1_recommendations"]} / {overlap["repeat_2_recommendations"]} 个')
    cross_section = f'''<section class="section" id="main-findings"><h2>两平台选出的推荐对象，差异有多大？</h2><ul class="section-conclusions"><li><strong>创作者题的跨平台分歧最明显。</strong>不同平台选出的资源并不相同，下方三个问题的重合度分别展示这种差异。</li><li><strong>共同推荐名单也不同。</strong>ChatGPT 与 Grok 在 Q3 各自形成了一组两轮都出现的对象；这只是本次观察，不能推断为长期平台偏好。</li></ul><p class="note">下方先合并每个平台的两轮推荐，再比较两个集合：跨平台重合度 = 共同对象 ÷ 两平台并集。每组分别有 2 份完整回答；这与下一节逐平台的“两次回答重合度”使用不同的集合，不能混为一项指标。</p><div class="finding-grid">{"".join(cross_panels)}</div><h3 style="margin-top:28px">Q3 · 创作者题的共同推荐名单</h3><div class="compare-grid">{"".join(stable)}</div><p class="note" style="margin-top:18px">Q1 的两轮推荐数分别为 {h("；".join(resource_counts))}。学习资源题中 Grok 名单更长；名单长度不能直接表示回答质量或稳定性。Q3 的共同推荐名单只描述本次两轮，不能推断为平台长期偏好。</p></section>'''

    coverage = []
    for row in insights["platforms"]:
        numerator, denominator = row["cited_recommendations"], row["totals"]["recommendation"]
        value = row["own_citation_coverage"]
        ratio = f'{value:.1%}' if value is not None else "不适用"
        bar = f'<div class="bar-track" role="img" aria-label="{h(row["platform"])}：{numerator}/{denominator} 条推荐同时引用对象自有内容"><div class="bar-fill" style="width:{(value or 0)*100:.4f}%"></div></div>'
        coverage.append(f'<article class="compare-panel"><h3>{h(row["platform"])}</h3><div class="finding-number">{ratio}</div>{bar}<p style="margin-top:12px">{numerator} / {denominator} 条推荐同时引用对象自有或署名内容</p><p class="note">另有 {row["recommendations_without_own_citation"]} 条推荐未观察到这类引用；{row["recommendations_with_unknown_citation"]} 条尚未判定。</p></article>')

    pattern_labels = [("CMR", "C＋M＋R", "#176b62"), ("MR", "M＋R，无自有 C", "#547997"), ("CM", "C＋M，无 R", "#866a9c"), ("C", "仅 C", "#9a6d23"), ("M", "仅 M", "#66747e"), ("CR", "C＋R，无 M", "#496f48"), ("R", "仅 R", "#83534f"), ("none", "三项均否", "#69777a"), ("unknown", "含待判定项", "#666666")]
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
                segments.append(f'<span class="cmr-segment" style="width:{count/n*100:.6f}%;background:{color}" title="{h(label)}：{count} / {n}">{count if count/n >= .06 else ""}</span>')
        caption = "；".join(labels)
        stacks.append(f'<div class="distribution-row"><div class="distribution-label"><strong>{h(row["platform"])}</strong><span>{n} 条主体×回答观察</span></div><div class="cmr-stack" role="img" aria-label="{h(row["platform"])}：{h(caption)}">{"".join(segments)}</div><p class="distribution-counts">{h(caption)}</p></div>')
    matrix_rows = []
    by_question = {(r["question_id"], r["platform"]): r for r in insights["by_question"]}
    for q in QUESTION_LABELS:
        cells = []
        for platform in ("ChatGPT Search", "Grok"):
            row = by_question.get((q, platform))
            if row:
                totals = row["totals"]
                cells.append(f'<td>{totals["citation"]} / {totals["mention"]} / {totals["recommendation"]}<div class="note">{row["observation_count"]} 条观察，{row["answer_count"]} 份回答</div></td>')
            else:
                cells.append('<td>未记录</td>')
        matrix_rows.append(f'<tr><th scope="row">{h(q)} · {h(QUESTION_LABELS[q])}</th>{"".join(cells)}</tr>')
    examples = [
        ("三项都有", "C-Q1-R1-A2", "Ahrefs", "自有教程被引用，名字明确出现，也被主动推荐。"),
        ("引用与提及", "C-Q2-R2-A3", "Axios", "报道被用来说明测量波动，没有被主动推荐为学习资源。"),
        ("只有引用", "C-Q3-R2-A3", "Relevance", "正文推荐 Seer，实际锚点指向 Relevance；引用出版者未被点名或推荐。"),
        ("只有提及", "C-Q2-R2-A3", "Muck Rack", "作为研究方被点名，引用的是 Axios 的第三方报道。"),
        ("推荐，无自有引用", "G-Q1-R1", "Bing Webmaster Tools", "明确被推荐，但没有观察到其自有内容被直接引用。"),
    ]
    example_rows = []
    for label, run_id, entity, explanation in examples:
        match = next(((i, r, o) for i, r in enumerate(runs, 1) if r.get("id") == run_id for o in r.get("observations") or [] if o.get("entity") == entity), None)
        if match:
            index, run, obs = match
            example_rows.append(f'<tr><td>{h(label)}</td><td><strong>{h(entity)}</strong><div class="note">{h(run["platform"])} · {h(run["question_id"])}</div></td><td>{flag(obs["citation"])}</td><td>{flag(obs["mention"])}</td><td>{flag(obs["recommendation"])}</td><td>{h(explanation)} <a href="#run-{index}">查看判定与原文</a></td></tr>')
    cmr_section = f'''<section class="section" id="cmr-distribution"><h2>被引用、被提及、被推荐，可以分开出现</h2><ul class="section-conclusions"><li><strong>本批 ChatGPT 的推荐更常伴随对象自有内容引用。</strong>下方用相同定义、各自的推荐记录作分母比较。</li><li><strong>引用、提及和推荐可以分开出现。</strong>内容被用作依据，不一定带来品牌曝光；对象被推荐，也可能由第三方内容支撑。</li></ul><blockquote class="report-note definition-note"><dl class="metric-defs"><div><dt>C · Citation</dt><dd>对象自己发布或署名的内容被回答引用。</dd></div><div><dt>M · Mention</dt><dd>回答正文明确点名对象。</dd></div><div><dt>R · Recommendation</dt><dd>回答主动建议使用、阅读或关注对象。</dd></div></dl></blockquote><p class="note">C/M/R 分别判断，不构成严格的三级漏斗；同一对象可以同时满足其中多项。未见自有引用不代表回答没有依据。</p><h3>推荐记录中，有多少同时获得自有内容引用？</h3><div class="compare-grid">{"".join(coverage)}</div><p class="note" style="margin-top:14px">分母是本批已编码的推荐记录，不是所有品牌，也不是品牌被推荐的概率。未见自有引用不等于回答没有依据。</p><h3 style="margin-top:28px">C/M/R 组合分布</h3><p class="note">共 {insights["observation_count"]} 条“主体×回答”记录；同一对象在两份回答中出现算两条。条形宽度按各平台观察数归一，文字给出绝对数量；未列字母均为“否”。对象包括品牌、机构、创作者和研究，不全是产品。</p><div class="cmr-legend">{legend}</div>{"".join(stacks)}<p class="note"><strong>编码范围限制：</strong>只统计已编码的主要推荐与实质讨论对象，没有穷尽所有来源出版者。Grok 的来源专属对象未全量编码，不能把“仅 C＝0”解释为它不会只引用而不提及。本批问题本身要求推荐，高推荐占比也不能代表市场平均水平。</p><h3>分问题核对：C / M / R 次数</h3><p class="note">三个数字分别计数，可以重叠，不能相加为对象总数。</p><div class="table-wrap"><table class="comparison-table"><thead><tr><th>问题</th><th>ChatGPT · C / M / R</th><th>Grok · C / M / R</th></tr></thead><tbody>{"".join(matrix_rows)}</tbody></table></div><details><summary>五种组合的实际例子与原文</summary><div class="table-wrap"><table class="case-table compact"><thead><tr><th>情况</th><th>对象与回答</th><th>C</th><th>M</th><th>R</th><th>解释与证据</th></tr></thead><tbody>{"".join(example_rows)}</tbody></table></div></details><aside class="interpretation" id="effect-limits"><h3>这些结果不能判断某个品牌的 GEO 优化做得好或差</h3><p>可以比较的是：本组问题、日期、账号与模式下，对象获得了多少引用、提及和推荐。这不是优化效果、内容质量或平台固有优劣的排名，也不代表点击、购买或转化。</p><p>本次没有预先固定待评品牌名单，没有实施优化干预，也没有优化前基线或对照组；每题每平台只有两次重复。测试跨日、思考强度变化，且观察到账户记忆影响。未出现的对象不能直接判为“GEO 做得差”。</p><p class="note">若要评估优化效果，需要固定品牌、问题与条件，加入优化前基线、对照和更多重复，分别追踪 C/M/R 的变化。多个教程转述同一篇 GEO 论文也不等于多份独立实证；本报告未独立核验外部研究和效果主张。</p></aside></section>'''
    return cross_section, cmr_section


def render_frequency(group):
    denominator = group["completed_runs"]
    if denominator == 0:
        return f'<div class="chart-panel"><h3>{h(group["platform"])} · {h(group["question_id"])}</h3><p class="chart-caption">{h(QUESTION_LABELS.get(group["question_id"], ""))}</p><p class="empty"><strong>无完整可分析正文</strong><br>未计算推荐频次，不能解读为没有推荐。</p></div>'
    rows = [x for x in group["frequencies"] if x["recommendation"] > 0]
    def render_bar(row):
        return f'<div class="chart-row"><span>{h(row["entity"])}</span><div class="bar-track" role="img" aria-label="{h(row["entity"])}：{row["recommendation"]} / {denominator} 次回答主动推荐"><div class="bar-fill" style="width:{row["recommendation"] / denominator * 100:.4f}%"></div></div><span class="bar-value">{row["recommendation"]}/{denominator}</span></div>'
    bars = "".join(render_bar(row) for row in rows[:8])
    if len(rows) > 8:
        bars += f'<details><summary>其余 {len(rows) - 8} 个推荐对象</summary>' + "".join(render_bar(row) for row in rows[8:]) + '</details>'
    if not bars:
        bars = '<p class="empty">正文已取得，观察编码待完成或审查；不能解读为没有推荐。</p>' if group["recommendation_coding_incomplete"] else '<p class="empty">没有已标记为“主动推荐”的对象。</p>'
    coding_note = '<p class="note">含未判定或尚未编码的推荐记录；条形仅显示已确认的推荐次数。</p>' if group["recommendation_coding_incomplete"] else ""
    comparison = (group.get("repeat_overlap") or {}).get("condition_comparison")
    condition_note = render_condition_comparison(comparison) if comparison and comparison["status"] == "different" else ""
    return f'<div class="chart-panel"><h3>{h(group["platform"])} · {h(group["question_id"])}</h3><p class="chart-caption">{h(QUESTION_LABELS.get(group["question_id"], ""))} · 已完成 {denominator} 次</p>{coding_note}{condition_note}{bars}</div>'


def render_condition_comparison(comparison):
    if not comparison:
        return ""
    details = [f'{d["label"]}：{d["first"]} → {d["second"]}' for d in comparison["differences"]]
    if comparison["unknown_fields"]:
        details.append("未充分记录：" + "、".join(comparison["unknown_fields"]))
    if any(c["date_conflict"] for c in comparison["runs"]):
        details.append("日期字段与提问时间存在冲突，需核对原始证据")
    detail_html = f'<br>{h("；".join(details))}' if details else ""
    return f'<p class="note"><strong>{h(comparison["label"])}</strong>{detail_html}</p>'


def render_condition_overview(summary):
    rows = []
    for platform in summary["platforms"]:
        for condition in platform["records"]:
            conflict = '<div class="note">日期字段与提交时间不一致</div>' if condition["date_conflict"] else ""
            rows.append(f'<tr><td>{h(condition["run_id"])}</td><td>{h(platform["platform"])}<br>{h(condition["question_id"])} · 第 {h(condition["repeat"])} 次</td><td>{h(condition["test_date"])}{conflict}</td><td>{h(condition["model_label"] or "具体版本未披露")}</td><td>{h(condition["reasoning_effort"] or "未披露")}</td><td>{h(condition["mode_label"])}</td><td>{h(STATUS_LABELS.get(condition["status"], condition["status"]))}</td></tr>')
    table = '<div class="table-wrap"><table class="compact"><thead><tr><th>主记录</th><th>平台 / 重复</th><th>提问日期</th><th>模型界面标签</th><th>思考强度</th><th>完整模式标签</th><th>正文状态</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>' if rows else '<p class="empty">尚无主记录条件。</p>'
    return '<details class="section detail-section" id="conditions"><summary>主记录的日期、模型与思考强度</summary><div class="detail-content"><p class="note">这里展示当前选中的主记录，包含未完成位置；频次与重合度仍只使用 completed 样本。日期取实际提问记录，不用恢复或继续工作日期代替。思考强度优先读明确字段，其次读界面模式标签；未披露值不推断。即使模型标签相同，思考强度不同时也视为不同条件；同一界面标签也不保证底层模型路由一致。</p>' + table + '</div></details>'


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
                label, detail = "缺失", "无完整可分析正文"
            elif overlap is None:
                label, detail = "—", "两次重复尚未同时完成"
            elif overlap["recommendation_coding_incomplete"]:
                label, detail = "待编码", "推荐判定尚未完成"
            elif value is None:
                label, detail = "不适用", "两次均无主动推荐对象"
            else:
                label = f"{value:.1%}"
                detail = f'共同 {overlap["intersection"]} / 合计 {overlap["union"]} 个对象'
            bar = f'<div class="bar-track" role="img" aria-label="{h(group["platform"])} {h(question_id)} 推荐对象重合度 {h(label)}"><div class="bar-fill" style="width:{value * 100:.4f}%"></div></div>' if value is not None else ""
            comparison_note = render_condition_comparison(overlap.get("condition_comparison")) if overlap else ""
            rows.append(f'<div class="overlap-item"><div class="overlap-label"><span>{h(group["platform"])}</span><strong>{h(label)}</strong></div>{bar}<div class="overlap-detail">{h(detail)}</div>{comparison_note}</div>')
        panels.append(f'<div class="chart-panel"><h3>{h(question_id)} · {h(QUESTION_LABELS.get(question_id))}</h3>{"".join(rows)}</div>')
    return '<div class="overlap-grid">' + "".join(panels) + '</div>' if panels else '<p class="empty">暂无可计算重合度的记录。</p>'


def render_observations(run):
    rows = []
    for obs in run.get("observations") or []:
        urls = obs.get("source_urls") or []
        if isinstance(urls, str):
            urls = [urls]
        source_links = "<br>".join(link(url) for url in urls) or "未记录"
        notes = f'<div class="note">{h(obs["notes"])}</div>' if obs.get("notes") else ""
        rows.append(f'<tr><td><strong>{h(obs.get("entity"))}</strong><div class="note">{h(obs.get("entity_type"))}</div></td><td>{flag(obs.get("citation"))}</td><td>{flag(obs.get("mention"))}</td><td>{flag(obs.get("recommendation"))}</td><td><div class="evidence">{h(obs.get("evidence"))}</div>{notes}</td><td class="small">{source_links}</td></tr>')
    if not rows:
        return '<p class="empty">本次尚无逐条观察编码记录。</p>'
    return '<div class="table-wrap"><table class="cmr-table compact"><thead><tr><th>对象</th><th>Citation</th><th>Mention</th><th>Recommendation</th><th>判定证据 / 备注</th><th>关联来源 URL</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'


def render_sources(run):
    partitions = source_partitions(run)
    mapping_note = '<p class="note"><strong>正文引用映射不完整。</strong>已观测正文链接不等于全部引用；未映射的标记保留在原始证据中。</p>' if run.get("citation_mapping_complete") is False else ""
    labels = {"answer": ("正文引用相关链接（含人工对应）", "这些链接来自正文直链、正文 Sources 列表，或依据引用标签与来源面板所作的人工对应；逐项方法和 Citation 归属以观察编码为准。"), "retrieval": ("检索来源面板", "这些是平台检索或来源面板记录，不等于正文实际引用，也不据此新增 Mention、Citation 或 Recommendation。"), "unknown": ("来源类型尚未确定", "旧记录未充分注明链接位置，保留用于追溯，不自动归为正文引用。")}
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
                context_html += f'<div class="small">匹配证据：{render_evidence_files(s["evidence_files"])}</div>'
            rows.append(f'<tr><td>{index}</td><td>{h(s.get("title") or s.get("text"))}<br>{link(s.get("url"))}{context_html}</td><td>{h(source_domain(s))}</td><td>{h(s.get("kind") or s.get("source_kind") or kind)}</td></tr>')
        table = '<div class="table-wrap"><table class="compact"><thead><tr><th>#</th><th>来源及具体 URL</th><th>域名</th><th>记录类型</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>' if rows else '<p class="empty">未取得可观测正文链接；不代表回答没有引用。</p>'
        output.append(f'<details><summary>{title} · {len(sources)} 条记录</summary><p class="note">{explanation}</p>{table}</details>')
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
    return "<br>".join(links) or "未记录"


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
    labels = {"started_at": "提问时间", "finished_at": "采集时间", "date_local": "提问日期", "model_label": "模型标签", "mode_label": "模式标签", "model_evidence": "模型证据"}
    rows = []
    for correction in corrections:
        field = correction.get("field")
        original = correction.get("original_value")
        previous = correction.get("previous_effective_value")
        previous_note = f'<div class="note">更正前派生值：{h(previous)}</div>' if "previous_effective_value" in correction and previous != original else ""
        files = render_evidence_files(correction.get("evidence_files"))
        rows.append(f'<tr><td>{h(labels.get(field, field))}<br><code>{h(field)}</code></td><td><code>{h(original)}</code>{previous_note}</td><td><code>{h(correction.get("value"))}</code></td><td><div class="evidence">{h(correction.get("evidence"))}</div>{files}</td></tr>')
    return f'<details><summary>元数据更正 · {len(corrections)} 项</summary><p class="note">更正用于派生记录和本报告显示；原始 raw 文件保留原值。时间在此保留原始 ISO 表示，便于与保存证据逐字核对。</p><div class="table-wrap"><table class="compact"><thead><tr><th>字段</th><th>原始值</th><th>更正后值</th><th>依据与证据文件</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></details>'


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
        observed_html = f'<p class="small">原始提交文本（JSON 字符串表示，保留空白）</p><pre class="raw-answer" lang="en">{h(json.dumps(observed, ensure_ascii=False))}</pre>'
    else:
        observed_html = '<p class="note">未保存原始提交文本观测，不能用派生表示替代原始证据。</p>'
        if run.get("submitted_prompt") is not None:
            observed_html += f'<p class="small">派生提交表示（非原始观测）</p><pre class="raw-answer" lang="en">{h(json.dumps(run["submitted_prompt"], ensure_ascii=False))}</pre>'
    if normalized is None:
        check_note = "未提供提交格式标准化校验记录；原始文本原样保留。"
    elif normalized == canonical:
        check_note = "装配校验记录显示：标准化提交格式后与标准英文题目逐字一致。"
        if "chatgpt" in str(run.get("platform") or "").casefold():
            check_note += "网页搜索工具 chip 在首部或尾部的位置、@ 符号与相邻空格属于提交记录的格式差异，未改写英文题目，也未添加英文引导。"
    else:
        check_note = "标准化提交记录与标准英文题目不一致，需要核查；不能据此认定原题保持不变。"
    return f'<details><summary>原始提交文本与标准英文题目</summary><p class="small">标准英文题目（canonical，原样保留）</p><div class="question" lang="en">{h(canonical)}</div>{observed_html}<p class="note">{h(check_note)}</p><p class="note">提交文本来源：{h(provenance or "原始记录未单独注明")}</p></details>'


def render_provenance(run):
    provenance = capture_provenance(run)
    correction_html = render_metadata_corrections(run)
    submitted_html = render_submitted_prompt(run)
    if not provenance and not correction_html and not submitted_html:
        return ""
    fields = [("原记录状态", provenance.get("original_status")), ("当前采集 ID", provenance.get("selected_capture_id") or run.get("capture_id")), ("选中证据方式", provenance.get("method")), ("证据采集时间", display_timestamp(provenance.get("captured_at"))), ("是否同一会话", "是" if provenance.get("same_conversation") is True else "否" if provenance.get("same_conversation") is False else "未判定"), ("正文完整性审查", provenance.get("body_completeness") or provenance.get("completeness_status")), ("审查备注", provenance.get("review_notes"))]
    metadata = "".join(f'<div><dt>{h(label)}</dt><dd>{h(value)}</dd></div>' for label, value in fields)
    files = [("原始采集证据", provenance.get("original_raw_file")), ("本次选中证据", provenance.get("selected_capture_file")), ("补充证据", provenance.get("evidence_files"))]
    file_html = "".join(f'<p class="small">{label}：{render_evidence_files(value)}</p>' for label, value in files if value)
    history_refs = f'<p class="note">此提问保留 {len(run["capture_history"])} 次采集，详见报告末尾的采集历史或 <a href="data/capture-history.json">完整采集记录</a>。</p>' if run.get("capture_history") else ""
    public_note = '<p class="note">通过分享对话框预览采集，但没有创建公开分享链接。</p>' if provenance.get("public_share_created") is False else ""
    return f'<details><summary>正文采集证据与恢复路径</summary><dl class="run-meta">{metadata}</dl>{file_html}{history_refs}{public_note}{correction_html}{submitted_html}<p class="note">同一会话的再次采集与新的提问是两件事。报告按最终记录状态统计，不根据采集次数增加测试样本。</p></details>'


def render_memory_evidence(run):
    evidence = memory_evidence(run)
    if not evidence:
        return ""
    rows = []
    for item in evidence:
        item = item if isinstance(item, dict) else {"evidence": item}
        files = render_evidence_files(item.get("file") or item.get("evidence_files"))
        chat_link = link(item["conversation_url"], "关联会话") if item.get("conversation_url") else ""
        rows.append(f'<p class="evidence">{h(item.get("evidence"))}</p><p class="small">{h(item.get("kind"))} · {files} {chat_link}</p>')
    return '<div class="notice"><p><strong>已观察到跨测试记忆污染。</strong>本批此前问题或会话出现在这次检索证据中，测试会话的独立性受到影响；这不单独证明它决定了具体推荐对象。</p>' + "".join(rows) + '</div>'


def render_corrections(corrections):
    output = []
    for correction in corrections or []:
        c = correction if isinstance(correction, dict) else {"corrected_claim": correction}
        previous = f'<p><span class="muted">此前判断：</span>{h(c["previous_claim"])}</p>' if c.get("previous_claim") else ""
        evidence = render_evidence_files(c.get("evidence_files") or c.get("file"))
        output.append(f'<div><h3>{h(c.get("id") or c.get("title") or "诊断更正")}</h3>{previous}<p><strong>更正：</strong>{h(c.get("corrected_claim") or c.get("notes"))}</p><p class="small">关联记录：{h(c.get("run_ids") or c.get("attempt_ids"))}<br>证据：{evidence}</p></div>')
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
        selected_note = " · 当前选中" if c.get("selected") is True else ""
        scope_note = " · 位于主样本提问" if c.get("attempt_in_main_sample") is True else ""
        rows.append(f'<tr><td>{h(c.get("capture_id"))}<br><span class="note">{h(c.get("attempt_id") or c.get("run_id"))}{selected_note}{scope_note}</span></td><td>{h(display_timestamp(c.get("captured_at") or c.get("capturedAt")))}</td><td>{h(c.get("method"))}<br><span class="note">{h(c.get("capture_kind"))}</span></td><td>{h(c.get("status"))}<br><span class="note">{h(c.get("body_completeness"))}</span></td><td>{files}</td><td>{h(c.get("notes") or c.get("review_notes"))}</td></tr>')
    if not rows and not history["corrections"]:
        return ""
    table = '<div class="table-wrap"><table class="compact"><thead><tr><th>采集 / 原提问</th><th>采集时间</th><th>方法</th><th>结果 / 正文状态</th><th>证据文件</th><th>备注</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>' if rows else ""
    corrections = render_corrections(history["corrections"])
    notes = history["notes"] if isinstance(history["notes"], list) else [history["notes"]]
    notes_html = "".join(f'<p class="note">{h(note)}</p>' for note in notes if note)
    return f'<details class="section detail-section" id="capture-history"><summary>采集失败、恢复与诊断更正 · {len(rows)} 次采集</summary><div class="detail-content"><p class="note">这里保留同一次真实提问的多次采集、失败和更正，不增加实际提问总数。read_thread 的摘要 / 预览不能证明服务器完整正文；异步来源面板的一次空结果也不能证明没有检索来源。</p>{notes_html}{corrections}{table}</div></details>'


def render_run(run, index):
    status = str(run.get("status") or "未记录")
    badge_class = "done" if status == "completed" else "blocked" if status == "blocked" else ""
    meta = [("日期", run.get("date_local")), ("提问时间", display_timestamp(run.get("started_at"))), ("采集时间", display_timestamp(run.get("finished_at"))), ("界面模式", run.get("mode_label")), ("模型标签", run.get("model_label")), ("搜索状态", run.get("search_status")), ("模型证据", run.get("model_evidence")), ("搜索证据", run.get("search_evidence")), ("正文采集方式", capture_method(run)), ("引用链接核对", mapping_label(run.get("citation_mapping_complete")))]
    condition = run_conditions(run)
    meta.insert(5, ("思考强度（已记录界面）", condition["reasoning_effort"] or "未披露"))
    if condition["date_conflict"]:
        meta.append(("日期记录冲突", f'date_local={condition["test_date"]}；提问时间换算 UTC+8={condition["date_from_submit"]}'))
    for field, label in (("slot_id", "计划位置"), ("attempt_id", "真实提问 ID"), ("capture_id", "选中采集 ID")):
        if run.get(field):
            meta.append((label, run[field]))
    if "selected_eligible" in run:
        meta.append(("选中采集是否可用", "是" if run["selected_eligible"] is True else "否" if run["selected_eligible"] is False else "未判定"))
    if run.get("selection_reason"):
        meta.append(("当前选用理由", run["selection_reason"]))
    if "coding_reviewed_for_capture" in run:
        meta.append(("编码是否已核对当前采集", "已核对" if run["coding_reviewed_for_capture"] is True else "待核对"))
    if run.get("attempt_number") is not None:
        meta.append(("该计划位置的提问次数", run.get("attempt_number")))
    if run.get("replacement_for"):
        meta.append(("补测关联原记录", run.get("replacement_for")))
    metadata = "".join(f'<div><dt>{h(label)}</dt><dd>{h(value)}</dd></div>' for label, value in meta)
    links = "".join(x for x in [link(run["conversation_url"], "原始会话") if run.get("conversation_url") else "", local_link(run.get("raw_file"), "原始记录文件"), local_link(run.get("screenshot_file"), "界面截图")] if x)
    notes = f'<p class="note">记录备注：{h(run["notes"])}</p>' if run.get("notes") else ""
    recovery_note = '<p><strong>read_thread 证据边界已更正。</strong>该工具返回摘要 / 预览，不能视为服务器完整存储正文，也不能单凭预览末尾判断原回答被截断。当前正文采用哪次采集，以“正文采集证据与恢复路径”为准；旧证据保留用于追溯。</p>' if uses_read_thread_preview(run) else ""
    citation_note = '<p><strong>内部引用映射不完整。</strong>本条未导出全部引用 URL。尚未映射的内部引用不计作“没有引用”；正文恢复状态与引用映射状态分别记录。</p>' if run.get("citation_mapping_complete") is False else ""
    limitations = f'<div class="notice">{recovery_note}{citation_note}</div>' if recovery_note or citation_note else ""
    personal = personalization_evidence(run)
    personal_note = f'<div class="notice"><p><strong>已观察到个性化混杂。</strong>回答引用了原始问题未提供的个人创作背景：</p><p class="evidence" lang="en">{h(personal)}</p><p class="note">新会话没有消除该影响；这条回答不属于经验证的无个性化条件。</p></div>' if personal else ""
    mapping_badge = '<span class="status blocked">引用映射不完整</span>' if run.get("citation_mapping_complete") is False else ""
    corrections = render_corrections(run.get("diagnostic_corrections") or [])
    correction_section = f'<details><summary>本条诊断更正</summary>{corrections}</details>' if corrections else ""
    return f'''<details id="run-{index}"><summary>{h(run.get("id"))} · {h(run.get("platform"))} · {h(run.get("question_id"))} · 第 {h(run.get("repeat"))} 次 <span class="status {badge_class}">{h(STATUS_LABELS.get(status, status))}</span> {mapping_badge}</summary><div class="run-body"><dl class="run-meta">{metadata}</dl>{limitations}{personal_note}{render_memory_evidence(run)}{render_provenance(run)}{correction_section}<div class="question" lang="en">{h(run.get("prompt"))}</div><div class="links">{links}</div>{notes}<h3>对象观察记录</h3>{render_observations(run)}<details><summary>正文链接与检索来源</summary>{render_sources(run)}</details><details><summary>原始回答 · 当前选用采集正文</summary><pre class="raw-answer" lang="en">{h(run.get("answer_text"))}</pre></details></div></details>'''


def render(runs, findings, attempts=None, capture_history=None):
    attempts = attempts or []
    if "insights" not in findings:
        findings["insights"] = summarize_insights(runs)
    platform_findings, cmr_findings = render_insight_sections(runs, findings)
    sidebar = render_sidebar(runs)
    executive_summary = render_executive_summary(findings)
    complete = findings["completed_runs"]
    dates = sorted({str(r["date_local"]) for r in runs + attempts if r.get("date_local")})
    date_label = " / ".join(dates) or "尚无测试日期"
    condition_summary = summarize_conditions(runs)
    platform_labels = []
    for platform in condition_summary["platforms"]:
        values = platform["values"]
        models = " / ".join(values["model_comparison"]) or "具体模型版本未披露"
        efforts = " / ".join(values["reasoning_effort"]) or "未披露"
        test_dates = " / ".join(values["test_date"]) or "未记录日期"
        modes = " / ".join(values["mode_comparison"]) or "未记录模式"
        platform_labels.append(f'{platform["platform"]}：{models} · 思考强度 {efforts} · {modes} · {test_dates}')
    condition_header = "<br>".join(h(label) for label in platform_labels) or "尚无主记录条件"
    condition_overview = render_condition_overview(condition_summary)
    matrix = "".join(f'<tr><td>{h(run.get("platform"))}</td><td>{h(run.get("question_id"))}</td><td>{h(run.get("repeat"))}</td><td>{h(run.get("date_local"))}</td><td>{h(run.get("mode_label"))}<br><span class="note">{h(run.get("model_label"))}</span></td><td>{h(run.get("search_status"))}</td><td>{h(capture_method(run))}<br><span class="note">{h(mapping_label(run.get("citation_mapping_complete")))}</span></td><td><a href="#run-{i}">{h(STATUS_LABELS.get(run.get("status"), run.get("status")))}</a></td></tr>' for i, run in enumerate(runs, 1))
    if not matrix:
        matrix = '<tr><td colspan="8" class="empty">尚无原始测试记录。</td></tr>'
    overlaps = []
    for group in findings["groups"]:
        overlap = group["repeat_overlap"]
        if overlap is None:
            reason = "无完整可分析正文" if group["completed_runs"] == 0 else "两次重复尚未同时完成或重复编号不唯一"
            a, b, both, union, ratio, entities = ["—"] * 5 + [reason]
        else:
            a, b, both, union = [str(overlap[k]) for k in ("repeat_1_recommendations", "repeat_2_recommendations", "intersection", "union")]
            ratio = "待编码" if overlap["recommendation_coding_incomplete"] else f'{overlap["jaccard"]:.1%}' if overlap["jaccard"] is not None else "不适用"
            entities = "、".join(overlap["shared_entities"]) or "无共同推荐对象"
        comparison_note = render_condition_comparison(overlap.get("condition_comparison")) if overlap else "待两次正文完成"
        overlaps.append(f'<tr><td>{h(group["platform"])} · {h(group["question_id"])}</td><td>{a}</td><td>{b}</td><td>{both}</td><td>{union}</td><td>{ratio}</td><td>{h(entities)}</td><td>{comparison_note}</td></tr>')
    overlap_table = '<div class="table-wrap"><table class="compact"><thead><tr><th>平台 / 问题</th><th>第 1 次</th><th>第 2 次</th><th>交集</th><th>并集</th><th>重合度</th><th>共同推荐对象</th><th>条件说明</th></tr></thead><tbody>' + ("".join(overlaps) or '<tr><td colspan="8" class="empty">暂无可汇总结果。</td></tr>') + '</tbody></table></div>'
    overlap_chart = render_overlap(findings["groups"])
    chart = "".join(render_frequency(group) for group in findings["groups"]) or '<p class="empty">待真实回答完成并编码后生成图表。</p>'
    pending = max(0, 12 - complete)
    records = "".join(render_run(run, index) for index, run in enumerate(runs, 1)) or '<p class="empty">暂无原始回答。</p>'
    history = "".join(render_run(run, f"history-{index}") for index, run in enumerate(attempts, 1))
    history_section = f'<details class="section detail-section" id="attempt-history"><summary>其他真实提问历史 · {len(attempts)} 条</summary><div class="detail-content"><p class="note">这些是真实提交过、但当前未被选入 12 个计划位置的提问；保留其正文、失败与采集证据，不进入主样本的频次和重合度统计。恢复原会话后，主样本的选用记录可以变化，旧记录不覆盖。</p>{history}</div></details>' if attempts else ""
    capture_history_section = render_capture_history(capture_history)
    previews = findings["capture"]["read_thread_preview_run_ids"]
    provenance_ids = findings["capture"]["provenance_run_ids"]
    partial = findings["capture"]["incomplete_citation_mapping_run_ids"]
    personalized = findings["capture"]["observed_personalization"]
    memory = findings["capture"]["observed_memory_evidence"]
    method_parts = ['<p><strong>测试条件分别记录。</strong>以每条真实提问的日期、模型界面标签、思考强度和界面模式比较条件，不把继续工作或恢复日期当作测试日期。任一已记录条件不同时，重复重合度标为“条件不同，仅描述性比较”；字段未披露时也不认定条件完全相同。条件变化不能归因为某一项 GEO 战术的效果。</p>']
    if attempts:
        retest_dates = sorted({str(r["date_local"]) for r in runs if r.get("date_local") and (r.get("replacement_for") or str(r.get("attempt_number") or "1") != "1")})
        retest_date_label = "、".join(retest_dates) or "补测记录未单独标注日期，详见每条开始时间"
        method_parts.append(f'<p><strong>补测政策：</strong>用户已批准额外补测并保留失败记录。主表保留 12 个计划位置当前选用的真实提问；其余 {len(attempts)} 条真实提问单独保存在历史记录。实际提问总数为 {len(runs)} 条主记录 + {len(attempts)} 条历史提问 = {findings["total_prompts"]} 次。同一会话的新采集不增加提问数。</p><p><strong>补测日期：</strong>{h(retest_date_label)}。图表只统计主表中 completed 的样本，历史提问不并入；原会话正文恢复后可以重新选用，但保留此前采集失败和诊断更正。</p>')
    if previews:
        method_parts.append(f'<p><strong>read_thread 证据边界更正：</strong>{h("、".join(map(str, previews)))} 的采集过程用过该工具。它返回摘要 / 预览，不能称为服务器完整存储正文；预览末尾不完整也不能单独证明原回答截断。当前正文依据每条的选中采集证据判断，旧工具输出只作采集历史。</p>')
    if provenance_ids:
        method_parts.append(f'<p><strong>恢复证据追溯：</strong>{h("、".join(map(str, provenance_ids)))} 已记录原状态、原始文件、选中采集 ID / 文件、方式与时间。当前 completed 状态由最终正文审查决定，生成器不会仅因存在恢复文件或来源面板而自动改为完成。</p>')
    if any(source_partitions(r)["retrieval"] for r in runs + attempts):
        method_parts.append('<p><strong>正文链接与检索面板分别记录。</strong>来源面板可能异步加载，单次空快照不能证明没有来源。面板收录的网页和记忆条目不是正文引用；只在正文或可核实内联标记中观察到的链接列为正文链接，Citation 仍按归属证据逐项编码。</p>')
    if partial:
        method_parts.append(f'<p><strong>内部引用映射不完整：</strong>{h("、".join(map(str, partial)))}。报告列出正文明确 URL 与已恢复链接；尚未映射的内部 cite 标记保留在原始记录，无法将来源表当作全部引用清单。Citation 判定需结合每行证据与不确定性，不根据链接缺失直接判“否”。</p>')
    for item in personalized:
        method_parts.append(f'<p><strong>个性化混杂已观察到：</strong>{h(item["run_id"])} 出现原问题未提供的个人创作背景。</p><p class="evidence" lang="en">{h(item["evidence"])}</p><p>因此新会话并未确保无个性化；这会限制跨平台差异的解释。</p>')
    if memory:
        method_parts.append(f'<p><strong>跨测试记忆污染已观察到：</strong>{h("、".join(str(item["run_id"]) for item in memory))} 的检索证据包含本批此前问题或会话。新建会话没有隔离账号记忆；本批结果不能按互相独立的重复试验解释。逐条记忆证据及关联会话保留在对应记录中，不能据此确定某个推荐对象就是由记忆造成的。</p>')
    method_section = '<details class="section detail-section" id="method"><summary>采集方法、补测与限制</summary><div class="detail-content method-notes">' + "".join(method_parts) + '</div></details>' if method_parts else ""
    limits = []
    if condition_summary["cross_day"]:
        limits.append("主记录跨日（" + " / ".join(condition_summary["dates"]) + "）")
    condition_field_labels = {"model_comparison": "模型标签", "reasoning_effort": "思考强度", "mode_comparison": "界面模式"}
    for platform in condition_summary["platforms"]:
        for field in platform["changed_fields"]:
            limits.append(f'{platform["platform"]} 的{condition_field_labels[field]}包含 ' + " / ".join(platform["values"][field]) + "，条件有变化")
    if condition_summary["date_conflict_run_ids"]:
        limits.append("部分日期字段与实际提问时间冲突，需核对")
    if previews or provenance_ids:
        limits.append("ChatGPT 正文采集曾失败，read_thread 仅提供摘要 / 预览")
    if personalized:
        limits.append("已观察到个性化")
    if partial:
        limits.append("部分主记录引用未映射为 URL" if any(r.get("citation_mapping_complete") is False for r in runs) else "历史采集的未映射引用已保留于证据")
    if memory:
        limits.append("已观察到跨测试记忆污染")
    short_limits = "；".join(limits)
    if short_limits:
        short_limits += "。"
    document = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>GEO · 双平台观察实验</title><style>{CSS}</style></head><body><div class="report-shell">{sidebar}<main>
<header><div class="eyebrow">GEO / Platform observation</div><h1>AI 会推荐谁，又引用了谁？</h1><p class="lede">ChatGPT Search 与 Grok 的推荐对象、引用来源和回答差异观察。</p></header>
{executive_summary}
{platform_findings}
<section class="section" id="repeat-stability"><h2>同一问题，两次回答有多相似？</h2><ul class="section-conclusions"><li><strong>本批没有一个平台在所有问题上都更稳定。</strong>实证研究题中 Grok 两轮更接近，另外两题的差距较小。</li><li><strong>这些数值只描述回答的一致程度。</strong>日期、思考强度和账号上下文没有完全控制，不能据此评价平台固有优劣。</li></ul><p class="note section-lead">推荐对象重合度（Jaccard）= 共同推荐数 ÷ 至少出现一次的推荐对象数；该值不衡量准确性或效果。下方同时列出每组的条件差异与未知字段。</p>{overlap_chart}<details><summary>查看交集、并集与共同对象</summary>{overlap_table}</details></section>
{cmr_findings}
<section class="section" id="recommendation-frequency"><h2>主动推荐对象出现频次</h2><ul class="section-conclusions"><li><strong>同一对象的可见性随问题和平台改变。</strong>下方按问题并列展示两平台的推荐次数，用于定位对象在哪类回答中出现。</li></ul><p class="note section-lead">每个对象每条回答最多计 1 次，分母是该组完整回答数；所有对象默认展开。完整 C/M/R 判定和证据保留在原始记录。</p><div class="chart-grid">{chart}</div></section>
<div class="section-kicker" style="margin-top:64px">以下为方法与完整证据</div>
<blockquote class="report-note"><p>全部提问日期：{h(date_label)} · 时区：Asia/Shanghai</p><p>{condition_header}</p><p><strong>小样本观察不能证明 GEO 效果。</strong>{h(short_limits) if short_limits else ''}仅统计已完成主样本，历史尝试不并入。</p></blockquote>
{method_section}
{condition_overview}
<details class="section detail-section" id="run-matrix"><summary>实验记录总表 · {len(runs)} / 12 个计划位置</summary><div class="detail-content"><p class="note">设计为 3 个原始英文问题 × 2 个平台 × 2 次重复。每次开启新会话，仅发送原问题，不追加引导。</p><div class="table-wrap"><table><thead><tr><th>平台</th><th>问题</th><th>重复</th><th>日期</th><th>模式 / 模型</th><th>搜索状态</th><th>正文采集 / 引用映射</th><th>记录状态</th></tr></thead><tbody>{matrix}</tbody></table></div></div></details>
<details class="section detail-section" id="raw-records"><summary>原始回答与逐项观察 · {len(runs)} 条</summary><div class="detail-content"><p class="note">编码由助手逐条阅读回答完成，未经过独立人工双评复核。Citation：该对象自身发布或署名的内容被回答引用。Mention：正文明确提到对象。Recommendation：回答主动建议使用、阅读或关注对象。三项分别判断，来源列表出现不自动等于推荐；边界情况在证据与备注中解释。提问和采集时间按 UTC+8 显示；采集时间不是服务器生成结束时间，原始 ISO 时间保留在数据文件中。统计仅忽略主体名称的空白和大小写，其余按已编码名称归一，不额外自动合并品牌别名。</p>{records}</div></details>
{history_section}
{capture_history_section}
<details class="section detail-section" id="reading-boundaries"><summary>阅读边界</summary><div class="detail-content method-notes"><p>记录反映测试当时账号、地区、界面模式与可见搜索状态下的回答。新会话不等于独立账号，也不保证平台记忆或个性化关闭。只有界面模式标签时，不能据此确认底层模型版本。</p><p>两次重复的样本量很小。推荐和引用的变化可能来自检索结果、生成随机性、索引更新及账号上下文。回答中的实验结论与推荐理由保留为平台原文，不等于本报告已独立复核其真实性。未判定值不计为“否”；引用映射完整性与正文状态分别记录。</p></div></details>
<footer>本报告由已采集原文和逐项观察记录生成，可离线阅读。外部会话、来源和本地证据文件链接需相应访问权限。所有汇总均可由原始记录复算。</footer>
</main></div><script>
function revealRecord(){{let target=document.getElementById(decodeURIComponent(location.hash.slice(1)));if(!target)return;let node=target;while(node){{if(node.tagName==='DETAILS')node.open=true;node=node.parentElement;}}target.scrollIntoView({{block:'start'}});}}
addEventListener('hashchange',revealRecord);if(location.hash)revealRecord();
const tocLinks=[...document.querySelectorAll('.sidebar nav a')];
const tocTargets=tocLinks.map(link=>({{link,target:document.getElementById(link.hash.slice(1))}})).filter(item=>item.target).sort((a,b)=>a.target===b.target?0:(a.target.compareDocumentPosition(b.target)&Node.DOCUMENT_POSITION_FOLLOWING?-1:1));
let tocPending=false;
function updateToc(){{let current=tocTargets[0];for(const item of tocTargets){{if(item.target.getBoundingClientRect().top<=160)current=item;}}for(const item of tocTargets){{if(item===current)item.link.setAttribute('aria-current','location');else item.link.removeAttribute('aria-current');}}tocPending=false;}}
addEventListener('scroll',()=>{{if(!tocPending){{tocPending=true;requestAnimationFrame(updateToc);}}}},{{passive:true}});updateToc();
</script></body></html>'''
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
    args.findings.write_text(json.dumps(findings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "findings": str(args.findings), "completed_runs": findings["completed_runs"], "recorded_runs": len(runs), "historical_attempts": len(attempts), "total_prompts": findings["total_prompts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
