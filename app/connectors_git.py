from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def _run_git(repo: str | Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Git 命令执行失败")
    return result.stdout


def _parse_raw_file(line: str) -> dict[str, Any] | None:
    """解析 `--raw` 输出的文件状态行。"""
    parts = line.strip().split("\t")
    metadata = parts[0][1:].split() if parts and parts[0].startswith(":") else []
    if len(metadata) < 5:
        return None
    status = metadata[4][0]
    if status not in {"A", "M", "D", "R", "C", "T", "U"}:
        return None

    if status in {"R", "C"} and len(parts) >= 3:
        return {"status": status, "previous_path": parts[1], "path": parts[2]}
    if len(parts) >= 2:
        return {"status": status, "path": "\t".join(parts[1:])}
    return None


def _parse_numstat(line: str) -> dict[str, Any] | None:
    """解析 `--numstat` 输出行；二进制文件用 binary 标记未知行数。"""
    parts = line.strip().split("\t", 2)
    if len(parts) != 3:
        return None
    additions, deletions, path = parts
    if (additions != "-" and not additions.isdigit()) or (deletions != "-" and not deletions.isdigit()):
        return None
    return {
        "additions": int(additions) if additions.isdigit() else 0,
        "deletions": int(deletions) if deletions.isdigit() else 0,
        "binary": additions == "-" or deletions == "-",
        "path": path,
    }


def collect_git_records(
    repo: str | Path,
    since: str | None = None,
    until: str | None = None,
    max_count: int = 100,
) -> list[dict[str, Any]]:
    """从本地 Git 仓库采集结构化提交记录。since/until 使用 Git 可识别的日期格式。"""
    repo = Path(repo).resolve()
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        raise ValueError(f"不是 Git 仓库：{repo}")

    pretty = "%x1e%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%P%x1f%s"
    args = ["log", f"--max-count={max_count}", f"--pretty=format:{pretty}", "--raw", "--numstat"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")

    raw = _run_git(repo, *args)
    records: list[dict[str, Any]] = []
    # 每条记录由 pretty header 开始，后续为 numstat/name-status 行。
    # Git 的 pretty header 以 record separator 结束；先按它拆分，避免 splitlines 将控制字符误判为换行。
    for record_block in raw.split("\x1e"):
        if not record_block.strip():
            continue
        block_lines = record_block.splitlines()
        header_line = next((line for line in block_lines if "\x1f" in line), "")
        if not header_line:
            continue
        header = header_line.split("\x1f")
        if len(header) < 7:
            continue
        full_id, short_id, author, email, committed_at, parents, message = header[:7]
        parent_ids = parents.split()
        current = {
            "commit_id": short_id,
            "full_commit_id": full_id,
            "repository": repo.name,
            "author": {"name": author, "email": email},
            "committed_at": committed_at,
            "message": message,
            "changed_files": [],
            "is_merge": len(parent_ids) > 1,
            "parent_ids": parent_ids,
            "raw_source": f"git://{repo.as_posix()}/commit/{full_id}",
        }
        raw_files: list[dict[str, Any]] = []
        numstats: list[dict[str, Any]] = []
        for line in block_lines[1:]:
            text = line.strip()
            if not text:
                continue
            file_info = _parse_raw_file(text)
            if file_info:
                raw_files.append(file_info)
                continue
            numstat = _parse_numstat(text)
            if numstat:
                numstats.append(numstat)
        for index, file_info in enumerate(raw_files):
            if index < len(numstats):
                numstat = numstats[index]
                file_info["additions"] = numstat["additions"]
                file_info["deletions"] = numstat["deletions"]
                if numstat["binary"]:
                    file_info["binary"] = True
            current["changed_files"].append(file_info)
        records.append(current)

    return records


def collect_git_records_from_repositories(
    repositories: list[str | Path] | tuple[str | Path, ...],
    since: str | None = None,
    until: str | None = None,
    max_count: int = 100,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """聚合多个本地仓库的提交，并保留逐仓库采集错误。

    单个仓库失败不会丢弃其他仓库已经采集到的记录。重复传入同一仓库只采集
    一次，最终结果按提交时间倒序排列并统一限制为 ``max_count`` 条。
    """
    unique_repositories: list[Path] = []
    seen: set[str] = set()
    for repository in repositories:
        resolved = Path(repository).expanduser().resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            unique_repositories.append(resolved)

    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for repository in unique_repositories:
        try:
            records.extend(
                collect_git_records(
                    repository,
                    since=since,
                    until=until,
                    max_count=max_count,
                )
            )
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append({"repo": str(repository), "error": str(exc)})

    def timestamp(record: dict[str, Any]) -> float:
        try:
            return datetime.fromisoformat(str(record["committed_at"])).timestamp()
        except (KeyError, TypeError, ValueError):
            return float("-inf")

    records.sort(key=timestamp, reverse=True)
    return records[:max_count], errors


def collect_today_git_records(repo: str | Path, day: str | None = None, max_count: int = 100) -> list[dict[str, Any]]:
    date = datetime.fromisoformat(day).date() if day else datetime.now().date()
    start = datetime.combine(date, datetime.min.time()).isoformat()
    end = datetime.combine(date + timedelta(days=1), datetime.min.time()).isoformat()
    return collect_git_records(repo, since=start, until=end, max_count=max_count)
