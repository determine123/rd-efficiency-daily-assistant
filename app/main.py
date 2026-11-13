from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from .connectors_git import collect_git_records_from_repositories
from .connectors_rss import collect_rss_with_errors
from .workflow import build_workflow


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("输入 JSON 顶层必须是对象")
    return data


def generate_report(input_data: dict) -> tuple[str, dict]:
    """兼容旧 API：通过工作流生成日报。"""
    result = build_workflow().invoke({"input_data": input_data})
    metadata = {
        "git_analysis": result["git_analysis"],
        "news_analysis": result["news_analysis"],
        "evidence_ledger": result["evidence_ledger"],
        "validation": result["validation"],
        "llm_used": result.get("llm_used", False),
        "llm_error": result.get("llm_error", ""),
    }
    return result["report"], metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="生成研发效能技术日报")
    parser.add_argument("--input", required=True, help="输入 JSON 文件")
    parser.add_argument("--output", required=True, help="日报 Markdown 输出路径")
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        help="可选：本地 Git 仓库路径，可重复传入以聚合多个仓库",
    )
    parser.add_argument("--rss", nargs="*", default=[], help="可选：RSS/Atom 地址列表")
    parser.add_argument("--day", help="采集 Git 的日期，格式 YYYY-MM-DD")

    parser.add_argument(
        "--metadata-output",
        help="可选：输出分析中间结果和证据账本 JSON",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    input_data = load_json(input_path)
    git_collection = None
    if args.repo:
        since = until = None
        if args.day:
            date = datetime.fromisoformat(args.day).date()
            since = datetime.combine(date, datetime.min.time()).isoformat()
            until = datetime.combine(date + timedelta(days=1), datetime.min.time()).isoformat()
        input_data["git_records"], git_errors = collect_git_records_from_repositories(
            args.repo,
            since=since,
            until=until,
            max_count=200,
        )
        unique_count = len(
            {
                os.path.normcase(str(Path(repo).expanduser().resolve()))
                for repo in args.repo
            }
        )
        git_collection = {
            "requested": unique_count,
            "succeeded": unique_count - len(git_errors),
            "failed": len(git_errors),
            "errors": git_errors,
        }
    rss_collection = None
    if args.rss:
        input_data["news_records"], rss_errors = collect_rss_with_errors(args.rss)
        rss_collection = {
            "requested": len(args.rss),
            "succeeded": len(args.rss) - len(rss_errors),
            "failed": len(rss_errors),
            "errors": rss_errors,
        }
    report, metadata = generate_report(input_data)
    if git_collection is not None:
        metadata["git_collection"] = git_collection
    if rss_collection is not None:
        metadata["rss_collection"] = rss_collection

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    if args.metadata_output:
        metadata_path = Path(args.metadata_output)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    validation = metadata["validation"]
    print(f"日报已生成：{output_path}")
    print(f"校验结果：{'通过' if validation['passed'] else '失败'}")
    for warning in validation.get("warnings", []):
        print(f"警告：{warning}")
    for error in validation.get("errors", []):
        print(f"错误：{error}")
    if git_collection and git_collection["failed"]:
        print(
            f"Git 采集失败：{git_collection['failed']}/{git_collection['requested']} 个仓库"
        )
        for error in git_collection["errors"]:
            print(f"Git 仓库错误：{error['repo']}：{error['error']}")
    if rss_collection and rss_collection["failed"]:
        print(
            f"RSS 采集失败：{rss_collection['failed']}/{rss_collection['requested']} 个源"
        )
        for error in rss_collection["errors"]:
            print(f"RSS 源错误：{error['url']}：{error['error']}")

    all_git_failed = bool(
        git_collection
        and git_collection["requested"]
        and git_collection["failed"] == git_collection["requested"]
    )
    all_rss_failed = bool(
        rss_collection
        and rss_collection["requested"]
        and rss_collection["failed"] == rss_collection["requested"]
    )
    return 0 if validation["passed"] and not all_git_failed and not all_rss_failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
