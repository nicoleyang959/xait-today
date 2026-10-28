"""Public build boundary: no account or private record is a build input."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("records_build", ROOT / "xait.py")
xait = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(xait)


class RecordsBuildTests(unittest.TestCase):
    def config(self, value):
        temporary = tempfile.TemporaryDirectory(prefix="xait-records-config-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "config.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return patch.object(xait, "RECORDS_CONFIG_PATH", path)

    def enabled(self):
        return {"enabled": True, "supabaseUrl": "https://abcdefghijklmnopqrst.supabase.co",
                "publishableKey": "sb_publishable_" + "SyntheticPublicValue1234",
                "redirectUrl": "https://example.org/xait/"}

    def test_default_off_has_no_cloud_endpoint_or_sdk_execution(self):
        self.assertFalse(xait._validate_records_config(xait._load_json(xait.RECORDS_CONFIG_PATH))["enabled"])
        page = (ROOT / "docs/index.html").read_text(encoding="utf-8")
        self.assertIn('id="saved-open"', page)
        self.assertIn('id="saved-projects"', page)
        if not xait.OFFICIAL_RECORDS_ENABLED:
            self.assertIn("connect-src 'none'", page)
            self.assertNotIn('src="assets/vendor/supabase', page)

    def test_official_binding_is_gated_and_site_exact(self):
        disabled = {"enabled": False, "supabaseUrl": "", "publishableKey": "", "redirectUrl": ""}
        official = self.enabled()
        with self.config(disabled), patch.object(xait, "OFFICIAL_RECORDS_BINDING", official), \
             patch.object(xait, "PUBLIC_BASE_URL", official["redirectUrl"]):
            with patch.object(xait, "OFFICIAL_RECORDS_ENABLED", False):
                self.assertEqual(disabled, xait.records_config())
            with patch.object(xait, "OFFICIAL_RECORDS_ENABLED", True):
                self.assertEqual(official, xait.records_config())
                issue = xait.load_issues()[-1]
                template = xait.TEMPLATE_PATH.read_text(encoding="utf-8")
                page = xait._render_page(template, issue, [issue["date"]], True, xait.load_language_catalogs())
                self.assertIn("connect-src https://abcdefghijklmnopqrst.supabase.co;", page)
                self.assertIn('src="assets/vendor/supabase-2.118.0.js"', page)
                archive = xait._render_page(template, issue, [issue["date"]], False, xait.load_language_catalogs())
                self.assertIn('src="../../assets/vendor/supabase-2.118.0.js"', archive)
        with self.config(disabled), patch.object(xait, "OFFICIAL_RECORDS_BINDING", official), \
             patch.object(xait, "PUBLIC_BASE_URL", "https://other.example/"), \
             patch.object(xait, "OFFICIAL_RECORDS_ENABLED", True):
            with self.assertRaises(xait.XaitError): xait.records_config()
        malformed = dict(official, publishableKey="sb_" + "secret_" + "a" * 40)
        with self.config(disabled), patch.object(xait, "OFFICIAL_RECORDS_BINDING", malformed), \
             patch.object(xait, "OFFICIAL_RECORDS_ENABLED", True):
            with self.assertRaises(xait.XaitError): xait.records_config()

    def test_explicit_deployer_config_takes_precedence_over_official_binding(self):
        custom = self.enabled()
        with self.config(custom), patch.object(xait, "OFFICIAL_RECORDS_ENABLED", True):
            self.assertEqual(custom, xait.records_config())

    def test_official_binding_has_valid_public_fields_and_exact_site(self):
        disabled = {"enabled": False, "supabaseUrl": "", "publishableKey": "", "redirectUrl": ""}
        with self.config(disabled), patch.object(xait, "OFFICIAL_RECORDS_ENABLED", True):
            official = xait.records_config()
            self.assertEqual(xait.PUBLIC_BASE_URL, official["redirectUrl"])
            self.assertTrue(official["publishableKey"].startswith("sb_publishable_"))

    def test_strict_public_configuration_and_exact_csp(self):
        issue = xait.load_issues()[-1]
        template = xait.TEMPLATE_PATH.read_text(encoding="utf-8")
        with self.config(self.enabled()):
            page = xait._render_page(template, issue, [issue["date"]], True, xait.load_language_catalogs())
            self.assertIn("connect-src https://abcdefghijklmnopqrst.supabase.co;", page)
            self.assertIn('src="assets/vendor/supabase-2.118.0.js"', page)
            self.assertNotIn("*.supabase.co", page)
            self.assertNotIn("unsafe-inline", page)
        invalid = []
        for field, value in [("publishableKey", "sb_" + "secret_" + "x" * 32),
                             ("publishableKey", "eyJ" + "x" * 50),
                             ("supabaseUrl", "https://evil.example"),
                             ("redirectUrl", "http://127.0.0.1/"),
                             ("redirectUrl", "https://example.org/?code=x"),
                             ("enabled", "false")]:
            data = self.enabled(); data[field] = value; invalid.append(data)
        data = self.enabled(); data["extra"] = "not permitted"; invalid.append(data)
        data = self.enabled(); data["enabled"] = False; invalid.append(data)
        for data in invalid:
            with self.subTest(data=list(data)):
                with self.config(data), self.assertRaises(xait.XaitError): xait.records_config()

    def test_immutable_official_sdk_not_blanket_scanner_exception(self):
        text = (ROOT / "site" / xait.SDK_ASSET).read_text(encoding="utf-8")
        self.assertEqual(xait.SDK_SHA256, hashlib.sha256(text.encode()).hexdigest())
        xait._scan_sensitive_text(text, xait.SDK_ASSET)
        for changed in (text + " ", text + "\n" + "sb_" + "secret_" + "x" * 40,
                        text.replace("localhost", "unexpected-host", 1)):
            with self.assertRaises(xait.XaitError): xait._scan_sensitive_text(changed, xait.SDK_ASSET)
        with self.assertRaises(xait.XaitError): xait._scan_sensitive_text(text, "assets/unknown-sdk.js")
        with self.assertRaises(xait.XaitError): xait._scan_sensitive_text("sb_" + "secret_" + "a" * 30, "issue.json")

    def test_only_real_project_links_have_compact_original_metadata(self):
        button = xait._save_project_button('A <private> "title"', "https://github.com/example/project", "github-trending", "2026-10-27")
        self.assertIn("data-save-project", button)
        self.assertIn('class="project-save-button"', button)
        self.assertIn("&lt;private&gt;", button)
        self.assertNotIn('A <private>', button)
        for url, source in [("https://www.producthunt.com/leaderboard/daily/2026/10/25", "product-hunt-ranking"),
                            ("https://github.com/example/project/issues", "github-trending"),
                            ("https://example.org/article", "hacker-news")]:
            self.assertEqual("", xait._save_project_button("Project", url, source, "2026-10-27"))

    def test_public_issue_is_not_extended_with_private_record_state(self):
        issue = xait.load_issues()[-1]
        original = copy.deepcopy(issue)
        xait._render_sections(issue)
        self.assertEqual(original, issue)
        self.assertNotIn("saved_projects", xait._canonical_json(xait.active_issue(issue)).decode())

    def test_service_worker_has_strict_public_allowlist(self):
        source = (ROOT / "site/sw.js").read_text(encoding="utf-8")
        self.assertIn('request.method !== "GET"', source)
        self.assertIn('request.headers.has("Authorization")', source)
        self.assertIn('url.origin !== root.origin', source)
        self.assertIn('key !== "lang"', source)
        self.assertNotIn("cache-first", source)
        self.assertIn('Quota is not a reading failure', source)


if __name__ == "__main__":
    unittest.main()
