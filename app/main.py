from __future__ import annotations

import argparse
import json
from pathlib import Path

from .connectors_git import collect_git_records
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
    parser.add_argument("--repo", help="可选：本地 Git 仓库路径，自动采集今日提交")
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
    if args.repo:
        if args.day:
            from .connectors_git import collect_today_git_records
            input_data["git_records"] = collect_today_git_records(args.repo, args.day, max_count=200)
        else:
            input_data["git_records"] = collect_git_records(args.repo, max_count=200)
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
    if rss_collection and rss_collection["failed"]:
        print(
            f"RSS 采集失败：{rss_collection['failed']}/{rss_collection['requested']} 个源"
        )
        for error in rss_collection["errors"]:
            print(f"RSS 源错误：{error['url']}：{error['error']}")

    all_rss_failed = bool(
        rss_collection
        and rss_collection["requested"]
        and rss_collection["failed"] == rss_collection["requested"]
    )
    return 0 if validation["passed"] and not all_rss_failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
