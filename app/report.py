from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def _safe(value: Any) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ").strip()
    return text or "根据当前数据无法判断"


def _category_label(category: str) -> str:
    return {
        "feature": "功能开发",
        "fix": "Bug 修复",
        "test": "测试",
        "docs": "文档",
        "refactor": "重构",
        "other": "其他",
    }.get(category, category)


def render_report(
    current_date: str,
    git_analysis: dict,
    news_analysis: dict,
    config: dict,
) -> str:
    lines = [
        f"# 研发技术日报 - {current_date}",
        "",
        "## 一、今日代码进展（Git 状态）",
        "",
    ]

    commits = git_analysis.get("valid_commits", [])
    if not commits:
        lines.append("今日无更新。")
    else:
        lines.extend([
            "| 模块 | 进展详情 | 提交人 | 来源 | 关联影响 |",
            "|---|---|---|---|---|",
        ])
        for item in commits:
            detail = f"[{_category_label(item['category'])}] {_safe(item['message'])}"
            impact = "根据当前数据无法判断"
            lines.append(
                f"| {_safe(item['module'])} | {_safe(detail)} | {_safe(item['author'])} | "
                f"`{_safe(item['commit_id'])}` | {_safe(impact)} |"
            )

    lines.extend(["", "**未解决问题/风险：**"])
    risks = git_analysis.get("risks", [])
    if risks:
        for risk in risks:
            lines.append(
                f"- 来源 `{_safe(risk['commit_id'])}`：{_safe(risk['detail'])}。"
            )
    else:
        lines.append("- 暂无明确风险。")

    lines.extend(["", "## 二、AI 与自动驾驶行业动态", ""])
    news = news_analysis.get("relevant_news", [])
    if not news:
        lines.append("今日无更新。")
    else:
        for index, item in enumerate(news, 1):
            source = _safe(item.get("url") or item.get("source_name"))
            lines.append(
                f"{index}. **【{_safe(item['topic'])}】{_safe(item['title'])}**："
                f"{_safe(item['summary'])}  "
            )
            lines.append(f"   来源：{source}")

    lines.extend(["", "## 三、团队建议跟进", ""])
    if news:
        item = news[0]
        lines.extend([
            f"- 建议关注：{_safe(item['title'])}。",
            f"- 依据：该新闻被分类为 {_safe(item['topic'])}，且来源为 {_safe(item.get('source_name'))}。",
            "- 说明：该项为基于今日数据的建议，不代表已确定计划。",
        ])
    else:
        lines.append("今日无更新。")

    lines.extend(["", "## 四、风险与明日建议", "", "### 风险项", ""])
    if risks:
        for risk in risks:
            lines.append(f"- { _safe(risk['detail']) }（来源：`{_safe(risk['commit_id'])}`）")
    else:
        lines.append("暂无明确风险。")

    lines.extend(["", "### 明日建议", ""])
    if risks:
        lines.append(
            f"- 建议优先确认来源 `{_safe(risks[0]['commit_id'])}` 涉及的问题，依据：原始 Git 数据中存在明确风险证据。"
        )
    elif commits:
        lines.append(
            f"- 建议优先复核 {_safe(commits[0]['module'])} 的提交内容，依据：今日存在相关代码提交。"
        )
    else:
        lines.append("- 今日没有足够数据提出具体明日建议。")

    return "\n".join(lines).rstrip() + "\n"


def parse_date(value: str | None) -> str:
    if value:
        return value
    return datetime.now().strftime("%Y-%m-%d")
