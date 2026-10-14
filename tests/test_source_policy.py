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


def latest_v2_issue():
    for path in reversed(sorted((ROOT / "content" / "issues").glob("*.json"))):
        issue = json.loads(path.read_text(encoding="utf-8"))
        if issue["schemaVersion"] == 2:
            return issue
    raise AssertionError("Keep at least one v2 issue for source policy tests")


def with_x_signals(status="ok", count=10):
    issue = latest_v2_issue()
    checked_at = issue["generatedAt"]
    messages = {
        "ok": "公开信号采集成功",
        "partial": "部分查询未完成",
        "empty": "本次未检出符合条件的公开内容",
        "unavailable": "来源暂不可用",
        "not_run": "本期未运行 X 采集",
    }
    issue["sources"].append({
        "id": xait.X_SIGNAL_SOURCE_ID,
        "label": xait.X_SIGNAL_TITLE,
        "status": status,
        "checkedAt": checked_at,
        "lastSuccessAt": checked_at if status in {"ok", "partial"} else None,
        "itemCount": count if status in {"ok", "partial"} else 0,
        "message": messages[status],
    })
    if status in {"ok", "partial"}:
        labels = sorted(xait.X_SIGNAL_LABELS)
        issue["sections"].append({
            "id": xait.X_SIGNAL_SOURCE_ID,
            "kind": "links",
            "title": xait.X_SIGNAL_TITLE,
            "items": [
                {
                    "title": labels[index % len(labels)],
                    "url": "https://x.com/i/status/{0}".format(1000000000000000000 + index),
                    "meta": "本期第 {0} 位".format(index + 1),
                }
                for index in range(count)
            ],
        })
    return issue


