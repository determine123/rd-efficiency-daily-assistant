import subprocess
import tempfile
import unittest
from pathlib import Path

from app.analysis import analyze_git
from app.connectors_git import collect_git_records


class GitMergeDetectionTests(unittest.TestCase):
    def test_custom_titled_merge_is_detected_by_parent_count(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            def git(*args):
                return subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=True,
                    capture_output=True,
                    text=True,
                )

            git("init", "-b", "main")
            git("config", "user.name", "Offline Tester")
            git("config", "user.email", "offline@example.invalid")
            (repo / "base.txt").write_text("base\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-m", "feat: add base")

            git("checkout", "-b", "feature")
            (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-m", "feat: add feature")

            git("checkout", "main")
            (repo / "main.txt").write_text("main\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-m", "fix: update main")
            git("merge", "--no-ff", "feature", "-m", "integrate feature work")

            records = collect_git_records(repo, max_count=1)
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0]["is_merge"])
            self.assertEqual(len(records[0]["parent_ids"]), 2)

            analysis = analyze_git(records, {})
            self.assertEqual(analysis["valid_commits"], [])
            self.assertEqual(analysis["ignored_commits"][0]["commit_id"], records[0]["commit_id"])


if __name__ == "__main__":
    unittest.main()
