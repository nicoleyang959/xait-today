"""Official Product Hunt rankings retain rank/date evidence without article promotion."""

from __future__ import annotations

import copy
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xait_ph_ranking", ROOT / "xait.py")
xait = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(xait)


def ranking_issue(status="ok", count=10):
    paths = sorted((ROOT / "content" / "issues").glob("*.json"))
    issue = next(value for value in (
        json.loads(path.read_text(encoding="utf-8")) for path in reversed(paths)
    ) if value["schemaVersion"] == 2)
    # The source fixture is independent of whether a later real edition already
    # includes a ranking. Never alter canonical issue files during tests.
    issue["sections"] = [section for section in issue["sections"] if section["id"] != xait.PRODUCT_HUNT_RANKING_ID]
    issue["sources"] = [source for source in issue["sources"] if source["id"] != xait.PRODUCT_HUNT_RANKING_ID]
    issue["sources"].append({
        "id": xait.PRODUCT_HUNT_RANKING_ID, "label": xait.PRODUCT_HUNT_RANKING_TITLE,
        "status": status, "checkedAt": issue["generatedAt"],
        "lastSuccessAt": issue["generatedAt"] if status in {"ok", "partial"} else None,
        "itemCount": count if status in {"ok", "partial"} else 0,
        "message": "公开日榜元数据；保留官方名次" if status in {"ok", "partial"} else "来源暂不可用",
    })
    if status in {"ok", "partial"}:
        ranking_date = (date.fromisoformat(issue["date"]) - timedelta(days=2)).isoformat()
        issue["sections"].append({
            "kind": "links", "id": xait.PRODUCT_HUNT_RANKING_ID,
            "title": xait.PRODUCT_HUNT_RANKING_TITLE,
            "ranking": {
                "date": ranking_date, "timezone": "America/Los_Angeles",
                "url": "https://www.producthunt.com/leaderboard/daily/" + ranking_date.replace("-", "/"),
                "capturedAt": issue["generatedAt"], "scope": "featured",
            },
            "items": [{
                "rank": index + 1, "title": "Example product {0}".format(index + 1),
                "description": "Source tagline & product information",
                "url": "https://www.producthunt.com/products/example-{0}".format(index + 1),
                "points": 1200 - index,
            } for index in range(count)],
        })
    return issue


