#!/usr/bin/env python3
"""Reproduce the public report from the versioned public observations, offline."""
import json
from pathlib import Path
import zipfile
import build_report

ROOT = Path(__file__).resolve().parents[1]
SITE_URL = 'https://helen-bird.github.io/geo-platform-observation/'

def main():
    read = lambda path: json.loads((ROOT / path).read_text())
    runs, attempts, history = read('data/runs.json'), read('data/attempts.json'), read('data/capture-history.json')
    assert (len(runs), len(attempts), len(history['captures'])) == (12, 10, 37)
    for record in runs + attempts:
        assert read(record['raw_file']) == record, 'Individual record differs from aggregate data'
    findings = build_report.aggregate(runs, attempts, history)
    findings['insights'] = build_report.summarize_insights(runs)
    (ROOT / 'findings.json').write_text(json.dumps(findings, ensure_ascii=False, indent=2) + '\n')
    html = build_report.render(runs, findings, attempts, history)
    notice = '<blockquote class="report-note"><strong>阶段一 · 公开记录</strong><p>个人上下文中与实验无关的片段已省略，并保留编辑标记；公开来源链接已去除跟踪参数。推荐对象、引用归属与统计保持一致。私人会话、截图及完整本地档案不公开。</p><p><a href="public-data.zip">下载阶段一公开数据</a> · <a href="data/publication-notes.json">公开范围说明</a> · <a href="https://github.com/helen-bird/geo-platform-observation">学习记录与阶段索引</a></p></blockquote>'
    html = html.replace('</header>', '</header>' + notice, 1)
    html = html.replace('原始记录文件', '公开记录副本').replace('原始回答 · 当前选用采集正文', '回答正文 · 公开脱敏副本')
    html = html.replace('外部会话、来源和本地证据文件链接需相应访问权限。', '外部研究来源由各站点提供；本页不包含私有会话、原始截图或本地证据档案。')
    html = html.replace('<title>GEO · 双平台观察实验</title>', '<title>GEO 学习实验记录｜阶段一：ChatGPT 与 Grok 对比</title><meta name="description" content="持续更新的GEO学习实验记录。当前阶段一通过12份完整回答，观察ChatGPT Search与Grok的推荐对象、引用来源及C/M/R分布。不能据此判断GEO优化效果。">')
    html = html.replace('GEO <span>观察实验</span>', 'GEO <span>学习实验记录</span>')
    html = html.replace('原始问题未提供的个人创作背景', '原始问题未提供的个人上下文').replace('原问题未提供的个人创作背景', '原问题未提供的个人上下文')
    html = html.replace('</head>', f'<link rel="canonical" href="{SITE_URL}"><meta property="og:type" content="website"><meta property="og:title" content="GEO 学习实验记录｜阶段一"><meta property="og:description" content="持续积累GEO学习与实验记录；当前展示ChatGPT与Grok双平台对比的阶段一成果。"><meta property="og:url" content="{SITE_URL}"></head>')
    (ROOT / 'index.html').write_text(html)
    (ROOT / '404.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>页面不存在</title><h1>页面不存在</h1><p><a href="/geo-platform-observation/">返回GEO实验报告</a></p></html>')
    with zipfile.ZipFile(ROOT / 'public-data.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((ROOT / 'data').rglob('*.json')):
            archive.write(path, path.relative_to(ROOT))
        archive.write(ROOT / 'findings.json', 'findings.json')
    print(json.dumps({'main_answers': len(runs), 'historical_attempts': len(attempts), 'captures': len(history['captures']), 'observations': findings['insights']['observation_count']}))

if __name__ == '__main__':
    main()
