from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.connectors_git import collect_git_records, collect_today_git_records
from app.connectors_rss import parse_rss
from app.llm_client import OpenAICompatibleLLM, build_summary_prompts
from app.main import generate_report
from app.workflow import build_workflow


class IntegrationAndBoundaryTests(unittest.TestCase):
    def test_empty_input_is_valid_and_explicit(self):
        report, metadata = generate_report({"current_date": "2026-01-01"})
        self.assertTrue(metadata["validation"]["passed"])
        self.assertIn("今日无更新。", report)
        self.assertEqual(metadata["evidence_ledger"], [])

    def test_rss_and_atom_parsing(self):
        rss = b'<rss><channel><title>Feed</title><item><title>Agent update</title><link>https://e.test/a</link><description>AI Agent news</description></item></channel></rss>'
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom</title><entry><title>VLM update</title><link href="https://e.test/b"/><summary>VLM news</summary><updated>2026-01-01T00:00:00Z</updated></entry></feed>'
        self.assertEqual(parse_rss(rss)[0]["url"], "https://e.test/a")
        self.assertEqual(parse_rss(atom)[0]["url"], "https://e.test/b")

    def test_git_collector_and_date_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            for command in (("git", "init"), ("git", "config", "user.name", "Tester"), ("git", "config", "user.email", "tester@example.com")):
                subprocess.run(command, cwd=repo, check=True, capture_output=True)
            (repo / "src.py").write_text("print(1)\n", encoding="utf-8")
            subprocess.run(("git", "add", "."), cwd=repo, check=True, capture_output=True)
            subprocess.run(("git", "commit", "-m", "feat: add source"), cwd=repo, check=True, capture_output=True)
            records = collect_git_records(repo)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["author"]["name"], "Tester")
            self.assertEqual(records[0]["changed_files"][0]["path"], "src.py")
            self.assertEqual(collect_today_git_records(repo, "2000-01-01"), [])

    def test_workflow_fallback(self):
        result = build_workflow().invoke({"input_data": {"current_date": "2026-01-01"}})
        self.assertTrue(result["validation"]["passed"])
        self.assertIn("report", result)

    def test_unknown_news_url_is_rejected(self):
        data = {"current_date": "2026-01-01", "news_records": [{"news_id": "n1", "title": "AI news", "content": "AI", "url": "https://known.test", "source_name": "Known"}]}
        report, _ = generate_report(data)
        tampered = report.replace("https://known.test", "https://forged.test")
        from app.analysis import analyze_git, analyze_news
        from app.validation import validate_report
        result = validate_report(tampered, data, analyze_git([], {}), analyze_news(data["news_records"], {}))
        self.assertFalse(result["passed"])

    def test_prompt_contains_verified_facts_only(self):
        system, user = build_summary_prompts({"git": {"valid_commits": []}})
        self.assertIn("verified_facts", system)
        self.assertIn("evidence_ledger", system)
        self.assertIn("所有 commit_id 和 URL 必须逐字来自输入", system)
        self.assertIn("valid_commits", user)


if __name__ == "__main__":
    unittest.main()