class ActiveSourcePolicyTests(unittest.TestCase):
    def test_direct_sources_and_social_platforms_have_separate_policies(self):
        for source_id in ("hacker-news", "github-trending", "product-hunt", "techmeme", "arxiv", "x-ai-signals"):
            with self.subTest(source_id=source_id):
                self.assertTrue(xait.source_enabled(source_id))
        for source_id in ("hexi-2077", "bluesky", "stocktwits", "y-combinator",
                          "hacker-news-best", "hacker_news_new", " HACKER NEWS NEW ",
                          "xiaohongshu", "xhs", "rednote", "red", "小红书", "douyin", "抖音",
                          "reddit", "youtube", "github"):
            with self.subTest(source_id=source_id):
                self.assertFalse(xait.source_enabled(source_id))
        for platform_id in ("x", "twitter", "xiaohongshu", "xhs", "rednote", "douyin", "reddit", "youtube",
                            "hacker-news", "hackernews", "github", "tiktok", "future-platform"):
            with self.subTest(platform_id=platform_id):
                self.assertFalse(xait.social_platform_enabled(platform_id))
                self.assertFalse(xait.source_enabled("social-" + platform_id))
        self.assertTrue(xait.source_enabled("hacker-news"), "core HN must not inherit social policy")
        self.assertTrue(xait.source_enabled("x-ai-signals"), "X signals are a direct observation source")
        self.assertFalse(xait.source_enabled("social-x"), "legacy social containers stay retired")

    def test_active_social_container_is_empty_and_missing_social_is_compatible(self):
        issue = legacy_issue()
        section = next(section for section in legacy_issue()["sections"] if section["kind"] == "social")
        self.assertEqual([], xait.active_social_section(section)["platforms"])
        self.assertEqual(xait.SOCIAL_OVERVIEW, xait.active_social_section(section)["overview"])
        issue["sections"] = [item for item in issue["sections"] if item["kind"] != "social"]
        xait.validate_issue(issue)
        self.assertEqual([], xait._social_compat(issue)["platforms"])
        self.assertEqual(xait.SOCIAL_OVERVIEW, xait._social_compat(issue)["rankingPolicy"])
        duplicate = copy.deepcopy(section)
        duplicate["id"] = section["id"] + "-duplicate"
        issue["sections"].extend((section, duplicate))
        with self.assertRaises(xait.XaitError):
            xait.validate_issue(issue)
        schema = json.loads((ROOT / "content" / "schema" / "issue-v1.schema.json").read_text(encoding="utf-8"))
        self.assertNotIn("minItems", schema["$defs"]["socialSection"]["properties"]["platforms"])

    def test_active_issue_filters_and_caps_without_mutating_canonical_input(self):
        issue = latest_v2_issue()
        original = copy.deepcopy(issue)
        active = xait.active_issue(issue)
        self.assertEqual(original, issue)
        self.assertEqual(active, xait.active_issue(active))
        section_ids = {section["id"] for section in active["sections"]}
        for section_id in xait.RETIRED_DIRECT_SOURCE_IDS | xait.HIDDEN_SECTION_IDS:
            self.assertNotIn(section_id, section_ids)
        self.assertFalse(any(section["kind"] == "social" for section in active["sections"]))
        self.assertIn("aihot", {source["id"] for source in active["sources"]},
                      "AIHot status remains an observation signal")
        self.assertIn("hacker-news", {source["id"] for source in active["sources"]})
        self.assertIn("github-trending", {source["id"] for source in active["sources"]})
        self.assertTrue(all(xait.source_enabled(source["id"]) for source in active["sources"]))
        self.assertTrue(all(xait.source_enabled(article["sourceId"]) for article in active["articles"]))
        wechat = next(section for section in active["sections"] if section["kind"] == "wechat")
        self.assertTrue(all(
            item["badge"] == "今日" and item["meta"].startswith(active["date"])
            for account in wechat["accounts"] for item in account["items"]
        ))
        self.assertTrue(all(
            account["items"] or account["statusTone"] == "stale"
            or (account["status"] == "今日未检出新文章" and account["statusTone"] == "quiet")
            for account in wechat["accounts"]
        ))
        account_by_name = {account["name"]: account for account in wechat["accounts"]}
        for source in active["sources"]:
            if source["label"] in account_by_name:
                account = account_by_name[source["label"]]
                self.assertEqual(len(account["items"]), source["itemCount"])
                if not account["items"] and account["statusTone"] != "stale":
                    self.assertEqual("empty", source["status"])
        current_wechat_items = {
            (account["name"], item["title"], item.get("url", ""))
            for account in wechat["accounts"] for item in account["items"]
        }
        labels = {source["id"]: source["label"] for source in active["sources"]}
        self.assertTrue(all(
            (labels[article["sourceId"]], article["title"], article["url"]) in current_wechat_items
            for article in active["articles"] if article["sourceId"].startswith("wechat-")
        ))
        for section_id, (field, maximum) in xait.SECTION_DISPLAY_LIMITS.items():
            source_section = next((section for section in issue["sections"] if section["id"] == section_id), None)
            if source_section is None:
                continue
            active_section = next(section for section in active["sections"] if section["id"] == section_id)
            expected = source_section[field]
            if section_id == "techmeme":
                expected = [item for item in expected if xait.techmeme_item_is_ai(item)]
            self.assertEqual(expected[:maximum], active_section[field])
            self.assertLessEqual(len(active_section[field]), maximum)
        product = next(section for section in active["sections"] if section["id"] == "product-hunt")
        self.assertEqual(xait.PRODUCT_HUNT_TITLE, product["title"])
        product_source = next(source for source in active["sources"] if source["id"] == "product-hunt")
        self.assertEqual(xait.PRODUCT_HUNT_TITLE, product_source["label"])

    def test_x_signals_are_capped_wide_and_observation_only(self):
        issue = with_x_signals(count=12)
        original = copy.deepcopy(issue)
        xait.validate_issue(issue)
        active = xait.active_issue(issue)
        self.assertEqual(original, issue)
        section = next(section for section in active["sections"] if section["id"] == xait.X_SIGNAL_SOURCE_ID)
        source = next(source for source in active["sources"] if source["id"] == xait.X_SIGNAL_SOURCE_ID)
        self.assertEqual(10, len(section["items"]))
        self.assertEqual(10, source["itemCount"])
        self.assertFalse(any(article["sourceId"] == xait.X_SIGNAL_SOURCE_ID for article in active["articles"]))
        before = xait.select_today(latest_v2_issue())
        self.assertEqual(before, xait.select_today(issue))

        rendered = xait._render_sections(issue)
        self.assertIn('id="module-frontline-signals"', rendered)
        self.assertIn('id="x-ai-signals"', rendered)
        self.assertIn('class="module-source section-links module-source-wide"', rendered)
        self.assertIn('class="x-signal-disclaimer"', rendered)
        self.assertIn(xait.X_SIGNAL_DISCLAIMER, rendered)
        self.assertEqual(10, rendered.count("https://x.com/i/status/"))
        self.assertNotIn('id="social-x"', rendered)

        with tempfile.TemporaryDirectory(prefix="xait-x-signals-") as temporary:
            destination = Path(temporary)
            xait.build_site(destination, [issue])
            xait.validate_built_site(destination, [issue])
            published = json.loads((destination / "issues" / (issue["date"] + ".json")).read_text(encoding="utf-8"))
            published_section = next(section for section in published["sections"] if section["id"] == xait.X_SIGNAL_SOURCE_ID)
            self.assertEqual(10, len(published_section["items"]))
            self.assertTrue(all(set(item) == {"title", "url", "meta"} for item in published_section["items"]))
            page = (destination / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="module-frontline-signals"', page)
            self.assertIn(xait.X_SIGNAL_DISCLAIMER, page)

    def test_x_partial_renders_and_failure_status_hides_body(self):
        partial = with_x_signals(status="partial", count=2)
        xait.validate_issue(partial)
        rendered = xait._render_sections(partial)
        self.assertIn("部分可用", rendered)
        self.assertIn('id="x-ai-signals"', rendered)

        for status in ("empty", "unavailable", "not_run"):
            with self.subTest(status=status):
                issue = with_x_signals(status=status, count=0)
                xait.validate_issue(issue)
                active = xait.active_issue(issue)
                self.assertIn(xait.X_SIGNAL_SOURCE_ID, {source["id"] for source in active["sources"]})
                self.assertNotIn(xait.X_SIGNAL_SOURCE_ID, {section["id"] for section in active["sections"]})
                rendered = xait._render_sections(issue)
                self.assertNotIn('id="x-ai-signals"', rendered)
                self.assertIn(xait.X_SIGNAL_TITLE, rendered)

    def test_x_public_contract_rejects_raw_content_identity_and_metrics(self):
        base = with_x_signals(count=1)
        mutations = (
            ("raw post text", lambda issue: issue["sections"][-1]["items"][0].update(title="OpenAI announces a new model")),
            ("handle and metrics", lambda issue: issue["sections"][-1]["items"][0].update(meta="@alice · 12,000 likes")),
            ("author URL", lambda issue: issue["sections"][-1]["items"][0].update(url="https://x.com/alice/status/1000000000000000000")),
            ("query URL", lambda issue: issue["sections"][-1]["items"][0].update(url="https://x.com/i/status/1000000000000000000?ref=home")),
            ("leading-zero ID", lambda issue: issue["sections"][-1]["items"][0].update(url="https://x.com/i/status/0123456789012345678")),
            ("oversized ID", lambda issue: issue["sections"][-1]["items"][0].update(url="https://x.com/i/status/123456789012345678901")),
            ("raw metric field", lambda issue: issue["sections"][-1]["items"][0].update(likes=12000)),
            ("free-form status", lambda issue: issue["sources"][-1].update(message="@alice post collected with 12000 likes")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                issue = copy.deepcopy(base)
                mutate(issue)
                with self.assertRaises(xait.XaitError):
                    xait.validate_issue(issue)

        article_issue = copy.deepcopy(base)
        fixture = copy.deepcopy(article_issue["articles"][0])
        fixture.update(id="x-observation-must-not-be-an-article", sourceId=xait.X_SIGNAL_SOURCE_ID)
        article_issue["articles"].append(fixture)
        with self.assertRaises(xait.XaitError):
            xait.validate_issue(article_issue)

    def test_x_schema_declares_partial_without_changing_v1(self):
        schema = json.loads((ROOT / "content" / "schema" / "issue-v2.schema.json").read_text(encoding="utf-8"))
        self.assertIn("partial", schema["$defs"]["source"]["properties"]["status"]["enum"])
        v1 = json.loads((ROOT / "content" / "schema" / "issue-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(1, v1["properties"]["schemaVersion"]["const"])

    def test_unavailable_source_is_hidden_but_has_one_collection_status(self):
        issue = latest_v2_issue()
        source = next(source for source in issue["sources"] if source["id"] == "hacker-news")
        source.update(status="unavailable", itemCount=0, message="temporarily unavailable")
        rendered = xait._render_sections(issue)
        self.assertNotIn('id="hacker-news"', rendered)
        self.assertIn(source["label"], rendered)
        self.assertEqual(1, rendered.count('id="collection-status"'))

    def test_techmeme_filters_ai_metadata_before_cap_and_hides_empty_body(self):
        issue = latest_v2_issue()
        section = next(section for section in issue["sections"] if section["id"] == "techmeme")
        source = next(source for source in issue["sources"] if source["id"] == "techmeme")
        non_ai = [
            {"title": "New laptop and phone accessories", "meta": "Consumer hardware", "url": "https://example.org/hardware"},
            {"title": "Streaming service changes its prices", "meta": "Media business", "url": "https://example.org/streaming"},
        ]
        ai = [
            {"title": "发布新一代人工智能模型", "meta": "公开报道", "url": "https://example.org/report/0"},
            {"title": "A new developer tool", "meta": "Machine learning platform", "url": "https://example.org/report/1"},
        ] + [
            {"title": "OpenAI releases model {0}".format(index), "meta": "Public report", "url": "https://example.org/ai/{0}".format(index)}
            for index in range(4)
        ]
        section["items"] = non_ai + ai
        source.update(status="ok", itemCount=len(section["items"]), message="collected")
        active = xait.active_issue(issue)
        active_section = next(item for item in active["sections"] if item["id"] == "techmeme")
        self.assertEqual(ai[:5], active_section["items"])
        self.assertFalse(any(item in active_section["items"] for item in non_ai))
        self.assertEqual(5, next(item for item in active["sources"] if item["id"] == "techmeme")["itemCount"])

        section["items"] = non_ai
        source.update(status="ok", itemCount=len(non_ai), message="collected")
        active = xait.active_issue(issue)
        active_source = next(item for item in active["sources"] if item["id"] == "techmeme")
        self.assertEqual("empty", active_source["status"])
        self.assertEqual(0, active_source["itemCount"])
        rendered = xait._render_sections(issue)
        self.assertNotIn('id="techmeme"', rendered)
        self.assertIn(active_source["label"], rendered)

    def test_ordinary_platform_news_is_preserved(self):
        issue = legacy_issue()
        article_section = next(section for section in issue["sections"]
                               if section["kind"] == "links" and xait.section_enabled(section["id"]))
        article_section["items"].insert(0, {"title": "小红书发布 AI 开源模型，抖音介绍新产品", "url": "https://example.org/ai-news"})
        active = xait.active_issue(issue)
        active_section = next(section for section in active["sections"] if section["id"] == article_section["id"])
        self.assertEqual(article_section["items"][0], active_section["items"][0])
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
                for source_id in xait.RETIRED_DIRECT_SOURCE_IDS | xait.HIDDEN_SECTION_IDS:
                    self.assertNotIn('id="' + source_id + '"', archive)
                compat = json.loads((destination / ("social-research-" + issue["date"] + ".json")).read_text(encoding="utf-8"))
                self.assertEqual([], compat["platforms"])
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
