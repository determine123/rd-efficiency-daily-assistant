from __future__ import annotations

from copy import deepcopy
from typing import Any, TypedDict

from .analysis import analyze_git, analyze_news, build_evidence_ledger
from .llm_client import (
    LLMClient, NoOpLLM, build_git_summary_prompt, build_news_summary_prompt,
    client_from_env,
)
from .report import parse_date, render_report
from .validation import validate_report


def _valid_git(value: Any, facts: dict) -> bool:
    ids = {x["commit_id"] for x in facts.get("valid_commits", [])}
    return isinstance(value, list) and len(value) == len(ids) and all(
        isinstance(x, dict) and x.get("commit_id") in ids and isinstance(x.get("summary"), str)
        for x in value
    )


def _valid_news(value: Any, facts: dict) -> bool:
    known = {x["news_id"]: x.get("url", "") for x in facts.get("relevant_news", [])}
    return isinstance(value, list) and len(value) == len(known) and all(
        isinstance(x, dict) and x.get("news_id") in known and isinstance(x.get("summary"), str)
        and (not known[x["news_id"]] or known[x["news_id"]] in x["summary"])
        for x in value
    )


def _apply_summaries(git: dict, news: dict, git_summaries: list | None, news_summaries: list | None) -> tuple[dict, dict]:
    git = deepcopy(git)
    news = deepcopy(news)
    gmap = {x["commit_id"]: x["summary"] for x in (git_summaries or [])}
    nmap = {x["news_id"]: x["summary"] for x in (news_summaries or [])}
    for item in git["valid_commits"]:
        if item["commit_id"] in gmap:
            item["message"] = gmap[item["commit_id"]]
    for item in news["relevant_news"]:
        if item["news_id"] in nmap:
            item["summary"] = nmap[item["news_id"]]
    return git, news


class ReportState(TypedDict, total=False):
    input_data: dict
    git_analysis: dict
    news_analysis: dict
    evidence_ledger: list
    git_summaries: list
    news_summaries: list
    report: str
    validation: dict
    llm_used: bool
    llm_error: str


def _execute(data: dict, llm: LLMClient | None = None) -> dict:
    if not isinstance(data, dict):
        raise ValueError("input_data 必须是对象")
    config = data.get("team_config") or {}
    git = analyze_git(data.get("git_records") or [], config)
    news = analyze_news(data.get("news_records") or [], config)
    ledger = build_evidence_ledger(git, news)
    git_summaries: list = []
    news_summaries: list = []
    llm_error = ""
    active_llm = llm or client_from_env()
    if not isinstance(active_llm, NoOpLLM):
        try:
            gs, gu = build_git_summary_prompt(git["valid_commits"])
            ns, nu = build_news_summary_prompt(news["relevant_news"])
            git_summaries = active_llm.generate_json(gs, gu)
            news_summaries = active_llm.generate_json(ns, nu)
            if not _valid_git(git_summaries, git) or not _valid_news(news_summaries, news):
                raise ValueError("LLM 摘要未通过 evidence 绑定校验")
        except Exception as exc:
            llm_error = str(exc)
            git_summaries, news_summaries = [], []
    report_git, report_news = _apply_summaries(git, news, git_summaries, news_summaries)
    report = render_report(parse_date(data.get("current_date")), report_git, report_news, config)
    validation = validate_report(report, data, git, news)
    return {
        "input_data": data, "git_analysis": git, "news_analysis": news,
        "evidence_ledger": ledger, "git_summaries": git_summaries,
        "news_summaries": news_summaries, "report": report,
        "validation": validation, "llm_used": bool(git_summaries or news_summaries),
        "llm_error": llm_error,
    }


def build_workflow(llm: LLMClient | None = None):
    """构建生产工作流；无 LangGraph 时提供同等顺序执行降级。"""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return CompatibleWorkflow(llm)

    def run(state: ReportState):
        return _execute(state["input_data"], llm)

    graph = StateGraph(ReportState)
    graph.add_node("run_report_pipeline", run)
    graph.add_edge(START, "run_report_pipeline")
    graph.add_edge("run_report_pipeline", END)
    return graph.compile()


class CompatibleWorkflow:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        return _execute(state["input_data"], self.llm)