class ProductHuntRankingTests(unittest.TestCase):
    def test_valid_rankings_coexist_with_recent_launches_without_article_promotion(self):
        issue = ranking_issue()
        before = copy.deepcopy(issue)
        xait.validate_issue(issue)
        active = xait.active_issue(issue)
        self.assertEqual(before, issue)
        self.assertEqual(active, xait.active_issue(active))
        ranking = next(section for section in active["sections"] if section["id"] == xait.PRODUCT_HUNT_RANKING_ID)
        source = next(source for source in active["sources"] if source["id"] == xait.PRODUCT_HUNT_RANKING_ID)
        self.assertEqual(10, len(ranking["items"]))
        self.assertEqual(10, source["itemCount"])
        self.assertIn("product-hunt", {section["id"] for section in active["sections"]})
        self.assertFalse(any(article["sourceId"] == xait.PRODUCT_HUNT_RANKING_ID for article in active["articles"]))
        without_ranking = copy.deepcopy(issue)
        without_ranking["sources"].pop()
        without_ranking["sections"].pop()
        self.assertEqual(xait.select_today(without_ranking), xait.select_today(issue))

    def test_rank_date_identity_and_source_contract_are_strict(self):
        mutations = (
            lambda issue: issue["sections"][-1]["items"][0].update(rank=2),
            lambda issue: issue["sections"][-1]["items"][1].update(rank=1),
            lambda issue: issue["sections"][-1]["items"][1].update(url=issue["sections"][-1]["items"][0]["url"]),
            lambda issue: issue["sections"][-1]["items"][0].update(points=True),
            lambda issue: issue["sections"][-1]["items"][0].update(points=-1),
            lambda issue: issue["sections"][-1]["items"][0].update(author="unnecessary private identity"),
            lambda issue: issue["sections"][-1]["ranking"].update(date="2026-02-30"),
            lambda issue: issue["sections"][-1]["ranking"].update(timezone="UTC"),
            lambda issue: issue["sections"][-1]["ranking"].update(scope="all"),
            lambda issue: issue["sections"][-1]["ranking"].update(capturedAt="2026-09-01T08:45:00"),
            lambda issue: issue["sections"][-1]["ranking"].update(capturedAt="2026-09-01T08:45:00+08:00"),
            lambda issue: issue["sources"][-1].update(itemCount=9),
            lambda issue: issue["sources"][-1].update(status="stale"),
            lambda issue: issue["sources"].pop(),
        )
        for mutation in mutations:
            issue = ranking_issue()
            mutation(issue)
            with self.subTest(mutation=mutation), self.assertRaises(xait.XaitError):
                xait.validate_issue(issue)
        for count in (0, 11):
            with self.subTest(count=count), self.assertRaises(xait.XaitError):
                xait.validate_issue(ranking_issue(count=count))

    def test_untrusted_urls_and_ranking_dates_cannot_masquerade_as_article_dates(self):
        for url in ("https://example.com/products/example", "https://www.producthunt.com.evil.example/products/example",
                    "http://www.producthunt.com/products/example", "https://www.producthunt.com/products/example?token=bad",
                    "https://www.producthunt.com/leaderboard/daily/2026/10/15", "javascript:alert(1)"):
            issue = ranking_issue()
            issue["sections"][-1]["items"][0]["url"] = url
            with self.subTest(url=url), self.assertRaises(xait.XaitError):
                xait.validate_issue(issue)
        issue = ranking_issue()
        issue["sections"][-1]["ranking"]["url"] = "https://example.com/leaderboard/daily/2026/10/15"
        with self.assertRaises(xait.XaitError):
            xait.validate_issue(issue)
        issue = ranking_issue()
        issue["sections"][-1]["ranking"]["url"] = "https://www.producthunt.com/leaderboard/daily/2000/01/01"
        with self.assertRaises(xait.XaitError):
            xait.validate_issue(issue)
        issue = ranking_issue()
        stale_day = (date.fromisoformat(issue["date"]) - timedelta(days=3)).isoformat()
        issue["sections"][-1]["ranking"].update(
            date=stale_day,
            url="https://www.producthunt.com/leaderboard/daily/" + stale_day.replace("-", "/"))
        with self.assertRaises(xait.XaitError):
            xait.validate_issue(issue)
        issue = ranking_issue()
        article = copy.deepcopy(issue["articles"][0])
        article.update(id="rank-is-not-news", sourceId=xait.PRODUCT_HUNT_RANKING_ID)
        issue["articles"].append(article)
        with self.assertRaises(xait.XaitError):
            xait.validate_issue(issue)
        self.assertFalse(xait._brief_source_allowed(article))

    def test_missing_product_url_and_points_render_without_guessing_links(self):
        issue = ranking_issue(count=2)
        first = issue["sections"][-1]["items"][0]
        del first["url"]
        del first["points"]
        first["title"] = "Research & Design"
        xait.validate_issue(issue)
        rendered = xait._render_sections(issue)
        self.assertIn('id="module-products-opensource"', rendered)
        self.assertIn('class="module-source section-links module-source-wide" id="product-hunt-ranking"', rendered)
        self.assertIn("Research &amp; Design", rendered)
        self.assertIn("Source tagline &amp; product information", rendered)
        self.assertIn("查看官方日榜", rendered)
        self.assertIn(xait.PRODUCT_HUNT_RANKING_NOTE, rendered)
        self.assertNotIn('/products/research', rendered)
        self.assertEqual(1, rendered.count('class="ph-ranking-points"'))
        self.assertEqual(2, rendered.count('class="ph-ranking-item"'))
        self.assertIn('target="_blank" rel="noopener noreferrer"', rendered)

    def test_manual_review_is_visible_and_product_names_are_not_translated(self):
        issue = ranking_issue(count=2)
        section = issue["sections"][-1]
        section["ranking"]["captureMethod"] = "manual-review"
        xait.validate_issue(issue)
        rendered = xait._render_product_hunt_ranking(section)
        self.assertIn("人工核验于：", rendered)
        self.assertIn('class="ph-ranking-name" data-no-i18n', rendered)
        self.assertNotIn("截至采集时间：", rendered)
        section["ranking"]["captureMethod"] = "unverified"
        with self.assertRaises(xait.XaitError):
            xait.validate_issue(issue)

    def test_empty_unavailable_and_not_run_keep_only_source_status(self):
        for status in ("empty", "unavailable", "not_run"):
            issue = ranking_issue(status=status)
            xait.validate_issue(issue)
            rendered = xait._render_sections(issue)
            self.assertIn(xait.PRODUCT_HUNT_RANKING_TITLE, rendered)
            self.assertNotIn('id="product-hunt-ranking"', rendered)
        partial = ranking_issue(status="partial", count=3)
        xait.validate_issue(partial)
        self.assertEqual(3, xait._render_sections(partial).count('class="ph-ranking-item"'))

    def test_ranking_build_is_deterministic_private_free_and_bilingual(self):
        issue = ranking_issue(count=2)
        xait.validate_issue(issue)
        with tempfile.TemporaryDirectory(prefix="xait-ranking-test-") as temporary:
            left, right = Path(temporary) / "a", Path(temporary) / "b"
            xait.build_site(left, [issue])
            xait.build_site(right, [issue])
            self.assertEqual([], xait._directory_diff(left, right))
            xait.validate_built_site(left, [issue])
            public = json.loads((left / "issues" / (issue["date"] + ".json")).read_text(encoding="utf-8"))
            ranking = next(section for section in public["sections"] if section["id"] == xait.PRODUCT_HUNT_RANKING_ID)
            self.assertEqual({"date", "timezone", "url", "capturedAt", "scope"}, set(ranking["ranking"]))
            self.assertTrue(all(set(item) == {"rank", "title", "description", "url", "points"} for item in ranking["items"]))
            page = (left / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("publishedAt", xait._render_product_hunt_ranking(ranking))
            self.assertIn("Top 10 products", page)
            self.assertIn("Points", page)
            self.assertIn('class="ph-ranking-description"', page)
            self.assertEqual(7, page.count('data-theme="theme-'))
            javascript = (left / "assets" / "app.js").read_text(encoding="utf-8")
            self.assertIn(".ph-ranking-item", javascript)
            self.assertIn(".ph-ranking-meta", javascript)
            css = (left / "assets" / "app.css").read_text(encoding="utf-8")
            self.assertIn("minmax(0, 1fr)", css)
            self.assertIn(".ph-ranking-points { grid-column: 2; }", css)


if __name__ == "__main__":
    unittest.main()
