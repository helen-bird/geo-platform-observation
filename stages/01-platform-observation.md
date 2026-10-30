# 阶段一：ChatGPT Search 与 Grok 平台观察

[返回 GEO 学习实验记录](../README.md) · **[阅读可视化报告](https://helen-bird.github.io/geo-platform-observation/)** · [主回答数据](../data/runs.json) · [历史尝试](../data/attempts.json) · [统计结果](../findings.json) · [下载公开数据](../public-data.zip)

本阶段通过重复提问，学习 AI 回答中的推荐对象、引用来源及回答波动。对 ChatGPT Search 与 Grok 提问同样的 3 个英文问题，每题每平台重复 2 次。测试日期为 **2026-10-29 至 2026-10-30**。

## 主要发现

- **创作者题的跨平台推荐差异最大**：合并各平台两轮推荐名单后，共同对象为 2 / 20，重合度 10.0%。
- **本批 ChatGPT 的推荐更常伴随对象自有内容引用**：ChatGPT 为 47 / 48（97.9%），Grok 为 39 / 76（51.3%）。
- **没有一个平台在全部问题上都更稳定**。实证研究题中 Grok 两轮更接近；其余两题没有同样明显的差距。
- **Citation、Mention、Recommendation 可以分开出现**。被引用不一定被点名或推荐，被推荐也不一定引用了对象自有内容。

> 这是小样本的探索性学习记录，编码由助手逐条阅读回答完成，未经过独立人工双评复核。每题每平台只有两次重复，测试跨日、思考强度有变化，并观察到账户上下文影响。没有优化前基线、优化干预或对照组，**不能证明某项 GEO 优化有效，也不能据此判断品牌的 GEO 水平或平台固有优劣**。外部研究和平台原文中的效果主张未在本阶段独立核验。

## 数据、引用与追溯

| 文件 | 内容 |
| --- | --- |
| [index.html](../index.html#stage-1) | 阶段一报告，左侧目录、结论、图表和逐条公开回答 |
| [data/protocol.json](../data/protocol.json) | 三个原始英文问题、实验设计和编码定义 |
| [data/runs.json](../data/runs.json) | 12 份完整主回答及 142 条主体×回答观察 |
| [data/attempts.json](../data/attempts.json) | 10 次未纳入主统计的历史提问，保留失败与恢复状态 |
| [data/capture-history.json](../data/capture-history.json) | 37 次采集及诊断更正，采集次数不等于提问次数 |
| [data/records/](../data/records/) | 22 次真实提交的独立脱敏记录，与主表及历史表对应 |
| [data/captures/](../data/captures/) | 每次采集的公开摘要 |
| [findings.json](../findings.json) | 由公开观察数据计算的汇总与 C/M/R 分布 |
| [scripts/](../scripts/) | 统计、页面生成与公开文件核验代码 |

> **C**：对象自己发布或署名的内容被引用。**M**：正文明确点名对象。**R**：主动建议使用、阅读或关注对象。三项分别判断，不是严格漏斗。统计只覆盖已编码的主要推荐与实质讨论对象，没有穷尽所有来源出版者；Grok 的“仅 C＝0”不能解释为它不会只引用而不点名。

报告中的每项观察保留 `evidence` 原文片段、C/M/R 判定、`source_urls`，每条来源保留具体 URL 和域名。HTML 使用仓库内相对路径链接到公开记录，外部研究链接保留其文章或论文标识。GitHub 的文件历史可用于追踪后续更正；需要固定版本引用时，可在文件页面选择 **Copy permalink**。

## 公开范围

**这里的“原始回答”是用于复核的脱敏副本，不是未修改的私人采集档案。** 原始英文问题、研究对象、引用归属和统计不变；与实验无关的个人上下文片段已省略，并保留编辑标记，公开 URL 去掉跟踪参数。

私人会话及分享链接、本机路径、账号信息、原始截图、完整 HTML 采集和内部诊断档案不包含在本仓库中。本地完整原始档案继续保留。公开版仍保留 12 份主回答、22 次真实提交、10 次历史尝试和 37 次采集摘要。[完整公开范围说明](../data/publication-notes.json)

## 本地复算与阅读

在仓库根目录运行以下命令，仅需 Python 3 标准库，无需账号或 API：

```sh
python3 scripts/rebuild.py
python3 scripts/check_publication.py
python3 -m http.server 8000
```

打开[本地报告](http://localhost:8000/)阅读完整内容。GitHub 仓库页面可阅读本阶段文档、JSON 数据和代码；GitHub Pages 使用同一份 [index.html](../index.html) 展示排版与图表。
