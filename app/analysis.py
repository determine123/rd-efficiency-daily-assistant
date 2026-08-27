from __future__ import annotations

import hashlib
import re
from collections import Counter
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any

DEFAULT_TOPICS = [
    "AI", "LLM", "VLM", "VLA", "Agent", "自动驾驶", "机器人", "世界模型",
    "数据处理", "开发工具", "Transformer", "大模型",
]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _author_name(commit: dict) -> str:
    author = commit.get("author", "")
    if isinstance(author, dict):
        return _text(author.get("name")) or "未知"
    return _text(author) or "未知"


def _message(commit: dict) -> str:
    return _text(commit.get("message"))


def _is_merge(commit: dict, patterns: list[str]) -> bool:
    if commit.get("is_merge") is True:
        return True
    message = _message(commit)
    return any(re.search(pattern, message, re.IGNORECASE) for pattern in patterns)


def classify_commit(commit: dict, config: dict) -> str:
    message = _message(commit).lower()
    files = [
        _text(item.get("path") if isinstance(item, dict) else item).lower()
        for item in commit.get("changed_files", [])
    ]

    if _is_merge(commit, config.get("ignored_commit_patterns", [])):
        return "ignored"
    if re.search(r"(^|\b)(feat|feature|add|implement|support)(\b|:)", message):
        return "feature"
    if re.search(r"(^|\b)(fix|bug|repair|patch|hotfix)(\b|:)", message):
        return "fix"
    if any("test" in path or path.startswith("tests/") or "spec" in path for path in files):
        return "test"
    if any("readme" in path or path.startswith("docs/") or path.endswith(".md") for path in files):
        return "docs"
    if re.search(r"refactor|cleanup|重构|优化结构", message):
        return "refactor"
    return "other"


def resolve_module(path: str, module_map: dict[str, str]) -> str:
    path = _text(path).replace("\\", "/")
    for prefix, module in sorted(module_map.items(), key=lambda item: len(item[0]), reverse=True):
        if path.startswith(prefix.replace("\\", "/")):
            return module
    return "根据当前路径无法判断"


def _risk_evidence(commit: dict) -> list[str]:
    values = [_message(commit), _text(commit.get("ci_status")), _text(commit.get("ci_message"))]
    values.extend(_text(item.get("path")) for item in commit.get("changed_files", []) if isinstance(item, dict))
    text = " ".join(values)
    patterns = [
        r"TODO", r"FIXME", r"unresolved", r"blocked", r"失败", r"failed",
        r"error", r"warning", r"not fixed", r"未解决", r"阻塞",
    ]
    return [value for value in patterns if re.search(value, text, re.IGNORECASE)]


def analyze_git(records: list[dict], config: dict) -> dict:
    module_map = config.get("module_map", {})
    valid = []
    ignored = []
    module_counter = Counter()
    risks = []

    for commit in records:
        category = classify_commit(commit, config)
        cid = _text(commit.get("commit_id"))
        if category == "ignored" or not cid:
            ignored.append({"commit_id": cid or "缺失", "reason": "Merge commit 或缺少 commit_id"})
            continue

        paths = []
        modules = []
        for item in commit.get("changed_files", []):
            path = _text(item.get("path") if isinstance(item, dict) else item)
            if path:
                paths.append(path)
                module = resolve_module(path, module_map)
                modules.append(module)
                module_counter[module] += 1

        unique_modules = list(dict.fromkeys(modules)) or ["根据当前数据无法判断"]
        evidence = _risk_evidence(commit)
        item = {
            "commit_id": cid,
            "category": category,
            "module": "、".join(unique_modules),
            "author": _author_name(commit),
            "message": _message(commit),
            "changed_files": paths,
            "ci_status": _text(commit.get("ci_status")),
            "risk_evidence": evidence,
        }
        valid.append(item)
        if evidence:
            risks.append({
                "commit_id": cid,
                "evidence": evidence,
                "detail": _text(commit.get("ci_message")) or _message(commit),
            })

    hotspots = [
        {"module": module, "change_count": count}
        for module, count in module_counter.most_common()
    ]
    return {
        "valid_commits": valid,
        "ignored_commits": ignored,
        "hotspots": hotspots,
        "risks": risks,
    }


def _news_hash(news: dict) -> str:
    raw = _text(news.get("raw_hash"))
    if raw:
        return raw
    content = _text(news.get("content"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest() if content else ""


def _news_relevant(news: dict, topics: list[str]) -> bool:
    text = " ".join([
        _text(news.get("title")),
        _text(news.get("content")),
        " ".join(_text(tag) for tag in news.get("tags", [])),
    ]).lower()
    return any(topic.lower() in text for topic in topics)


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _short_summary(content: str, title: str) -> str:
    content = re.sub(r"\s+", " ", _text(content))
    if not content:
        return title or "根据当前数据无法判断"
    # V0.1 只做保守截断，不由规则层添加新事实。
    return content[:120] + ("……" if len(content) > 120 else "")


def analyze_news(records: list[dict], config: dict) -> dict:
    topics = config.get("relevant_topics", DEFAULT_TOPICS)
    relevant = []
    irrelevant = []
    duplicate_groups: list[list[str]] = []
    seen_hashes: dict[str, str] = {}

    for news in records:
        nid = _text(news.get("news_id"))
        if not nid:
            irrelevant.append({"news_id": "缺失", "reason": "缺少 news_id"})
            continue
        if not _news_relevant(news, topics):
            irrelevant.append({"news_id": nid, "title": _text(news.get("title")), "reason": "无关主题"})
            continue

        raw_hash = _news_hash(news)
        duplicate_of = None
        if raw_hash and raw_hash in seen_hashes:
            duplicate_of = seen_hashes[raw_hash]
        else:
            for old in relevant:
                if _similar(_text(news.get("title")), old["title"]) >= 0.88:
                    duplicate_of = old["news_id"]
                    break

        item = {
            "news_id": nid,
            "title": _text(news.get("title")),
            "summary": _short_summary(news.get("content"), news.get("title")),
            "topic": next((topic for topic in topics if topic.lower() in (" ".join([
                _text(news.get("title")), _text(news.get("content")), " ".join(news.get("tags", []))
            ])).lower()), "其他相关主题"),
            "source_name": _text(news.get("source_name")) or "来源不足",
            "url": _text(news.get("url")),
            "published_at": _text(news.get("published_at")),
            "duplicate_of": duplicate_of,
        }

        if duplicate_of:
            for group in duplicate_groups:
                if duplicate_of in group:
                    group.append(nid)
                    break
            else:
                duplicate_groups.append([duplicate_of, nid])
        else:
            relevant.append(item)
            if raw_hash:
                seen_hashes[raw_hash] = nid

    return {
        "relevant_news": relevant[: int(config.get("max_news_items", 5))],
        "irrelevant_news": irrelevant,
        "duplicate_groups": duplicate_groups,
    }


def build_evidence_ledger(git_analysis: dict, news_analysis: dict) -> list[dict]:
    ledger = []
    for item in git_analysis.get("valid_commits", []):
        ledger.append({
            "evidence_id": f"git:{item['commit_id']}",
            "source_type": "git",
            "source_id": item["commit_id"],
            "verified": True,
            "fields": item,
        })
    for item in news_analysis.get("relevant_news", []):
        ledger.append({
            "evidence_id": f"news:{item['news_id']}",
            "source_type": "news",
            "source_id": item["news_id"],
            "verified": bool(item.get("url") or item.get("source_name")),
            "fields": item,
        })
    return ledger
