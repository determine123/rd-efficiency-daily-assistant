import subprocess
import tempfile
import unittest
from pathlib import Path

from app.connectors_git import collect_git_records


class GitNumstatTests(unittest.TestCase):
    def test_collects_additions_and_deletions_for_every_changed_file(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            def git(*args):
                subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=True,
                    capture_output=True,
                )

            git("init")
            git("config", "user.name", "Offline Tester")
            git("config", "user.email", "offline@example.invalid")
            (repo / "existing.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-m", "add source")

            (repo / "existing.py").write_text("one\nthree\nfour\nfive\n", encoding="utf-8")
            (repo / "new.py").write_text("alpha\nbeta\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-m", "update source and add module")

            files = collect_git_records(repo, max_count=1)[0]["changed_files"]
            by_path = {item["path"]: item for item in files}

            self.assertEqual(by_path["existing.py"]["additions"], 2)
            self.assertEqual(by_path["existing.py"]["deletions"], 1)
            self.assertEqual(by_path["new.py"]["additions"], 2)
            self.assertEqual(by_path["new.py"]["deletions"], 0)

    def test_marks_binary_files_when_line_counts_are_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            def git(*args):
                subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=True,
                    capture_output=True,
                )

            git("init")
            git("config", "user.name", "Offline Tester")
            git("config", "user.email", "offline@example.invalid")
            (repo / "logo.bin").write_bytes(b"\x00\x01\x02")
            git("add", ".")
            git("commit", "-m", "add binary asset")

            file_info = collect_git_records(repo, max_count=1)[0]["changed_files"][0]
            self.assertTrue(file_info["binary"])
            self.assertEqual(file_info["additions"], 0)
            self.assertEqual(file_info["deletions"], 0)


if __name__ == "__main__":
    unittest.main()
