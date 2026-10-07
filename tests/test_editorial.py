"""Evidence-based briefing, conservative duplicate pairs, and publication safety."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xait_editorial", ROOT / "xait.py")
xait = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(xait)


def legacy_issue():
    for path in sorted((ROOT / "content" / "issues").glob("*.json")):
        issue = json.loads(path.read_text(encoding="utf-8"))
        if issue["schemaVersion"] == 1:
            return issue
    raise AssertionError("Keep at least one real v1 archive for compatibility tests")


def source(source_id="source-a", status="ok"):
    return {"id": source_id, "label": source_id, "status": status,
            "checkedAt": "2026-10-07T08:44:00+08:00", "lastSuccessAt": None,
            "itemCount": 1, "message": ""}


def article(article_id="article-a", source_id="source-a", **overrides):
    result = {"id": article_id, "sourceId": source_id, "title": "AI model release",
              "url": "https://example.org/news/" + article_id,
              "publishedAt": "2026-10-06T12:00:00+08:00", "dateEvidence": "exact",
              "collectedAt": "2026-10-07T08:44:00+08:00", "category": "models"}
    result.update(overrides)
    return result


def editorial_issue():
    issue = copy.deepcopy(legacy_issue())
    issue.update(schemaVersion=2, date="2026-10-07", generatedAt="2026-10-07T08:45:00+08:00",
                 edition={"windowStart": "2026-10-06T08:45:00+08:00", "windowEnd": "2026-10-07T08:45:00+08:00"},
                 sources=[source()], articles=[article()])
    for section in issue["sections"]:
        if section["kind"] == "wechat":
            for account in section["accounts"]:
                account["statusTone"] = "stale"
                for item in account["items"]:
                    item["badge"] = "最近"
    return issue


# Each case names the actual evidence distinction; no title similarity threshold.
# Arguments are (label, should_merge, left overrides, right overrides).
DUPLICATE_PAIRS = [
    ("same_url_changed_title", True, {"url": "https://example.org/a", "title": "AI launch"}, {"url": "https://example.org/a", "title": "Correction to AI launch"}),
    ("same_url_distinct_publishers", True, {"url": "https://example.org/a"}, {"url": "https://example.org/a"}),
    ("hostname_case", True, {"url": "https://EXAMPLE.org/a"}, {"url": "https://example.org/a"}),
    ("default_https_port", True, {"url": "https://example.org:443/a"}, {"url": "https://example.org/a"}),
    ("default_http_port", True, {"url": "http://example.org:80/a"}, {"url": "http://example.org/a"}),
    ("dns_final_dot", True, {"url": "https://example.org./a"}, {"url": "https://example.org/a"}),
    ("campaign_source", True, {"url": "https://example.org/a?utm_source=news"}, {"url": "https://example.org/a"}),
    ("campaign_fields_around_semantic", True, {"url": "https://example.org/a?utm_medium=rss&id=42&utm_campaign=morning"}, {"url": "https://example.org/a?id=42"}),
    ("campaign_key_case", True, {"url": "https://example.org/a?UTM_CONTENT=tile"}, {"url": "https://example.org/a"}),
    ("encoded_campaign_key", True, {"url": "https://example.org/a?%75tm_term=llm"}, {"url": "https://example.org/a"}),
    ("facebook_click_marker", True, {"url": "https://example.org/a?fbclid=abc"}, {"url": "https://example.org/a"}),
    ("google_click_marker", True, {"url": "https://example.org/a?gclid=abc"}, {"url": "https://example.org/a"}),
    ("microsoft_click_marker", True, {"url": "https://example.org/a?msclkid=abc"}, {"url": "https://example.org/a"}),
    ("mailchimp_markers", True, {"url": "https://example.org/a?mc_cid=ab&mc_eid=cd"}, {"url": "https://example.org/a"}),
    ("tracking_preserves_equal_anchor", True, {"url": "https://example.org/a?utm_id=one#details"}, {"url": "https://example.org/a#details"}),
    ("two_reposts_same_original", True, {"originalUrl": "https://primary.org/ai"}, {"originalUrl": "https://primary.org/ai"}),
    ("primary_and_attributed_repost", True, {"url": "https://primary.org/ai"}, {"originalUrl": "https://primary.org/ai"}),
    ("reverse_primary_attribution", True, {"originalUrl": "https://primary.org/ai"}, {"url": "https://primary.org/ai"}),
    ("original_tracking_variation", True, {"originalUrl": "https://primary.org/ai?utm_source=wire"}, {"originalUrl": "https://primary.org/ai"}),
    ("original_host_case", True, {"originalUrl": "https://PRIMARY.org/ai"}, {"url": "https://primary.org/ai"}),
    ("explicit_event_key", True, {"eventKey": "release-2026"}, {"eventKey": "release-2026"}),
    ("event_key_overrides_different_title", True, {"eventKey": "model-2", "title": "AI launch"}, {"eventKey": "model-2", "title": "Model 2 technical report"}),
    ("shared_url_different_event_keys", True, {"url": "https://example.org/a", "eventKey": "a"}, {"url": "https://example.org/a", "eventKey": "b"}),
    ("same_encoded_path", True, {"url": "https://example.org/%E4%B8%AD"}, {"url": "https://example.org/%E4%B8%AD"}),
    ("same_semantic_query_sequence", True, {"url": "https://example.org/a?id=2&id=3"}, {"url": "https://example.org/a?id=2&id=3"}),
    ("same_title_distinct_urls", False, {"title": "AI launch"}, {"title": "AI launch"}),
    ("similar_title_word_order", False, {"title": "OpenAI launches new model"}, {"title": "New OpenAI model launches"}),
    ("title_punctuation_only", False, {"title": "AI: new model!"}, {"title": "AI new model"}),
    ("title_case_only", False, {"title": "AI MODEL RELEASE"}, {"title": "ai model release"}),
    ("title_translated", False, {"title": "OpenAI 发布新模型"}, {"title": "OpenAI releases a new model"}),
    ("different_model_versions", False, {"title": "Model AI 2.0 launch"}, {"title": "Model AI 2.1 launch"}),
    ("same_model_different_actions", False, {"title": "AI model launches"}, {"title": "AI model price cut"}),
    ("same_headline_different_year", False, {"title": "AI yearly report 2025"}, {"title": "AI yearly report 2026"}),
    ("path_case_is_significant", False, {"url": "https://example.org/AI"}, {"url": "https://example.org/ai"}),
    ("trailing_slash_is_significant", False, {"url": "https://example.org/ai"}, {"url": "https://example.org/ai/"}),
    ("http_https_not_assumed_redirect", False, {"url": "http://example.org/ai"}, {"url": "https://example.org/ai"}),
    ("www_not_assumed_alias", False, {"url": "https://www.example.org/ai"}, {"url": "https://example.org/ai"}),
    ("non_default_port", False, {"url": "https://example.org:8443/ai"}, {"url": "https://example.org/ai"}),
    ("semantic_article_id", False, {"url": "https://example.org/a?id=1"}, {"url": "https://example.org/a?id=2"}),
    ("semantic_page_number", False, {"url": "https://example.org/a?page=1"}, {"url": "https://example.org/a?page=2"}),
    ("semantic_language", False, {"url": "https://example.org/a?lang=en"}, {"url": "https://example.org/a?lang=zh"}),
    ("semantic_version", False, {"url": "https://example.org/a?v=1"}, {"url": "https://example.org/a?v=2"}),
    ("ref_not_assumed_tracking", False, {"url": "https://example.org/a?ref=one"}, {"url": "https://example.org/a"}),
    ("source_not_assumed_tracking", False, {"url": "https://example.org/a?source=one"}, {"url": "https://example.org/a"}),
    ("unknown_utm_not_stripped", False, {"url": "https://example.org/a?utm_custom=id"}, {"url": "https://example.org/a"}),
    ("different_anchor", False, {"url": "https://example.org/a#one"}, {"url": "https://example.org/a#two"}),
    ("anchor_missing", False, {"url": "https://example.org/a#one"}, {"url": "https://example.org/a"}),
    ("tracking_cannot_hide_anchor", False, {"url": "https://example.org/a?utm_source=rss#one"}, {"url": "https://example.org/a#two"}),
    ("query_order_preserved", False, {"url": "https://example.org/a?x=1&y=2"}, {"url": "https://example.org/a?y=2&x=1"}),
    ("repeated_query_order", False, {"url": "https://example.org/a?id=1&id=2"}, {"url": "https://example.org/a?id=2&id=1"}),
    ("blank_query_value_significant", False, {"url": "https://example.org/a?id="}, {"url": "https://example.org/a"}),
    ("encoded_path_not_decoded", False, {"url": "https://example.org/%61"}, {"url": "https://example.org/a"}),
    ("encoded_slash_not_decoded", False, {"url": "https://example.org/a%2Fb"}, {"url": "https://example.org/a/b"}),
    ("different_original_urls", False, {"originalUrl": "https://primary.org/one"}, {"originalUrl": "https://primary.org/two"}),
    ("different_original_anchors", False, {"originalUrl": "https://primary.org/a#one"}, {"originalUrl": "https://primary.org/a#two"}),
    ("event_key_case_significant", False, {"eventKey": "AI-one"}, {"eventKey": "ai-one"}),
    ("event_key_whitespace_significant", False, {"eventKey": "ai-one"}, {"eventKey": "ai-one "}),
    ("different_event_keys", False, {"eventKey": "ai-one"}, {"eventKey": "ai-two"}),
    ("one_sided_event_key_not_title_evidence", False, {"eventKey": "launch"}, {}),
    ("event_key_url_namespace_separate", False, {"eventKey": "https://primary.org/a"}, {"url": "https://primary.org/a"}),
]


class DuplicatePairTests(unittest.TestCase):
    def test_dataset_has_at_least_fifty_labeled_pairs(self):
        self.assertGreaterEqual(len(DUPLICATE_PAIRS), 50)
        self.assertEqual(len(DUPLICATE_PAIRS), len({row[0] for row in DUPLICATE_PAIRS}))

    def test_original_chain_is_transitive_and_order_independent(self):
        articles = [article("a", "source-z", url="https://primary.org/a"),
                    article("b", "source-b", originalUrl="https://primary.org/a"),
                    article("c", "source-c", originalUrl="https://example.org/news/b")]
        groups = xait.group_articles(articles)
        self.assertEqual(1, len(groups))
        self.assertEqual("a", groups[0]["representative"]["id"])
        self.assertEqual(2, len(groups[0]["relatedLinks"]))
        self.assertEqual(groups, xait.group_articles(list(reversed(articles))))


def install_pair_tests():
    for label, expected, left, right in DUPLICATE_PAIRS:
        def test(self, expected=expected, left=left, right=right):
            a = article("left", "source-a", **left)
            b = article("right", "source-b", **right)
            groups = xait.group_articles([a, b])
            self.assertEqual(1 if expected else 2, len(groups))
            self.assertEqual(groups, xait.group_articles([b, a]))
        setattr(DuplicatePairTests, "test_pair_" + label, test)


install_pair_tests()


class SchemaAndSelectionTests(unittest.TestCase):
    def test_v1_is_not_promoted_and_has_no_editorial_markup(self):
        issue = legacy_issue()
        self.assertIs(issue, xait.validate_issue(issue))
        self.assertEqual([], xait.select_today(issue))
        self.assertEqual("", xait.render_editorial(issue))
        self.assertNotIn('id="today-brief"', xait._render_sections(issue))
        issue["articles"] = []
        with self.assertRaises(xait.XaitError):
            xait.validate_issue(issue)

    def test_v2_validates_and_preserves_unknown_date(self):
        issue = editorial_issue()
        issue["articles"] += [article("day", publishedAt="2026-10-06", dateEvidence="day"),
                              article("unknown", publishedAt=None, dateEvidence="unknown")]
        before = copy.deepcopy(issue)
        xait.validate_issue(issue)
        self.assertEqual(1, len(xait.select_today(issue)))
        self.assertEqual(before, issue)

    def test_strict_unknown_fields_and_missing_fields_at_every_level(self):
        for level in ("root", "edition", "source", "article"):
            for mutation in ("extra", "missing"):
                with self.subTest(level=level, mutation=mutation):
                    issue = editorial_issue()
                    target = {"root": issue, "edition": issue["edition"], "source": issue["sources"][0], "article": issue["articles"][0]}[level]
                    if mutation == "extra":
                        target["unrecognized"] = "value"
                    else:
                        target.pop(next(iter(target)))
                    with self.assertRaises(xait.XaitError):
                        xait.validate_issue(issue)

    def test_version_is_an_exact_integer(self):
        for version in (True, False, 1.0, 2.0, "2", None, 0, 3):
            with self.subTest(version=version):
                issue = editorial_issue()
                issue["schemaVersion"] = version
                with self.assertRaises(xait.XaitError):
                    xait.validate_issue(issue)

    def test_source_and_article_identity_constraints(self):
        for mode in ("duplicate-source", "duplicate-article", "missing-source", "bool-count", "negative-count", "bad-status", "bad-category", "reserved-id"):
            with self.subTest(mode=mode):
                issue = editorial_issue()
                if mode == "duplicate-source": issue["sources"].append(copy.deepcopy(issue["sources"][0]))
                elif mode == "duplicate-article": issue["articles"].append(copy.deepcopy(issue["articles"][0]))
                elif mode == "missing-source": issue["articles"][0]["sourceId"] = "missing"
                elif mode == "bool-count": issue["sources"][0]["itemCount"] = True
                elif mode == "negative-count": issue["sources"][0]["itemCount"] = -1
                elif mode == "bad-status": issue["sources"][0]["status"] = "fresh"
                elif mode == "bad-category": issue["articles"][0]["category"] = "business"
                else: issue["sections"][0]["id"] = "today-brief"
                with self.assertRaises(xait.XaitError): xait.validate_issue(issue)

    def test_strict_evidence_types(self):
        for evidence, published in (("exact", None), ("exact", "2026-10-06"), ("exact", "2026-10-06 12:00:00+08:00"),
                                    ("exact", "2026-10-06T12:00:00"), ("exact", "2026-10-06T12:00:00+0800"),
                                    ("exact", "2026-02-30T12:00:00+08:00"), ("day", "2026-10-06T00:00:00+08:00"),
                                    ("day", None), ("unknown", "2026-10-06"), ("guess", None)):
            with self.subTest(evidence=evidence, published=published):
                issue = editorial_issue()
                issue["articles"][0].update(dateEvidence=evidence, publishedAt=published)
                with self.assertRaises(xait.XaitError): xait.validate_issue(issue)

    def test_edition_timezone_and_fixed_boundaries(self):
        for field, value in (("windowStart", "2026-10-06T00:45:00Z"), ("windowEnd", "2026-10-07T00:45:00Z"),
                             ("windowStart", "2026-10-06T08:44:00+08:00"), ("windowEnd", "2026-10-07T08:45:01+08:00"),
                             ("windowEnd", "2026-10-08T08:45:00+08:00")):
            with self.subTest(field=field, value=value):
                issue = editorial_issue()
                issue["edition"][field] = value
                with self.assertRaises(xait.XaitError): xait.validate_issue(issue)

    def test_window_start_inclusive_end_exclusive_unknown_future_excluded(self):
        issue = editorial_issue()
        cases = [("start", "2026-10-06T08:45:00+08:00"), ("end", "2026-10-07T08:45:00+08:00"),
                 ("prior", "2026-10-06T08:44:59+08:00"), ("future", "2026-10-08T12:00:00+08:00"),
                 ("utc", "2026-10-07T00:44:59Z")]
        issue["articles"] = [article(name, publishedAt=time, collectedAt="2026-10-07T08:45:00+08:00") for name, time in cases]
        self.assertEqual(["utc", "start"], [group["representative"]["id"] for group in xait.select_today(issue)])

    def test_v2_generated_date_uses_cst_instead_of_lexical_date(self):
        issue = editorial_issue()
        issue["generatedAt"] = "2026-10-06T23:59:00Z"
        issue["sources"][0]["checkedAt"] = None
        issue["articles"][0]["collectedAt"] = "2026-10-06T23:58:00Z"
        xait.validate_issue(issue)
        issue["generatedAt"] = "2026-10-06T15:59:00Z"
        with self.assertRaises(xait.XaitError): xait.validate_issue(issue)

    def test_future_provenance_and_success_after_check_are_rejected(self):
        for field in ("checkedAt", "lastSuccessAt", "collectedAt", "last-after-check"):
            with self.subTest(field=field):
                issue = editorial_issue()
                if field == "collectedAt":
                    issue["articles"][0][field] = "2099-01-01T12:00:00Z"
                elif field == "last-after-check":
                    issue["sources"][0]["lastSuccessAt"] = "2026-10-07T08:44:01+08:00"
                else:
                    issue["sources"][0][field] = "2099-01-01T12:00:00Z"
                with self.assertRaises(xait.XaitError): xait.validate_issue(issue)

    def test_future_publication_is_preserved_but_never_selected(self):
        issue = editorial_issue()
        issue["articles"][0]["publishedAt"] = "2099-01-01T12:00:00Z"
        xait.validate_issue(issue)
        self.assertEqual([], xait.select_today(issue))
        issue["articles"][0]["publishedAt"] = "2026-10-07T08:44:30+08:00"
        self.assertEqual([], xait.select_today(issue), "publication after collection is not evidence for a pick")

    def test_hacker_news_feeds_share_one_source_cap(self):
        issue = editorial_issue()
        source_ids = ("hacker-news", "hacker-news-new", "hacker-news-show", "source-a")
        issue["sources"] = [source(name) for name in source_ids]
        issue["articles"] = [article("item-" + str(index), name) for index, name in enumerate(source_ids)]
        selected = xait.select_today(issue)
        ids = [group["representative"]["sourceId"] for group in selected]
        self.assertEqual(3, len(selected))
        self.assertEqual(2, sum(name.startswith("hacker-news") for name in ids))

    def test_caps_and_source_diversity_are_deterministic(self):
        issue = editorial_issue()
        issue["sources"] = [source("source-" + str(i)) for i in range(6)]
        issue["articles"] = [article("article-{0}-{1}".format(i, j), "source-" + str(i)) for i in range(6) for j in range(5)]
        selected = xait.select_today(issue)
        self.assertEqual(8, len(selected))
        ids = [group["representative"]["sourceId"] for group in selected]
        self.assertTrue(all(ids.count(source_id) <= 2 for source_id in ids))
        random.Random(17).shuffle(issue["articles"])
        issue["sources"].reverse()
        self.assertEqual(selected, xait.select_today(issue))

    def test_only_ai_and_ok_non_social_sources_selected(self):
        for source_id, status, title, url in (("source-a", "stale", "AI launch", "https://example.org/a"),
                                             ("source-a", "empty", "AI launch", "https://example.org/a"),
                                             ("source-a", "unavailable", "AI launch", "https://example.org/a"),
                                             ("source-a", "not_run", "AI launch", "https://example.org/a"),
                                             ("aihot", "ok", "AI launch", "https://example.org/a"),
                                             ("wechat-appso", "ok", "AI launch", "https://example.org/a"),
                                             ("social-x", "ok", "AI launch", "https://example.org/a"),
                                             ("source-a", "ok", "New phone battery", "https://example.org/a"),
                                             ("source-a", "ok", "AI launch", "https://mp.weixin.qq.com/s/abc")):
            with self.subTest(source_id=source_id, status=status, title=title, url=url):
                issue = editorial_issue()
                issue["sources"] = [source(source_id, status)]
                issue["articles"] = [article(source_id=source_id, title=title, url=url)]
                self.assertEqual([], xait.select_today(issue))

    def test_grouping_before_source_cap_does_not_charge_related_sources(self):
        issue = editorial_issue()
        issue["sources"] += [source("source-b")]
        issue["articles"] = [article("a"), article("b", "source-b", originalUrl="https://example.org/news/a"),
                             article("c"), article("d"), article("e", "source-b")]
        selected = xait.select_today(issue)
        self.assertEqual(3, len(selected))
        self.assertEqual("a", selected[0]["representative"]["id"])
        self.assertEqual(1, len(selected[0]["relatedLinks"]))

    def test_provided_summary_is_escaped_and_never_invented(self):
        issue = editorial_issue()
        issue["articles"][0]["summary"] = "A & B: quoted research claim"
        rendered = xait.render_editorial(issue)
        self.assertIn("A &amp; B: quoted research claim", rendered)
        self.assertIn("入选依据", rendered)
        issue["articles"][0].pop("summary")
        self.assertNotIn('class="brief-summary"', xait.render_editorial(issue))
        issue["articles"][0]["summary"] = "<script>alert(1)</script>"
        with self.assertRaises(xait.XaitError): xait.validate_issue(issue)

    def test_brief_times_and_categories_are_human_readable(self):
        issue = editorial_issue()
        issue["articles"][0]["publishedAt"] = "2026-10-06T04:00:00Z"
        rendered = xait.render_editorial(issue)
        self.assertIn('<time datetime="2026-10-06T04:00:00Z">10-06 12:00</time>（北京时间） · 模型', rendered)
        self.assertIn("2026-10-06 08:45 至 2026-10-07 08:45", rendered)
        self.assertEqual(1, rendered.count("来源收录时间不等同于原文首发时间"))

    def test_empty_brief_has_explicit_message_and_all_source_sections(self):
        issue = editorial_issue()
        issue["articles"] = []
        rendered = xait._render_sections(issue)
        self.assertIn('class="brief-empty"', rendered)
        self.assertNotIn('class="brief-event"', rendered)
        self.assertIn('id="source-reading"', rendered)
        self.assertIn('class="reading-nav"', rendered)
        for section in issue["sections"]:
            self.assertIn('href="#' + section["id"] + '"', rendered)
            self.assertIn('id="' + section["id"] + '"', rendered)

    def test_social_empty_origin_collapses_only_in_v2(self):
        section = next(s for s in editorial_issue()["sections"] if s["kind"] == "social")
        for platform in section["platforms"]:
            platform["status"] = "unavailable"
            platform["items"] = []
        self.assertNotIn("social-origin-details", xait._render_social(section))
        self.assertIn('<details class="social-origin-details">', xait._render_social(section, compact_empty=True))

    def test_source_statuses_have_labels_and_nulls_are_honest(self):
        issue = editorial_issue()
        issue["sources"] = [source("source-" + str(index), status) for index, status in enumerate(sorted(xait.SOURCE_STATUS))]
        issue["articles"] = []
        for record in issue["sources"]: record["checkedAt"] = None
        xait.validate_issue(issue)
        rendered = xait.render_editorial(issue)
        for label in ("成功", "无新增", "不可用", "沿用旧快照", "未运行", "未记录"):
            self.assertIn(label, rendered)
        self.assertIn('data-label="最近成功"', rendered)

    def test_schema_is_explicit_and_v1_remains_a_separate_contract(self):
        schema = json.loads((ROOT / "content" / "schema" / "issue-v2.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(2, schema["properties"]["schemaVersion"]["const"])
        self.assertEqual(set(editorial_issue()), set(schema["required"]))


class SensitiveScannerTests(unittest.TestCase):
    def test_literal_public_users_path_is_allowed_in_every_text_context(self):
        for text in ('https://example.org/users/alice', 'https://other.example/Users/alice?mode=public#bio',
                     'Profile https://example.org/users/alice is public.',
                     '<a href="https://example.org/users/alice">Alice</a>',
                     '{"url":"https:\\/\\/example.org\\/users\\/alice"}'):
            with self.subTest(text=text): xait._scan_sensitive_text(text, "fixture")

    def test_paths_remain_blocked_without_domain_exemptions(self):
        forbidden = ["/Users/alice/private", "/users/alice/private", "/home/alice/notes", "/private/var/db",
                     "/var/folders/cache", "/Volumes/Personal/data", "C:\\Users\\alice\\notes", "C:/Users/alice/notes",
                     "file:///Users/alice/notes", "%2FUsers%2Falice%2Fnotes", "%252FUsers%252Falice%252Fnotes",
                     r"\u002fUsers\u002falice", "https://example.org/%55sers/alice", "https://example.org/%2fUsers/alice",
                     r"https://example.org/\u0055sers/alice", "https://example.org/&#85;sers/alice", "https://example.org/users/alice?path=/Users/private",
                     "https://example.org/users/alice#path=/Users/private", "https://example.org/users/alice?path=%252FUsers%252Fprivate",
                     "https://example.org/users/alice and /Users/private", "https://example.org/users/alice#%2Fhome%2Falice"]
        for text in forbidden:
            with self.subTest(text=text):
                with self.assertRaises(xait.XaitError): xait._scan_sensitive_text(text, "fixture")

    def test_credentials_and_private_hosts_in_public_user_urls_are_not_masked(self):
        forbidden = ["https://example.org/users/alice?api_key=short", "https://example.org/users/alice#password=secret-value",
                     'https://example.org/users/alice and "api_key": "secret-value"',
                     "https://example.org/users/alice?%74oken=abc", "https://localhost/users/alice",
                     "https://router.internal/users/alice", "http://192.168.1.2/users/alice", "http://127.0.0.1/users/alice",
                     "http://[::1]/users/alice", "http://[fe80::1]/users/alice", "http://127.1/users/alice", "http://0177.0.0.1/users/alice", "https://user:pass@example.org/users/alice",
                     "https://example.org/users/alice and 10.0.0.1", "https://example.org/users/alice and file://private/data",
                     "https://example.org/users/alice?next=http%3A%2F%2F127.0.0.1%2Fprivate"]
        for text in forbidden:
            with self.subTest(text=text):
                with self.assertRaises(xait.XaitError): xait._scan_sensitive_text(text, "fixture")


if __name__ == "__main__":
    unittest.main()
