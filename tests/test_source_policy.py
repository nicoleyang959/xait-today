"""Source removal reaches every publication path without rewriting old inputs."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xait_source_policy", ROOT / "xait.py")
xait = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(xait)


def legacy_issue():
    return json.loads((ROOT / "content" / "issues" / "2026-09-01.json").read_text(encoding="utf-8"))


class ActiveSourcePolicyTests(unittest.TestCase):
    def test_retired_source_aliases_are_disabled_but_tiktok_remains_active(self):
        for source_id in ("xiaohongshu", "xhs", "rednote", "red", "小红书", "douyin", "抖音",
                          " SOCIAL_XHS ", "social-rednote", "social-Xiao-Hong-Shu", "social-抖音",
                          "social-red", " Dou Yin ", "social - xhs"):
            with self.subTest(source_id=source_id):
                self.assertFalse(xait.source_enabled(source_id))
        for source_id in ("tiktok", "social-tiktok", "TikTok", "reddit", "red-news", "xiaohongshu-news"):
            with self.subTest(source_id=source_id):
                self.assertTrue(xait.source_enabled(source_id))
        section = next(section for section in legacy_issue()["sections"] if section["kind"] == "social")
        section["platforms"] = [{**section["platforms"][0], "id": "rednote", "title": "Rednote Top 10"}]
        section["overview"] = "RED provides this source snapshot."
        self.assertEqual([], xait.active_social_section(section)["platforms"])
        self.assertEqual(xait.SOCIAL_OVERVIEW, xait.active_social_section(section)["overview"])

    def test_empty_social_contract_is_valid_and_hidden(self):
        issue = legacy_issue()
        section = next(section for section in issue["sections"] if section["kind"] == "social")
        section["platforms"] = []
        xait.validate_issue(issue)
        self.assertEqual("", xait._render_social(section))
        self.assertNotIn('id="' + section["id"] + '"', xait._render_sections(issue))
        self.assertEqual([], xait._social_compat(issue)["platforms"])
        schema = json.loads((ROOT / "content" / "schema" / "issue-v1.schema.json").read_text(encoding="utf-8"))
        self.assertNotIn("minItems", schema["$defs"]["socialSection"]["properties"]["platforms"])

    def test_legacy_render_and_compatibility_filter_only_disabled_records(self):
        issue = legacy_issue()
        original = copy.deepcopy(issue)
        section = next(section for section in issue["sections"] if section["kind"] == "social")
        section["overview"] = "小红书按赞藏评，抖音按点赞量。"
        original = copy.deepcopy(issue)
        active = xait.active_issue(issue)
        enabled = next(section for section in active["sections"] if section["kind"] == "social")
        self.assertEqual([platform for platform in section["platforms"] if platform["id"] not in {"xiaohongshu", "douyin"}], enabled["platforms"])
        self.assertEqual(original, issue)
        self.assertEqual(active, xait.active_issue(active))
        for rendered in (xait._render_social(section), xait._render_sections(issue), json.dumps(xait._social_compat(issue), ensure_ascii=False)):
            self.assertNotIn("小红书", rendered)
            self.assertNotIn("抖音", rendered)
            self.assertNotIn("xiaohongshu", rendered)
            self.assertNotIn("douyin", rendered)
            self.assertIn("Reddit", rendered)

    def test_disabled_v2_sources_articles_and_empty_navigation_are_hidden(self):
        issue = json.loads((ROOT / "content" / "issues" / "2026-10-07.json").read_text(encoding="utf-8"))
        for source_id, label in (("social-xiaohongshu", "小红书"), ("social-douyin", "抖音")):
            issue["sources"].append({"id": source_id, "label": label, "status": "ok", "checkedAt": None,
                                     "lastSuccessAt": None, "itemCount": 1, "message": ""})
            issue["articles"].append({"id": source_id + "-article", "sourceId": source_id, "title": label + " AI news",
                                      "url": "https://example.org/" + source_id,
                                      "publishedAt": "2026-10-06T12:00:00+08:00", "dateEvidence": "exact",
                                      "collectedAt": issue["generatedAt"], "category": "models"})
        social = next(section for section in issue["sections"] if section["kind"] == "social")
        social["platforms"] = []
        xait.validate_issue(issue)
        active = xait.active_issue(issue)
        self.assertFalse(any(not xait.source_enabled(source["id"]) for source in active["sources"]))
        self.assertFalse(any(not xait.source_enabled(article["sourceId"]) for article in active["articles"]))
        rendered = xait._render_sections(issue)
        self.assertNotIn('href="#' + social["id"] + '"', rendered)
        self.assertNotIn('id="' + social["id"] + '"', rendered)
        self.assertNotIn("social-xiaohongshu", json.dumps(active))
        self.assertNotIn("social-douyin", json.dumps(active))
        for label in ("小红书", "抖音"):
            self.assertNotIn(label, xait.render_editorial(issue))

    def test_ordinary_platform_news_is_preserved(self):
        issue = legacy_issue()
        article_section = next(section for section in issue["sections"] if section["kind"] == "links")
        article_section["items"].append({"title": "小红书发布 AI 开源模型，抖音介绍新产品", "url": "https://example.org/ai-news"})
        active = xait.active_issue(issue)
        self.assertEqual(article_section, next(section for section in active["sections"] if section["id"] == article_section["id"]))
        self.assertIn("小红书发布 AI 开源模型，抖音介绍新产品", xait._render_sections(issue))

    def test_build_filters_all_archives_and_hashes_without_input_mutation(self):
        issues = xait.load_issues()
        original = copy.deepcopy(issues)
        with tempfile.TemporaryDirectory(prefix="xait-source-policy-") as temporary:
            destination = Path(temporary)
            xait.build_site(destination, issues)
            xait.validate_built_site(destination, issues)
            health = json.loads((destination / "health.json").read_text(encoding="utf-8"))
            for issue in issues:
                published = json.loads((destination / "issues" / (issue["date"] + ".json")).read_text(encoding="utf-8"))
                self.assertEqual(xait.active_issue(issue), published)
                xait.validate_issue(published)
                self.assertEqual(hashlib.sha256(xait._canonical_json(published)).hexdigest(), health["issueSha256"][issue["date"]])
                archive = (destination / "archive" / issue["date"] / "index.html").read_text(encoding="utf-8")
                for platform in ("xiaohongshu", "douyin"):
                    self.assertNotIn('id="platform-' + platform + '"', archive)
                compat = json.loads((destination / ("social-research-" + issue["date"] + ".json")).read_text(encoding="utf-8"))
                self.assertTrue(all(platform["key"] not in {"xiaohongshu", "douyin"} for platform in compat["platforms"]))
        self.assertEqual(original, issues)

    def test_disabled_input_is_still_checked_before_filtering(self):
        issue = legacy_issue()
        social = next(section for section in issue["sections"] if section["kind"] == "social")
        disabled = next(platform for platform in social["platforms"] if platform["id"] == "xiaohongshu")
        disabled["origin"] = "Cookie: private-session"
        with tempfile.TemporaryDirectory(prefix="xait-source-policy-") as temporary:
            with self.assertRaises(xait.XaitError):
                xait.build_site(Path(temporary), [issue])


if __name__ == "__main__":
    unittest.main()
