from __future__ import annotations

import re


def validate_report(report: str, input_data: dict, git_analysis: dict, news_analysis: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    required_sections = [
        "# 研发技术日报 -",
        "## 一、今日代码进展（Git 状态）",
        "## 二、AI 与自动驾驶行业动态",
        "## 三、团队建议跟进",
        "## 四、风险与明日建议",
    ]
    for section in required_sections:
        if section not in report:
            errors.append(f"缺少章节：{section}")

    source_ids = {
        str(item.get("commit_id"))
        for item in git_analysis.get("valid_commits", [])
        if item.get("commit_id")
    }
    source_ids.update(
        str(item.get("news_id"))
        for item in news_analysis.get("relevant_news", [])
        if item.get("news_id")
    )

    known_news_urls = {
        str(item.get("url"))
        for item in input_data.get("news_records", [])
        if isinstance(item, dict) and item.get("url")
    }
    known_news_sources = {
        str(item.get("source_name"))
        for item in input_data.get("news_records", [])
        if isinstance(item, dict) and item.get("source_name")
    }
    for url in re.findall(r"https?://[^\s)<>]+", report):
        if url.rstrip(".,，。") not in known_news_urls:
            errors.append(f"报告引用了输入中不存在的新闻 URL：{url}")

    # 代码表格中的来源应为已知 commit_id。
    for commit_id in re.findall(r"`([^`]+)`", report):
        if commit_id not in source_ids and commit_id not in {"current_date"}:
            errors.append(f"报告引用了输入中不存在的来源：{commit_id}")

    # 新闻来源必须来自输入数据；报告可以引用 URL，也可以引用来源名称。
    for item in news_analysis.get("relevant_news", []):
        url = str(item.get("url") or "")
        source = str(item.get("source_name") or "")
        if url and url not in known_news_urls:
            errors.append(f"新闻分析引用了输入中不存在的 URL：{url}")
        if source and source not in known_news_sources and source != "来源不足":
            errors.append(f"新闻分析引用了输入中不存在的来源：{source}")

    for item in git_analysis.get("valid_commits", []):
        if item["commit_id"] not in report:
            warnings.append(f"提交未出现在报告中：{item['commit_id']}")

    for item in news_analysis.get("relevant_news", []):
        if item["news_id"] not in report and item.get("url") not in report:
            warnings.append(f"新闻未出现明确 ID 或 URL：{item['news_id']}")

    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
    }
