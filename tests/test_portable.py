"""Black-box tests for the zero-dependency xAIT Today deployment contract."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener


REPOSITORY = Path(__file__).resolve().parents[1]


def minimal_environment() -> dict[str, str]:
    environment = {"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    if sys.platform == "win32" and os.environ.get("SystemRoot"):
        environment["SystemRoot"] = os.environ["SystemRoot"]
    return environment


def copy_repository(destination: Path) -> Path:
    """Copy the public checkout without VCS or local test artifacts."""
    target = destination / "xait-today"
    ignored = shutil.ignore_patterns(
        ".git",
        ".github",
        ".coverage",
        ".pytest_cache",
        "__pycache__",
        "*.pyc",
    )
    shutil.copytree(REPOSITORY, target, ignore=ignored)
    return target


def run_cli(
    repository: Path,
    *arguments: str,
    cwd: Path | None = None,
    expect_success: bool = True,
    environment_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = minimal_environment()
    environment.update(environment_overrides or {})
    result = subprocess.run(
        [sys.executable, str(repository / "xait.py"), *arguments],
        cwd=str(cwd or repository),
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
        env=environment,
    )
    if expect_success and result.returncode != 0:
        raise AssertionError(
            f"xait.py {' '.join(arguments)} failed ({result.returncode}):\n"
            f"{result.stdout}"
        )
    return result


def tree_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def replace_first_public_url(value: object) -> bool:
    """Replace one declared URL with a forbidden private endpoint."""
    if isinstance(value, dict):
        for key in list(value):
            item = value[key]
            if key.lower().endswith("url") and isinstance(item, str):
                value[key] = "http://127.0.0.1/private"
                return True
            if replace_first_public_url(item):
                return True
    elif isinstance(value, list):
        for item in value:
            if replace_first_public_url(item):
                return True
    return False


class PortableCommandTests(unittest.TestCase):
    def make_checkout(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory(prefix="xait-portable-test-")
        return temporary, copy_repository(Path(temporary.name))

    def test_check_and_build_are_deterministic(self) -> None:
        temporary, repository = self.make_checkout()
        self.addCleanup(temporary.cleanup)

        original = tree_digest(repository)
        run_cli(repository, "check")
        run_cli(repository, "build")
        first = tree_digest(repository)
        self.assertEqual(
            original,
            first,
            "a clean checkout must already contain the reproducible build output",
        )
        run_cli(repository, "build")
        second = tree_digest(repository)

        self.assertEqual(first, second)
        run_cli(repository, "check")

    def test_malformed_issue_is_rejected_without_replacing_docs(self) -> None:
        temporary, repository = self.make_checkout()
        self.addCleanup(temporary.cleanup)
        before = tree_digest(repository / "docs")
        issue = repository / "content" / "issues" / "2099-01-01.json"
        issue.parent.mkdir(parents=True, exist_ok=True)
        issue.write_text('{"schemaVersion": 1,', encoding="utf-8")

        checked = run_cli(repository, "check", expect_success=False)
        built = run_cli(repository, "build", expect_success=False)

        self.assertNotEqual(checked.returncode, 0, checked.stdout)
        self.assertNotEqual(built.returncode, 0, built.stdout)
        self.assertEqual(before, tree_digest(repository / "docs"))

    def test_cli_output_is_utf8_with_a_legacy_system_encoding(self) -> None:
        temporary, repository = self.make_checkout()
        self.addCleanup(temporary.cleanup)
        legacy_environment = {"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"}
        for command in ("check", "build"):
            result = run_cli(
                repository, command, environment_overrides=legacy_environment
            )
            self.assertIn("最新", result.stdout)
        checked_json = run_cli(
            repository, "check", "--json", environment_overrides=legacy_environment
        )
        self.assertTrue(json.loads(checked_json.stdout)["ok"])

        issue = repository / "content" / "issues" / "2099-01-01.json"
        issue.write_text('{"schemaVersion": 1,', encoding="utf-8")
        rejected = run_cli(
            repository, "check", expect_success=False,
            environment_overrides=legacy_environment,
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("错误：", rejected.stdout)
        rejected_json = run_cli(
            repository, "check", "--json", expect_success=False,
            environment_overrides=legacy_environment,
        )
        self.assertNotEqual(0, rejected_json.returncode)
        self.assertIn("无法解析", json.loads(rejected_json.stdout)["error"])

    def test_history_matches_issues_and_real_archives(self) -> None:
        temporary, repository = self.make_checkout()
        self.addCleanup(temporary.cleanup)
        run_cli(repository, "build")

        issue_dates = sorted(
            path.stem for path in (repository / "content" / "issues").glob("*.json")
        )
        self.assertGreaterEqual(len(issue_dates), 1)

        history_path = repository / "docs" / "history.json"
        history = json.loads(history_path.read_text(encoding="utf-8"))
        serialized_history = json.dumps(history, ensure_ascii=False, sort_keys=True)
        for issue_date in issue_dates:
            self.assertIn(issue_date, serialized_history)
            archive = repository / "docs" / "archive" / issue_date / "index.html"
            self.assertTrue(archive.is_file(), archive)

        archive_dates = sorted(
            path.parent.name
            for path in (repository / "docs" / "archive").glob("*/index.html")
        )
        self.assertEqual(issue_dates, archive_dates)

        latest_html = (repository / "docs" / "index.html").read_text(encoding="utf-8")
        self.assertIn(issue_dates[-1], latest_html)

    def test_private_url_is_rejected_and_escaped_data_cannot_publish(self) -> None:
        temporary, repository = self.make_checkout()
        self.addCleanup(temporary.cleanup)
        run_cli(repository, "build")
        before = tree_digest(repository / "docs")

        latest = sorted((repository / "content" / "issues").glob("*.json"))[-1]
        issue = json.loads(latest.read_text(encoding="utf-8"))
        self.assertTrue(replace_first_public_url(issue), "fixture must contain a URL")
        latest.write_text(
            json.dumps(issue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        checked = run_cli(repository, "check", expect_success=False)
        built = run_cli(repository, "build", expect_success=False)

        self.assertNotEqual(checked.returncode, 0, checked.stdout)
        self.assertNotEqual(built.returncode, 0, built.stdout)
        self.assertEqual(before, tree_digest(repository / "docs"))

    def test_issue_timestamps_must_match_the_issue_date(self) -> None:
        temporary, repository = self.make_checkout()
        self.addCleanup(temporary.cleanup)
        before = tree_digest(repository / "docs")
        latest = sorted((repository / "content" / "issues").glob("*.json"))[-1]
        issue = json.loads(latest.read_text(encoding="utf-8"))
        issue["generatedAt"] = "2099-01-01T08:45:00+08:00"
        latest.write_text(
            json.dumps(issue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        built = run_cli(repository, "build", expect_success=False)

        self.assertNotEqual(built.returncode, 0, built.stdout)
        self.assertIn("generatedAt", built.stdout)
        self.assertEqual(before, tree_digest(repository / "docs"))

    def test_stale_wechat_capture_is_accepted_only_with_clear_labels(self) -> None:
        temporary, repository = self.make_checkout()
        self.addCleanup(temporary.cleanup)
        latest = sorted((repository / "content" / "issues").glob("*.json"))[-1]
        original = json.loads(latest.read_text(encoding="utf-8"))
        from datetime import date, timedelta
        previous = (date.fromisoformat(original["date"]) - timedelta(days=1)).isoformat()

        for mode in ("stale", "fresh", "today-badge", "future"):
            issue = json.loads(json.dumps(original))
            wechat = next(section for section in issue["sections"] if section["kind"] == "wechat")
            wechat["capturedAt"] = previous + "T08:45:00+08:00"
            for account in wechat["accounts"]:
                account["statusTone"] = "stale"
                account["status"] = "沿用 " + previous + " 快照"
                for item in account["items"]:
                    item["badge"] = "最近"
            if mode == "fresh":
                wechat["accounts"][0]["statusTone"] = "fresh"
            elif mode == "today-badge":
                next(a for a in wechat["accounts"] if a["items"])["items"][0]["badge"] = "今日"
            elif mode == "future":
                wechat["capturedAt"] = "2099-01-01T08:45:00+08:00"
            latest.write_text(json.dumps(issue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            before = tree_digest(repository / "docs")
            result = run_cli(repository, "build", expect_success=(mode == "stale"))
            if mode == "stale":
                self.assertEqual(0, result.returncode)
                run_cli(repository, "check")
            else:
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(before, tree_digest(repository / "docs"))

    def test_source_health_is_collapsible_and_text_is_escaped(self) -> None:
        temporary, repository = self.make_checkout()
        self.addCleanup(temporary.cleanup)
        latest = sorted((repository / "content" / "issues").glob("*.json"))[-1]
        issue = json.loads(latest.read_text(encoding="utf-8"))
        issue["sections"] = [section for section in issue["sections"] if section["id"] != "source-health"]
        issue["sections"].append({
            "id": "source-health", "kind": "blocks", "title": "来源状态",
            "blocks": [{"type": "paragraph", "spans": [{"text": "Source A & B"}]}],
        })
        latest.write_text(json.dumps(issue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        run_cli(repository, "build")
        page = (repository / "docs" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<details class="source-health"><summary>', page)
        self.assertIn("Source A &amp; B", page)
        run_cli(repository, "check")

    def test_commands_work_when_invoked_outside_repository(self) -> None:
        temporary, repository = self.make_checkout()
        self.addCleanup(temporary.cleanup)
        with tempfile.TemporaryDirectory(prefix="xait-external-cwd-") as external:
            external_path = Path(external)
            before = sorted(external_path.iterdir())
            run_cli(repository, "check", cwd=external_path)
            run_cli(repository, "build", cwd=external_path)
            self.assertEqual(before, sorted(external_path.iterdir()))

    def test_local_server_binding_does_not_require_reverse_dns(self) -> None:
        spec = importlib.util.spec_from_file_location("xait_under_test", REPOSITORY / "xait.py")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        application = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(application)
        with patch("socket.getfqdn", side_effect=AssertionError("reverse DNS is unavailable")), \
             patch("socket.gethostbyaddr", side_effect=AssertionError("reverse DNS is unavailable")):
            with application._ReusableThreadingServer(
                ("127.0.0.1", 0), application._QuietHandler
            ) as server:
                self.assertEqual("127.0.0.1", server.server_name)
                self.assertEqual(server.server_address[1], server.server_port)
                self.assertGreater(server.server_port, 0)

    def test_serve_exposes_homepage_and_health(self) -> None:
        temporary, repository = self.make_checkout()
        self.addCleanup(temporary.cleanup)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-c",
                "import faulthandler, runpy, sys; "
                "faulthandler.dump_traceback_later(10); "
                "script = sys.argv.pop(1); "
                "runpy.run_path(script, run_name='__main__')",
                str(repository / "xait.py"),
                "serve",
                "--port",
                str(port),
            ],
            cwd=str(repository.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            env=minimal_environment(),
        )
        self.addCleanup(self._stop_process, process)

        # This probe must stay on loopback even when the host/CI has proxies.
        # An explicit empty handler also skips macOS system proxy discovery.
        with patch("urllib.request.getproxies", side_effect=AssertionError("proxy discovery is not needed for loopback")):
            local_http = build_opener(ProxyHandler({}))

        homepage = None
        health = None
        deadline = time.monotonic() + 20
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                self.fail(f"serve exited early ({process.returncode}):\n{output}")
            try:
                with local_http.open(f"http://127.0.0.1:{port}/", timeout=1) as response:
                    self.assertEqual(200, response.status)
                    self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])
                    self.assertEqual(
                        "strict-origin-when-cross-origin",
                        response.headers["Referrer-Policy"],
                    )
                    self.assertEqual("no-store", response.headers["Cache-Control"])
                    homepage = response.read().decode("utf-8")
                with local_http.open(
                    f"http://127.0.0.1:{port}/health.json", timeout=1
                ) as response:
                    self.assertEqual(200, response.status)
                    health = json.loads(response.read().decode("utf-8"))
                break
            except (OSError, URLError, json.JSONDecodeError) as error:
                last_error = error
                time.sleep(0.1)

        if homepage is None or health is None:
            if process.poll() is None:
                process.terminate()
            try:
                output, _ = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate(timeout=5)
            self.fail(
                f"serve did not respond within 20 seconds: {last_error}\n"
                f"Child startup output / bounded stack trace:\n{output[-12000:]}"
            )
        self.assertIn("xAIT 今日", homepage)
        self.assertIsInstance(health, dict)
        with self.assertRaises(HTTPError) as directory_error:
            local_http.open(f"http://127.0.0.1:{port}/assets/", timeout=1)
        self.addCleanup(directory_error.exception.close)
        self.assertEqual(404, directory_error.exception.code)

    @staticmethod
    def _stop_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stdout:
            process.stdout.close()


if __name__ == "__main__":
    unittest.main()
