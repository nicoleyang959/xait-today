"""Public, deterministic language overlays never replace canonical source facts."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xait_i18n_test", REPOSITORY / "xait.py")
assert SPEC is not None and SPEC.loader is not None
xait = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(xait)


def content_entry(source: str, **translations: str) -> dict[str, str]:
    return {"sourceSha256": hashlib.sha256(source.encode("utf-8")).hexdigest(), **translations}


class LanguageOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="xait-language-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog_dir = self.root / "site" / "i18n"
        self.catalog_dir.mkdir(parents=True)
        self.root_patch = patch.object(xait, "ROOT", self.root)
        self.directory_patch = patch.object(xait, "I18N_DIR", self.catalog_dir)
        self.root_patch.start()
        self.directory_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.directory_patch.stop)
        self.issue = copy.deepcopy(xait.load_issues()[-1])
        self.source = self.issue["articles"][0]["title"]
        self.ui = {"schemaVersion": 1, "entries": {"采集概况": {"zh": "采集概况", "en": "Collection overview"}}}
        self.content = {
            "schemaVersion": 1,
            "entries": {
                self.source: content_entry(self.source, zh="这是一条经过核对的中文译文", en=self.source),
                "An unrelated historical headline": content_entry("An unrelated historical headline", zh="无关历史标题"),
            },
        }
        self.write_catalogs()

    def write_catalogs(self) -> None:
        for kind, value in (("ui", self.ui), ("content", self.content)):
            (self.catalog_dir / (kind + ".json")).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_payload_is_scoped_and_preserves_canonical_facts(self) -> None:
        before = xait._canonical_json(self.issue)
        payload = xait.language_payload(self.issue)
        self.assertEqual(1, payload["schemaVersion"])
        self.assertEqual(self.ui["entries"], payload["ui"])
        self.assertEqual({self.source}, set(payload["content"]))
        self.assertNotIn("sourceSha256", payload["content"][self.source])
        self.assertEqual(before, xait._canonical_json(self.issue))
        payload["content"][self.source]["zh"] = "changed locally"
        self.assertNotEqual(payload, xait.language_payload(self.issue))

    def test_catalog_is_inert_escaped_json_not_inline_script(self) -> None:
        self.ui["entries"]["Comparison"] = {"zh": "小于 3 < 5 & 大于 7 > 2", "en": "3 < 5 & 7 > 2"}
        self.write_catalogs()
        rendered = xait.render_language_data(self.issue)
        self.assertTrue(rendered.startswith('<template id="xait-language-data">'))
        self.assertNotIn("<script", rendered)
        self.assertIn("&lt; 5 &amp;", rendered)
        parser = xait._SiteHTMLParser()
        parser.feed(rendered)
        self.assertEqual(0, parser.inline_scripts)
        self.assertFalse(parser.language_nested_nodes)
        self.assertEqual(xait.language_payload(self.issue), json.loads(parser.language_data[0]))

    def test_missing_content_falls_back_without_changing_source(self) -> None:
        (self.catalog_dir / "content.json").unlink()
        self.assertEqual({}, xait.language_payload(self.issue)["content"])
        self.assertEqual(self.source, self.issue["articles"][0]["title"])
        (self.catalog_dir / "ui.json").unlink()
        self.assertEqual({"ui": {}, "content": {}}, xait.load_language_catalogs())
        with self.assertRaises(xait.XaitError):
            xait.load_language_catalogs(required=True)

    def test_hashes_types_limits_and_duplicate_keys_are_strict(self) -> None:
        mutations = [
            {"schemaVersion": True, "entries": {}},
            {"schemaVersion": 1, "entries": []},
            {"schemaVersion": 1, "entries": {"source": {"sourceSha256": "0" * 64, "en": "translation"}}},
            {"schemaVersion": 1, "entries": {"source": content_entry("source", en="")}},
            {"schemaVersion": 1, "entries": {"source": content_entry("source")}},
            {"schemaVersion": 1, "entries": {"source": {**content_entry("source", en="translation"), "unexpected": "field"}}},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.content = mutation
                self.write_catalogs()
                with self.assertRaises(xait.XaitError):
                    xait.load_language_catalogs()
        (self.catalog_dir / "content.json").write_text('{"schemaVersion":1,"entries":{},"entries":{}}', encoding="utf-8")
        with self.assertRaises(xait.XaitError):
            xait.load_language_catalogs()
        self.content = {"schemaVersion": 1, "entries": {"a": content_entry("a", en="a"), "b": content_entry("b", en="b")}}
        self.write_catalogs()
        with patch.object(xait, "LANGUAGE_CATALOG_MAX_ENTRIES", 1):
            with self.assertRaises(xait.XaitError):
                xait.load_language_catalogs()

    def test_unused_translations_are_still_security_scanned(self) -> None:
        for text in ("password=not-a-real-secret", "http://127.0.0.1/private", "/Users/example/private", "<script>bad</script>"):
            with self.subTest(text=text):
                self.content = {"schemaVersion": 1, "entries": {"Unused source": content_entry("Unused source", en=text)}}
                self.write_catalogs()
                with self.assertRaises(xait.XaitError) as failure:
                    xait.load_language_catalogs()
                self.assertEqual(xait.EXIT_SECURITY, failure.exception.exit_code)

    def test_source_keys_are_security_scanned_too(self) -> None:
        source = "cookie=not-a-real-secret"
        self.content = {"schemaVersion": 1, "entries": {source: content_entry(source, en="harmless")}}
        self.write_catalogs()
        with self.assertRaises(xait.XaitError) as failure:
            xait.load_language_catalogs()
        self.assertEqual(xait.EXIT_SECURITY, failure.exception.exit_code)

    def test_symbolic_files_and_parent_directories_are_rejected(self) -> None:
        target = self.root / "real-content.json"
        target.write_text(json.dumps(self.content), encoding="utf-8")
        path = self.catalog_dir / "content.json"
        path.unlink()
        try:
            path.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links not available")
        with self.assertRaises(xait.XaitError) as failure:
            xait.load_language_catalogs()
        self.assertEqual(xait.EXIT_SECURITY, failure.exception.exit_code)
        linked_directory = self.root / "linked-i18n"
        linked_directory.symlink_to(self.catalog_dir, target_is_directory=True)
        with patch.object(xait, "I18N_DIR", linked_directory):
            with self.assertRaises(xait.XaitError):
                xait.load_language_catalogs()

    def test_removed_source_translations_are_not_embedded(self) -> None:
        section = next(section for section in self.issue["sections"] if section["kind"] == "social")
        title = "Retired-source-only example"
        section["platforms"].append({"id": "douyin", "title": title})
        self.content["entries"][title] = content_entry(title, zh="停用来源")
        self.write_catalogs()
        self.assertNotIn(title, xait.language_payload(self.issue)["content"])

    def test_renderer_text_pieces_can_receive_exact_translations(self) -> None:
        source = "今日必读"
        self.content["entries"][source] = content_entry(source, en="Today's essentials")
        self.write_catalogs()
        self.assertIn(source, xait.language_payload(self.issue)["content"])

    def test_build_audits_controls_payload_and_keeps_public_json_unchanged(self) -> None:
        template = xait.TEMPLATE_PATH.read_text(encoding="utf-8")
        if "{{LANGUAGE_DATA}}" not in template:
            template = template.replace("</body>", '<button type="button" data-language="zh">中文</button><button type="button" data-language="en">English</button>{{LANGUAGE_DATA}}</body>')
        template_path = self.root / "page.html"
        template_path.write_text(template, encoding="utf-8")
        output = self.root / "built"
        with patch.object(xait, "TEMPLATE_PATH", template_path):
            xait.build_site(output, [self.issue])
            xait.validate_built_site(output, [self.issue])
            self.assertEqual(xait._canonical_json(xait.active_issue(self.issue)), (output / "issues" / (self.issue["date"] + ".json")).read_bytes())
            page_path = output / "index.html"
            original = page_path.read_text(encoding="utf-8")
            page_path.write_text(original.replace('data-language="en"', 'data-language="invalid"'), encoding="utf-8")
            with self.assertRaises(xait.XaitError):
                xait.validate_built_site(output, [self.issue])
            page_path.write_text(original.replace("Collection overview", "Unverified replacement"), encoding="utf-8")
            with self.assertRaises(xait.XaitError):
                xait.validate_built_site(output, [self.issue])


if __name__ == "__main__":
    unittest.main()
