from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.analysis import analyze_git, analyze_news
from app.main import generate_report, load_json
from app.validation import validate_report


ROOT = Path(__file__).parents[1]


class ReportAssistantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_json(ROOT / "examples" / "input.json")

    def test_merge_and_irrelevant_news_are_filtered(self):
        git = analyze_git(self.data["git_records"], self.data["team_config"])
        news = analyze_news(self.data["news_records"], self.data["team_config"])
        commit_ids = {item["commit_id"] for item in git["valid_commits"]}
        self.assertNotIn("merge001", commit_ids)
        self.assertEqual(len(news["relevant_news"]), 1)
        self.assertEqual(news["irrelevant_news"][0]["news_id"], "news_002")

    def test_report_contains_sources_and_required_sections(self):
        report, metadata = generate_report(self.data)
        self.assertIn("`a1b2c3d`", report)
        self.assertIn("https://example.com/news/001", report)
        self.assertTrue(metadata["validation"]["passed"])
        self.assertIn("## 四、风险与明日建议", report)

    def test_risk_comes_from_failed_ci(self):
        _, metadata = generate_report(self.data)
        risks = metadata["git_analysis"]["risks"]
        self.assertTrue(any(item["commit_id"] == "d4e5f6g" for item in risks))

    def test_missing_source_fails_validation(self):
        report = """# 研发技术日报 - 2026-08-25
## 一、今日代码进展（Git 状态）
| 模块 | 进展详情 | 提交人 | 来源 | 关联影响 |
|---|---|---|---|---|
| Agent | fake | 张三 | `not-exist` | fake |
## 二、AI 与自动驾驶行业动态
今日无更新。
## 三、团队建议跟进
今日无更新。
## 四、风险与明日建议
### 风险项
暂无明确风险。
### 明日建议
暂无。
"""
        git = analyze_git(self.data["git_records"], self.data["team_config"])
        news = analyze_news(self.data["news_records"], self.data["team_config"])
        result = validate_report(report, self.data, git, news)
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
