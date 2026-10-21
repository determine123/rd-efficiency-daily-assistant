import subprocess
import tempfile
import unittest
from pathlib import Path

from app.connectors_git import collect_git_records


class GitRenameTests(unittest.TestCase):
    def test_exact_rename_preserves_destination_and_original_path(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args):
                subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
            git("init")
            git("config", "user.name", "Offline Tester")
            git("config", "user.email", "offline@example.invalid")
            (repo / "before.py").write_text("print('unchanged')\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-m", "add source")
            git("mv", "before.py", "after.py")
            git("commit", "-m", "rename source")
            files = collect_git_records(repo, max_count=1)[0]["changed_files"]
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["status"], "R")
            self.assertEqual(files[0]["path"], "after.py")
            self.assertEqual(files[0]["previous_path"], "before.py")
