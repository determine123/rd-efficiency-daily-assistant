from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from app.input_validation import InputValidationError, validate_input_data
from app.main import _parse_day, main


class InputValidationTests(unittest.TestCase):
    def test_rejects_non_object_and_wrong_container_shapes(self):
        cases = (
            ([], "顶层必须是对象"),
            ({"team_config": []}, "team_config 必须是对象"),
            ({"git_records": "change"}, "git_records 必须是数组"),
            ({"news_records": [None]}, "news_records[0] 必须是对象"),
            ({"historical_reports": [1]}, "historical_reports[0] 必须是对象"),
        )
        for data, message in cases:
            with self.subTest(data=data), self.assertRaises(
                InputValidationError
            ) as raised:
                validate_input_data(data)
            self.assertIn(message, str(raised.exception))

    def test_rejects_invalid_dates(self):
        for value in ("2026/11/13", "2026-13-01", "2026-02-30", ""):
            with self.subTest(value=value), self.assertRaises(InputValidationError):
                validate_input_data({"current_date": value})

    def test_accepts_documented_empty_input_and_null_optional_fields(self):
        validate_input_data(
            {
                "current_date": "2026-11-13",
                "team_config": {},
                "git_records": [],
                "news_records": None,
                "historical_reports": [],
            }
        )

    def test_invalid_day_argument_has_actionable_message(self):
        with self.assertRaises(argparse.ArgumentTypeError) as raised:
            _parse_day("2026-02-30")
        self.assertIn("--day", str(raised.exception))
        self.assertIn("2026-02-30", str(raised.exception))


class CliInputBoundaryTests(unittest.TestCase):
    def _run_main(self, payload, *extra_args):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            output_path = root / "report.md"
            input_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            stderr = io.StringIO()
            argv = [
                "app.main",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                *extra_args,
            ]
            with patch("sys.argv", argv), redirect_stderr(stderr):
                exit_code = main()
            return exit_code, stderr.getvalue(), output_path.exists()

    def test_malformed_record_container_returns_two_without_report(self):
        exit_code, stderr, report_created = self._run_main(
            {"current_date": "2026-11-13", "git_records": "not-a-list"}
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("git_records 必须是数组", stderr)
        self.assertFalse(report_created)

    def test_rejects_invalid_input_before_collecting_external_data(self):
        with (
            patch(
                "app.main.collect_git_records_from_repositories"
            ) as collect_git,
            patch("app.main.collect_rss_with_errors") as collect_rss,
        ):
            exit_code, stderr, report_created = self._run_main(
                {"current_date": "2026-11-13", "git_records": "not-a-list"},
                "--repo",
                ".",
                "--rss",
                "https://example.com/feed.xml",
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("git_records 必须是数组", stderr)
        self.assertFalse(report_created)
        collect_git.assert_not_called()
        collect_rss.assert_not_called()

    def test_malformed_json_returns_two_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            output_path = root / "report.md"
            input_path.write_text("{not json", encoding="utf-8")
            stderr = io.StringIO()
            argv = [
                "app.main",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ]
            with patch("sys.argv", argv), redirect_stderr(stderr):
                exit_code = main()
            self.assertEqual(exit_code, 2)
            self.assertIn("输入错误", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertFalse(output_path.exists())

    def test_top_level_array_returns_two_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            output_path = root / "report.md"
            input_path.write_text("[]", encoding="utf-8")
            stderr = io.StringIO()
            argv = [
                "app.main",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ]
            with patch("sys.argv", argv), redirect_stderr(stderr):
                exit_code = main()
            self.assertEqual(exit_code, 2)
            self.assertIn("顶层必须是对象", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
