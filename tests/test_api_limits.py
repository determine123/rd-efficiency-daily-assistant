from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import api
from app.api import BoundedTaskRunner, TaskCapacityError, TaskTimeoutError
from app.config import Settings
from app.input_validation import InputValidationError


class BoundedTaskRunnerTests(unittest.TestCase):
    def test_successful_tasks_release_their_slot(self):
        runner = BoundedTaskRunner(1, 1)
        try:
            self.assertEqual(runner.run(lambda: "first"), "first")
            self.assertEqual(runner.run(lambda: "second"), "second")
        finally:
            runner.shutdown()

    def test_rejects_new_work_while_all_slots_are_busy(self):
        started = threading.Event()
        release = threading.Event()
        results: list[str] = []
        runner = BoundedTaskRunner(1, 1)

        def slow_task():
            started.set()
            release.wait(1)
            return "finished"

        thread = threading.Thread(
            target=lambda: results.append(runner.run(slow_task)),
            daemon=True,
        )
        try:
            thread.start()
            self.assertTrue(started.wait(1))
            with self.assertRaises(TaskCapacityError):
                runner.run(lambda: "unexpected")
        finally:
            release.set()
            thread.join(2)
            runner.shutdown()

        self.assertEqual(results, ["finished"])

    def test_timeout_keeps_slot_until_background_work_finishes(self):
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        runner = BoundedTaskRunner(1, 0.05)

        def slow_task():
            started.set()
            release.wait(1)
            finished.set()
            return "finished"

        try:
            with self.assertRaises(TaskTimeoutError):
                runner.run(slow_task)
            self.assertTrue(started.is_set())
            with self.assertRaises(TaskCapacityError):
                runner.run(lambda: "unexpected")

            release.set()
            self.assertTrue(finished.wait(1))
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                try:
                    self.assertEqual(runner.run(lambda: "available"), "available")
                    break
                except TaskCapacityError:
                    time.sleep(0.01)
            else:
                self.fail("超时任务结束后未释放并发槽")
        finally:
            release.set()
            runner.shutdown()


class ApiLimitMappingTests(unittest.TestCase):
    def test_both_generation_endpoints_return_503_when_saturated(self):
        for endpoint in (api.generate, api.invoke_workflow):
            with self.subTest(endpoint=endpoint.__name__):
                with (
                    patch.object(
                        api.report_runner,
                        "run",
                        side_effect=TaskCapacityError("busy"),
                    ),
                    self.assertRaises(HTTPException) as raised,
                ):
                    endpoint({})
                self.assertEqual(raised.exception.status_code, 503)
                self.assertEqual(raised.exception.headers, {"Retry-After": "1"})

    def test_both_generation_endpoints_return_504_when_timed_out(self):
        for endpoint in (api.generate, api.invoke_workflow):
            with self.subTest(endpoint=endpoint.__name__):
                with (
                    patch.object(
                        api.report_runner,
                        "run",
                        side_effect=TaskTimeoutError("timed out"),
                    ),
                    self.assertRaises(HTTPException) as raised,
                ):
                    endpoint({})
                self.assertEqual(raised.exception.status_code, 504)

    def test_both_generation_endpoints_return_422_for_invalid_input(self):
        for endpoint in (api.generate, api.invoke_workflow):
            with self.subTest(endpoint=endpoint.__name__):
                with (
                    patch.object(
                        api.report_runner,
                        "run",
                        side_effect=InputValidationError("git_records 必须是数组"),
                    ),
                    self.assertRaises(HTTPException) as raised,
                ):
                    endpoint({})
                self.assertEqual(raised.exception.status_code, 422)
                self.assertIn("git_records", raised.exception.detail)


class SettingsLimitTests(unittest.TestCase):
    def test_rejects_invalid_concurrency_and_timeout_settings(self):
        invalid_settings = (
            Settings(max_concurrent_requests=0),
            Settings(max_concurrent_requests=65),
            Settings(request_timeout_seconds=0),
            Settings(request_timeout_seconds=3601),
        )
        for settings in invalid_settings:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                settings.validate()


if __name__ == "__main__":
    unittest.main()
