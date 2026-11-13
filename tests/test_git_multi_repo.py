from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app.analysis import analyze_git, build_evidence_ledger
from app.connectors_git import collect_git_records_from_repositories
from app.workflow import _apply_summaries

ROOT = Path(__file__).parents[1]


class GitMultiRepositoryTests(unittest.TestCase):
    def make_repo(self, root: Path, name: str, message: str, committed_at: str) -> Path:
        repo = root / name
        repo.mkdir()
        subprocess.run(
            ["git", "init"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Multi Repo Tester"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "multi-repo@example.invalid"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "."],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        env = os.environ.copy()
        env.update({"GIT_AUTHOR_DATE": committed_at, "GIT_COMMITTER_DATE": committed_at})
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo,
            check=True,
            capture_output=True,
            env=env,
        )
        return repo

    def test_aggregates_sorts_and_deduplicates_repositories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            older = self.make_repo(
                root,
                "older-repo",
                "fix: older change",
                "2026-11-12T10:00:00+00:00",
            )
            newer = self.make_repo(
                root,
                "newer-repo",
                "feat: newer change",
                "2026-11-13T10:00:00+00:00",
            )

            records, errors = collect_git_records_from_repositories(
                [older, newer, older]
            )

            self.assertEqual(errors, [])
            self.assertEqual(len(records), 2)
            self.assertEqual(
                [record["repository"] for record in records],
                ["newer-repo", "older-repo"],
            )
            self.assertIn("feat: newer change", records[0]["message"])

            limited, errors = collect_git_records_from_repositories(
                [older, newer], max_count=1
            )
            self.assertEqual(errors, [])
            self.assertEqual(len(limited), 1)
            self.assertEqual(limited[0]["repository"], "newer-repo")

    def test_keeps_successful_records_when_another_repository_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = self.make_repo(
                root,
                "valid-repo",
                "feat: collect me",
                "2026-11-13T10:00:00+00:00",
            )
            missing = root / "missing-repo"

            records, errors = collect_git_records_from_repositories([valid, missing])

            self.assertEqual(len(records), 1)
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0]["repo"], str(missing.resolve()))
            self.assertIn("不是 Git 仓库", errors[0]["error"])

    def test_disambiguates_same_short_sha_across_repositories(self):
        records = [
            {
                "commit_id": "abc1234",
                "full_commit_id": "a" * 40,
                "repository": "api-repo",
                "message": "feat: expose API",
                "author": {"name": "Tester"},
                "changed_files": [{"path": "api.py"}],
            },
            {
                "commit_id": "abc1234",
                "full_commit_id": "b" * 40,
                "repository": "worker-repo",
                "message": "fix: retry worker",
                "author": {"name": "Tester"},
                "changed_files": [{"path": "worker.py"}],
            },
        ]

        analysis = analyze_git(records, {})
        ledger = build_evidence_ledger(analysis, {"relevant_news": []})
        self.assertEqual(len({item["evidence_id"] for item in ledger}), 2)
        self.assertEqual(
            [item["source_id"] for item in ledger], ["a" * 40, "b" * 40]
        )

        summarized, _ = _apply_summaries(
            analysis,
            {"relevant_news": []},
            [
                {
                    "repository": "api-repo",
                    "commit_id": "abc1234",
                    "summary": "API 摘要",
                },
                {
                    "repository": "worker-repo",
                    "commit_id": "abc1234",
                    "summary": "Worker 摘要",
                },
            ],
            [],
        )
        self.assertEqual(
            [item["message"] for item in summarized["valid_commits"]],
            ["API 摘要", "Worker 摘要"],
        )

    def test_cli_records_multi_repository_metadata_and_report_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.make_repo(
                root,
                "api-repo",
                "feat: expose report API",
                "2026-11-13T09:00:00+00:00",
            )
            second = self.make_repo(
                root,
                "worker-repo",
                "fix: preserve retry budget",
                "2026-11-13T10:00:00+00:00",
            )
            input_path = root / "input.json"
            output_path = root / "report.md"
            metadata_path = root / "metadata.json"
            input_path.write_text(
                json.dumps({"current_date": "2026-11-13"}),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    "-m",
                    "app.main",
                    "--input",
                    str(input_path),
                    "--repo",
                    str(first),
                    "--repo",
                    str(second),
                    "--output",
                    str(output_path),
                    "--metadata-output",
                    str(metadata_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(
                metadata["git_collection"],
                {
                    "requested": 2,
                    "succeeded": 2,
                    "failed": 0,
                    "errors": [],
                },
            )
            report = output_path.read_text(encoding="utf-8")
            self.assertIn("worker-repo / `", report)
            self.assertIn("api-repo / `", report)
            self.assertIn("feat: expose report API", report)
            self.assertIn("fix: preserve retry budget", report)

    def test_cli_returns_nonzero_when_every_repository_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            output_path = root / "report.md"
            metadata_path = root / "metadata.json"
            input_path.write_text(
                json.dumps({"current_date": "2026-11-13"}),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    "-m",
                    "app.main",
                    "--input",
                    str(input_path),
                    "--repo",
                    str(root / "missing"),
                    "--output",
                    str(output_path),
                    "--metadata-output",
                    str(metadata_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            self.assertEqual(completed.returncode, 1)
            self.assertTrue(output_path.exists())
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["git_collection"]["failed"], 1)
            self.assertIn("Git 采集失败", completed.stdout)


if __name__ == "__main__":
    unittest.main()
