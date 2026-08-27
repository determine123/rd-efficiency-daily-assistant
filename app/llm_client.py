from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class LLMClient(Protocol):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        ...

    def generate_json(self, system_prompt: str, user_prompt: str, retries: int = 2) -> Any:
        ...


@dataclass
class NoOpLLM:
    """默认客户端：不调用网络，交给规则渲染器生成安全日报。"""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("未配置 LLM。请使用规则版日报，或配置 LLM_BASE_URL/LLM_API_KEY。")

    def generate_json(self, system_prompt: str, user_prompt: str, retries: int = 2) -> Any:
        raise RuntimeError("未配置 LLM")


@dataclass
class OpenAICompatibleLLM:
    """兼容 OpenAI Chat Completions 的接口。生产环境应通过环境变量注入配置。"""

    base_url: str
    api_key: str
    model: str
    timeout: int = 60
    retry_backoff: float = 0.5

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail[:500]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"LLM 网络请求失败：{exc}") from exc

        try:
            content = result["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            return content
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM 返回格式不符合 Chat Completions 规范") from exc

    def generate_json(self, system_prompt: str, user_prompt: str, retries: int = 2) -> Any:
        last_error: Exception | None = None
        for attempt in range(max(0, retries) + 1):
            try:
                return parse_json_response(self.generate(system_prompt, user_prompt))
            except (json.JSONDecodeError, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(self.retry_backoff * (2**attempt))
        raise RuntimeError(f"LLM JSON 输出失败：{last_error}") from last_error


def parse_json_response(text: str) -> Any:
    """允许模型返回裸 JSON 或 ```json 代码块，但拒绝 JSON 外的解释文本。"""
    value = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.I | re.S)
    if fenced:
        value = fenced.group(1).strip()
    result = json.loads(value)
    if not isinstance(result, (list, dict)):
        raise ValueError("模型 JSON 顶层必须是数组或对象")
    return result


def client_from_env() -> LLMClient:
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    if base_url and api_key and model:
        return OpenAICompatibleLLM(
            base_url, api_key, model,
            timeout=int(os.getenv("LLM_TIMEOUT", "60")),
            retry_backoff=float(os.getenv("LLM_RETRY_BACKOFF", "0.5")),
        )
    return NoOpLLM()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def build_git_summary_prompt(git_facts: list[dict]) -> tuple[str, str]:
    system = """你是 Git 研发进展摘要器。只能使用用户提供的已校验 git_facts。逐条处理，不合并提交，不添加未出现的功能、性能、影响、风险或计划。每个输出对象的 commit_id 必须原样复制。docs 必须以[文档]开头，test 必须以[测试]开头。只返回 JSON 数组，不要解释。"""
    user = f"""任务：为每条 Git 提交生成一句简洁、客观的中文摘要。\n\n已校验输入事实：\n{_json(git_facts)}\n\n输出格式：\n[{{\"commit_id\": \"原始 commit_id\", \"summary\": \"摘要（commit_id）\"}}]"""
    return system, user


def build_news_summary_prompt(news_facts: list[dict]) -> tuple[str, str]:
    system = """你是 AI/自动驾驶新闻摘要器。只能使用用户提供的已校验新闻事实和正文。不得推断趋势、影响、战略或性能。每个 news_id、url 必须原样复制。只返回 JSON 数组，不要评论。"""
    user = f"""任务：为每条新闻生成一句客观摘要，并在摘要末尾附(来源: 原始URL)。\n\n已校验输入事实：\n{_json(news_facts)}\n\n输出格式：\n[{{\"news_id\": \"原始 news_id\", \"summary\": \"摘要 (来源: 原始URL)\"}}]"""
    return system, user


def build_final_report_prompt(
    current_date: str,
    git_summaries: list[dict],
    news_summaries: list[dict],
    evidence_ledger: list[dict],
    team_config: dict,
    historical_report_style: Any = None,
) -> tuple[str, str]:
    system = """你是研发技术日报生成器。只能基于 verified_facts 和 evidence_ledger 输出日报。所有 commit_id 和 URL 必须逐字来自输入。没有证据的影响写“根据当前数据无法判断”，没有证据的风险写“暂无明确风险”。建议必须标注为建议，不能写成既定计划。历史内容只能参考结构和措辞，不能引用其中事实。只输出纯 Markdown。"""
    user = f"""请严格生成日期为 {current_date} 的日报。\n\n今日代码摘要：\n{_json(git_summaries)}\n\n行业新闻摘要：\n{_json(news_summaries)}\n\n证据账本（不可修改）：\n{_json(evidence_ledger)}\n\n团队配置：\n{_json(team_config)}\n\n历史日报风格（仅结构参考）：\n{_json(historical_report_style or [])}\n\n固定章节：\n# 研发技术日报 - {current_date}\n## 一、今日代码进展（Git 状态）\n## 二、AI 与自动驾驶行业动态\n## 三、团队建议跟进\n## 四、风险与明日建议\n"""
    return system, user


def build_summary_prompts(facts: dict, historical_reports: list[dict] | None = None) -> tuple[str, str]:
    """兼容旧调用；新代码应使用三套独立 Prompt。"""
    return build_final_report_prompt("未指定日期", facts.get("git", []), facts.get("news", []), facts.get("evidence_ledger", []), {}, historical_reports)
