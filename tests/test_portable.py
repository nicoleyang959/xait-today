"""Black-box tests for the zero-dependency xAIT Today deployment contract."""

from __future__ import annotations

import hashlib
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
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


REPOSITORY = Path(__file__).resolve().parents[1]


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
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(repository / "xait.py"), *arguments],
        cwd=str(cwd or repository),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
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

    def test_commands_work_when_invoked_outside_repository(self) -> None:
        temporary, repository = self.make_checkout()
        self.addCleanup(temporary.cleanup)
        with tempfile.TemporaryDirectory(prefix="xait-external-cwd-") as external:
            external_path = Path(external)
            before = sorted(external_path.iterdir())
            run_cli(repository, "check", cwd=external_path)
            run_cli(repository, "build", cwd=external_path)
            self.assertEqual(before, sorted(external_path.iterdir()))

    def test_serve_exposes_homepage_and_health(self) -> None:
        temporary, repository = self.make_checkout()
        self.addCleanup(temporary.cleanup)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        process = subprocess.Popen(
            [
                sys.executable,
                str(repository / "xait.py"),
                "serve",
                "--port",
                str(port),
            ],
            cwd=str(repository.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.addCleanup(self._stop_process, process)

        homepage = None
        health = None
        deadline = time.monotonic() + 20
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                self.fail(f"serve exited early ({process.returncode}):\n{output}")
            try:
                with urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
                    self.assertEqual(200, response.status)
                    self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])
                    self.assertEqual(
                        "strict-origin-when-cross-origin",
                        response.headers["Referrer-Policy"],
                    )
                    self.assertEqual("no-store", response.headers["Cache-Control"])
                    homepage = response.read().decode("utf-8")
                with urlopen(
                    f"http://127.0.0.1:{port}/health.json", timeout=1
                ) as response:
                    self.assertEqual(200, response.status)
                    health = json.loads(response.read().decode("utf-8"))
                break
            except (OSError, URLError, json.JSONDecodeError) as error:
                last_error = error
                time.sleep(0.1)

        self.assertIsNotNone(homepage, last_error)
        self.assertIn("xAIT 今日", homepage)
        self.assertIsInstance(health, dict)
        with self.assertRaises(HTTPError) as directory_error:
            urlopen(f"http://127.0.0.1:{port}/assets/", timeout=1)
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
