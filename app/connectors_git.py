from __future__ import annotations

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


def _parse_numstat(raw: str) -> dict[str, int]:
    additions = deletions = 0
    if raw and raw != "-":
        try:
            additions = int(raw)
        except ValueError:
            pass
    return {"additions": additions, "deletions": deletions}


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

    pretty = "%x1e%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s"
    args = ["log", f"--max-count={max_count}", f"--pretty=format:{pretty}", "--numstat", "--name-status"]
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
        if len(header) < 6:
            continue
        full_id, short_id, author, email, committed_at, message = header[:6]
        current = {
            "commit_id": short_id,
            "full_commit_id": full_id,
            "author": {"name": author, "email": email},
            "committed_at": committed_at,
            "message": message,
            "changed_files": [],
            "is_merge": False,
            "raw_source": f"git://{repo.as_posix()}/commit/{full_id}",
        }
        pending_numstat = None
        for line in block_lines[1:]:
            if current is None:
                continue
            text = line.strip()
            if not text:
                continue
            parts = text.split("\t")
            if len(parts) >= 2 and parts[0] in {"A", "M", "D", "R", "C", "T", "U"}:
                status = parts[0]
                path = "\t".join(parts[1:])
                info = {"path": path, "status": status}
                if pending_numstat and pending_numstat.get("path") == path:
                    info.update({k: v for k, v in pending_numstat.items() if k != "path"})
                    pending_numstat = None
                current["changed_files"].append(info)
                continue
            if len(parts) >= 3 and (parts[0].isdigit() or parts[0] == "-") and (parts[1].isdigit() or parts[1] == "-"):
                pending_numstat = _parse_numstat(parts[0])
                pending_numstat["deletions"] = _parse_numstat(parts[1])["deletions"]
                pending_numstat["path"] = "\t".join(parts[2:])
                continue
        records.append(current)

    for record in records:
        record["is_merge"] = len(record["message"].lower().split()) > 0 and record["message"].lower().startswith("merge ")
    return records


def collect_today_git_records(repo: str | Path, day: str | None = None, max_count: int = 100) -> list[dict[str, Any]]:
    date = datetime.fromisoformat(day).date() if day else datetime.now().date()
    start = datetime.combine(date, datetime.min.time()).isoformat()
    end = datetime.combine(date + timedelta(days=1), datetime.min.time()).isoformat()
    return collect_git_records(repo, since=start, until=end, max_count=max_count)
