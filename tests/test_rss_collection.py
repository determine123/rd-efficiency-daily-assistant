import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.connectors_rss import collect_rss, collect_rss_with_errors
from app.main import main


class RSSCollectionTests(unittest.TestCase):
    def _run_cli(self, urls, collection):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            output_path = root / "report.md"
            metadata_path = root / "metadata.json"
            input_path.write_text('{"current_date": "2026-11-13"}', encoding="utf-8")
            argv = [
                "app.main",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--metadata-output",
                str(metadata_path),
                "--rss",
                *urls,
            ]

            stdout = io.StringIO()
            with patch("app.main.collect_rss_with_errors", return_value=collection), patch(
                "sys.argv", argv
            ), redirect_stdout(stdout):
                exit_code = main()

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            return exit_code, stdout.getvalue(), metadata, output_path.exists()

    def test_reports_failed_sources_without_dropping_successful_records(self):
        record = {"news_id": "rss_ok", "title": "Agent update"}
        with patch(
            "app.connectors_rss.fetch_rss",
            side_effect=[[record], OSError("connection reset")],
        ):
            records, errors = collect_rss_with_errors(
                ["https://ok.test/rss", "https://bad.test/rss"]
            )

        self.assertEqual(records, [record])
        self.assertEqual(
            errors,
            [{"url": "https://bad.test/rss", "error": "connection reset"}],
        )

    def test_collect_rss_remains_a_records_only_compatibility_api(self):
        record = {"news_id": "rss_ok", "title": "Agent update"}
        with patch("app.connectors_rss.fetch_rss", return_value=[record]):
            self.assertEqual(collect_rss(["https://ok.test/rss"]), [record])

    def test_cli_fails_when_every_rss_source_fails_but_still_writes_report(self):
        error = {"url": "https://bad.test/rss", "error": "timeout"}
        exit_code, stdout, metadata, report_created = self._run_cli(
            ["https://bad.test/rss"], ([], [error])
        )

        self.assertEqual(exit_code, 1)
        self.assertTrue(report_created)
        self.assertIn("RSS 采集失败：1/1 个源", stdout)
        self.assertEqual(
            metadata["rss_collection"],
            {"requested": 1, "succeeded": 0, "failed": 1, "errors": [error]},
        )

    def test_cli_continues_successfully_when_only_one_rss_source_fails(self):
        record = {
            "news_id": "rss_ok",
            "title": "Agent update",
            "content": "Agent update",
            "source_name": "Feed",
            "url": "https://ok.test/article",
        }
        error = {"url": "https://bad.test/rss", "error": "timeout"}
        exit_code, stdout, metadata, report_created = self._run_cli(
            ["https://ok.test/rss", "https://bad.test/rss"], ([record], [error])
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(report_created)
        self.assertIn("RSS 采集失败：1/2 个源", stdout)
        self.assertEqual(metadata["rss_collection"]["succeeded"], 1)


if __name__ == "__main__":
    unittest.main()
