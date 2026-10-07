#!/usr/bin/env python3
"""Offline builder and local server for xAIT Today.

The public repository deliberately uses only the Python standard library.  This
module is both the command line entry point and an importable API for tests and
other agents.  It never performs collection or reads browser/account state.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import html
from html.parser import HTMLParser
import http.server
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import socketserver
import sys
import tempfile
from datetime import date as Date
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit
import uuid


ROOT = Path(__file__).resolve().parent
ISSUES_DIR = ROOT / "content" / "issues"
TEMPLATE_PATH = ROOT / "site" / "templates" / "page.html"
ASSETS_DIR = ROOT / "site" / "assets"
DOCS_DIR = ROOT / "docs"
PUBLIC_BASE_URL = "https://nicoleyang959.github.io/xait-today/"

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_DRIFT = 3
EXIT_BUILD = 4
EXIT_SERVE = 5
EXIT_SECURITY = 6

THEMES = {
    "theme-terminal",
    "theme-cyberpunk",
    "theme-swiss",
    "theme-editorial",
    "theme-consulting",
    "theme-minimal",
    "theme-paper",
}
SECTION_KINDS = {"blocks", "wechat", "social", "links", "table"}
WECHAT_ACCOUNTS = {"APPSO", "数字生命卡兹克", "智东西", "花叔"}
SOCIAL_STATUS = {"fresh", "stale", "unavailable"}
WECHAT_TONES = {"fresh", "quiet", "stale"}
SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "cookie",
    "key",
    "password",
    "secret",
    "session",
    "sessionid",
    "token",
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
HTML_TAG_RE = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")
MARKDOWN_BLOCK_RE = re.compile(r"(?m)^\s*(?:#{1,6}\s+|```|~~~|>\s+)")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]\n]+\]\(\s*(?:https?://|/)[^)]+\)")
RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
CST = timezone(timedelta(hours=8))
SOURCE_STATUS = {"ok", "empty", "unavailable", "stale", "not_run"}
ARTICLE_CATEGORIES = {"models", "products", "research", "tutorials", "industry", "opensource", "other"}
TRACKING_QUERY_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "utm_source_platform", "utm_creative_format", "utm_marketing_tactic",
    "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid",
}
AI_RE = re.compile(
    r"(?i)(?:\b(?:ai|llms?|gpt(?:-?\d[\w.-]*)?|chatgpt|openai|anthropic|claude|gemini|"
    r"deepseek|qwen|llama|mistral|copilot|chatbot|transformers?|diffusion|rag|"
    r"artificial intelligence|machine learning|deep learning|neural network|generative|agentic)\b|"
    r"人工智能|大模型|语言模型|智能体|机器学习|深度学习|生成式|神经网络|多模态|扩散模型)"
)


class XaitError(Exception):
    """Expected user-facing failure with a stable exit code."""

    def __init__(self, message: str, exit_code: int = EXIT_INPUT) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _duplicate_safe_object(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: {0}".format(key))
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    try:
        if path.is_symlink():
            raise XaitError("拒绝符号链接数据文件：{0}".format(path.name), EXIT_SECURITY)
        if path.stat().st_size > 12 * 1024 * 1024:
            raise XaitError("数据文件过大：{0}".format(path.name), EXIT_INPUT)
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_duplicate_safe_object)
    except XaitError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise XaitError("无法解析 {0}：{1}".format(path.name, exc), EXIT_INPUT) from exc


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _expect_object(value: Any, path: str, required: Set[str], optional: Set[str] = set()) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise XaitError("{0} 必须是对象".format(path))
    keys = set(value)
    missing = sorted(required - keys)
    unknown = sorted(keys - required - optional)
    if missing:
        raise XaitError("{0} 缺少字段：{1}".format(path, ", ".join(missing)))
    if unknown:
        raise XaitError("{0} 包含未知字段：{1}".format(path, ", ".join(unknown)))
    return value


def _expect_array(value: Any, path: str, minimum: int = 0, maximum: Optional[int] = None) -> List[Any]:
    if not isinstance(value, list):
        raise XaitError("{0} 必须是数组".format(path))
    if len(value) < minimum:
        raise XaitError("{0} 至少需要 {1} 项".format(path, minimum))
    if maximum is not None and len(value) > maximum:
        raise XaitError("{0} 最多允许 {1} 项".format(path, maximum))
    return value


def _expect_string(value: Any, path: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise XaitError("{0} 必须是字符串".format(path))
    if not allow_empty and not value.strip():
        raise XaitError("{0} 不能为空".format(path))
    if len(value) > 200_000:
        raise XaitError("{0} 文本过长".format(path))
    if CONTROL_RE.search(value):
        raise XaitError("{0} 含控制字符".format(path), EXIT_SECURITY)
    if HTML_TAG_RE.search(value):
        raise XaitError("{0} 含原始 HTML".format(path), EXIT_SECURITY)
    if MARKDOWN_BLOCK_RE.search(value) or MARKDOWN_LINK_RE.search(value):
        raise XaitError("{0} 含原始 Markdown".format(path), EXIT_SECURITY)
    return value


def _expect_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise XaitError("{0} 必须是布尔值".format(path))
    return value


def _expect_integer(value: Any, path: str, minimum: Optional[int] = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise XaitError("{0} 必须是整数".format(path))
    if minimum is not None and value < minimum:
        raise XaitError("{0} 不能小于 {1}".format(path, minimum))
    return value


def _expect_date(value: Any, path: str) -> str:
    text = _expect_string(value, path)
    if not DATE_RE.fullmatch(text):
        raise XaitError("{0} 必须使用 YYYY-MM-DD".format(path))
    try:
        Date.fromisoformat(text)
    except ValueError as exc:
        raise XaitError("{0} 不是有效日期".format(path)) from exc
    return text


def _expect_datetime(value: Any, path: str) -> str:
    text = _expect_string(value, path)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise XaitError("{0} 必须是 ISO 8601 时间".format(path)) from exc
    if parsed.tzinfo is None:
        raise XaitError("{0} 必须包含时区".format(path))
    return text


def _expect_id(value: Any, path: str) -> str:
    text = _expect_string(value, path)
    if not ID_RE.fullmatch(text):
        raise XaitError("{0} 只能包含小写字母、数字和连字符".format(path))
    return text


def _validate_public_url(value: Any, path: str) -> str:
    url = _expect_string(value, path)
    if len(url) > 4096 or any(char.isspace() for char in url):
        raise XaitError("{0} 不是安全的公开 URL".format(path), EXIT_SECURITY)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise XaitError("{0} URL 无效".format(path), EXIT_SECURITY) from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise XaitError("{0} 只允许 http/https 公共地址".format(path), EXIT_SECURITY)
    if parts.username is not None or parts.password is not None:
        raise XaitError("{0} 不允许携带 URL 凭据".format(path), EXIT_SECURITY)
    if port is not None and not (1 <= port <= 65535):
        raise XaitError("{0} 端口无效".format(path), EXIT_SECURITY)
    hostname = parts.hostname.rstrip(".").lower()
    if (hostname == "localhost" or any(hostname.endswith(suffix) for suffix in (".localhost", ".local", ".internal", ".lan", ".home"))
            or ("." not in hostname and ":" not in hostname)):
        raise XaitError("{0} 不允许本机地址".format(path), EXIT_SECURITY)
    if "%" in hostname or hostname.isdigit() or hostname.startswith("0x"):
        raise XaitError("{0} 不允许混淆的主机地址".format(path), EXIT_SECURITY)
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
        if re.fullmatch(r"[0-9.]+", hostname):
            raise XaitError("{0} 不允许混淆的主机地址".format(path), EXIT_SECURITY)
    if address is not None and not address.is_global:
        raise XaitError("{0} 不允许私网或保留地址".format(path), EXIT_SECURITY)
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in SENSITIVE_QUERY_KEYS:
            raise XaitError("{0} 含敏感查询参数".format(path), EXIT_SECURITY)
    return url


def _validate_span(value: Any, path: str) -> None:
    span = _expect_object(value, path, {"text"}, {"strong", "url"})
    _expect_string(span["text"], path + ".text")
    if "strong" in span:
        _expect_bool(span["strong"], path + ".strong")
    if "url" in span:
        _validate_public_url(span["url"], path + ".url")


def _validate_spans(value: Any, path: str) -> None:
    spans = _expect_array(value, path, minimum=1)
    for index, span in enumerate(spans):
        _validate_span(span, "{0}[{1}]".format(path, index))


def _validate_blocks(section: Dict[str, Any], path: str) -> None:
    _expect_object(section, path, {"kind", "id", "title", "blocks"})
    blocks = _expect_array(section["blocks"], path + ".blocks", minimum=1)
    for index, raw_block in enumerate(blocks):
        block_path = "{0}.blocks[{1}]".format(path, index)
        if not isinstance(raw_block, dict):
            raise XaitError("{0} 必须是对象".format(block_path))
        block_type = raw_block.get("type")
        if block_type == "paragraph":
            block = _expect_object(raw_block, block_path, {"type", "spans"})
            _validate_spans(block["spans"], block_path + ".spans")
        elif block_type == "list":
            block = _expect_object(raw_block, block_path, {"type", "ordered", "items"})
            _expect_bool(block["ordered"], block_path + ".ordered")
            items = _expect_array(block["items"], block_path + ".items", minimum=1)
            for item_index, raw_item in enumerate(items):
                item_path = "{0}.items[{1}]".format(block_path, item_index)
                item = _expect_object(raw_item, item_path, {"spans"})
                _validate_spans(item["spans"], item_path + ".spans")
        else:
            raise XaitError("{0}.type 只允许 paragraph 或 list".format(block_path))


def _validate_links(section: Dict[str, Any], path: str) -> None:
    _expect_object(section, path, {"kind", "id", "title", "items"})
    items = _expect_array(section["items"], path + ".items", minimum=1)
    for index, raw_item in enumerate(items):
        item_path = "{0}.items[{1}]".format(path, index)
        item = _expect_object(raw_item, item_path, {"title"}, {"url", "meta"})
        _expect_string(item["title"], item_path + ".title")
        if "url" in item:
            _validate_public_url(item["url"], item_path + ".url")
        if "meta" in item:
            _expect_string(item["meta"], item_path + ".meta", allow_empty=True)


def _validate_table_cell(value: Any, path: str) -> None:
    if isinstance(value, str):
        _expect_string(value, path)
        return
    cell = _expect_object(value, path, {"text"}, {"url"})
    _expect_string(cell["text"], path + ".text")
    if "url" in cell:
        _validate_public_url(cell["url"], path + ".url")


def _validate_table(section: Dict[str, Any], path: str) -> None:
    _expect_object(section, path, {"kind", "id", "title", "columns", "rows"})
    columns = _expect_array(section["columns"], path + ".columns", minimum=1)
    for index, column in enumerate(columns):
        _expect_string(column, "{0}.columns[{1}]".format(path, index))
    rows = _expect_array(section["rows"], path + ".rows", minimum=1)
    for row_index, raw_row in enumerate(rows):
        row_path = "{0}.rows[{1}]".format(path, row_index)
        row = _expect_array(raw_row, row_path, minimum=1)
        if len(row) != len(columns):
            raise XaitError("{0} 列数与 columns 不一致".format(row_path))
        for cell_index, cell in enumerate(row):
            _validate_table_cell(cell, "{0}[{1}]".format(row_path, cell_index))


def _validate_wechat(section: Dict[str, Any], path: str) -> None:
    _expect_object(section, path, {"kind", "id", "title", "overview", "capturedAt", "accounts"})
    _expect_string(section["overview"], path + ".overview")
    _expect_datetime(section["capturedAt"], path + ".capturedAt")
    accounts = _expect_array(section["accounts"], path + ".accounts", minimum=4, maximum=4)
    account_names: Set[str] = set()
    for index, raw_account in enumerate(accounts):
        account_path = "{0}.accounts[{1}]".format(path, index)
        account = _expect_object(
            raw_account,
            account_path,
            {"name", "status", "statusTone", "sourceUrl", "items"},
        )
        name = _expect_string(account["name"], account_path + ".name")
        if name in account_names:
            raise XaitError("{0}.name 重复".format(account_path))
        account_names.add(name)
        _expect_string(account["status"], account_path + ".status")
        if account["statusTone"] not in WECHAT_TONES:
            raise XaitError("{0}.statusTone 无效".format(account_path))
        _validate_public_url(account["sourceUrl"], account_path + ".sourceUrl")
        items = _expect_array(account["items"], account_path + ".items")
        entries: Set[Tuple[str, str]] = set()
        for item_index, raw_item in enumerate(items):
            item_path = "{0}.items[{1}]".format(account_path, item_index)
            item = _expect_object(raw_item, item_path, {"badge", "title", "meta"}, {"url"})
            _expect_string(item["badge"], item_path + ".badge")
            title = _expect_string(item["title"], item_path + ".title")
            _expect_string(item["meta"], item_path + ".meta", allow_empty=True)
            if "url" in item:
                url = _validate_public_url(item["url"], item_path + ".url")
            else:
                url = ""
            entry_key = (title, url)
            if entry_key in entries:
                raise XaitError("{0} 的标题与链接组合重复".format(item_path))
            entries.add(entry_key)
    if account_names != WECHAT_ACCOUNTS:
        raise XaitError("{0}.accounts 必须且只能包含 APPSO、数字生命卡兹克、智东西、花叔".format(path))


def _validate_social(section: Dict[str, Any], path: str) -> None:
    _expect_object(section, path, {"kind", "id", "title", "overview", "platforms"})
    _expect_string(section["overview"], path + ".overview")
    platforms = _expect_array(section["platforms"], path + ".platforms", minimum=1)
    platform_ids: Set[str] = set()
    for index, raw_platform in enumerate(platforms):
        platform_path = "{0}.platforms[{1}]".format(path, index)
        platform = _expect_object(
            raw_platform,
            platform_path,
            {"id", "title", "snapshotLabel", "status", "origin", "items"},
        )
        platform_id = _expect_id(platform["id"], platform_path + ".id")
        if platform_id in platform_ids:
            raise XaitError("{0}.id 重复".format(platform_path))
        platform_ids.add(platform_id)
        _expect_string(platform["title"], platform_path + ".title")
        _expect_string(platform["snapshotLabel"], platform_path + ".snapshotLabel")
        _expect_string(platform["origin"], platform_path + ".origin")
        if platform["status"] not in SOCIAL_STATUS:
            raise XaitError("{0}.status 无效".format(platform_path))
        items = _expect_array(platform["items"], platform_path + ".items", maximum=10)
        if platform["status"] == "unavailable" and items:
            raise XaitError("{0}.items 在 unavailable 状态下必须为空".format(platform_path))
        if platform_id in {"xiaohongshu", "douyin"} and platform["status"] != "unavailable" and len(items) != 10:
            raise XaitError("{0}.items 可用或沿用快照时必须恰好有 10 项".format(platform_path))
        ranks: Set[int] = set()
        urls: Set[str] = set()
        for item_index, raw_item in enumerate(items):
            item_path = "{0}.items[{1}]".format(platform_path, item_index)
            item = _expect_object(raw_item, item_path, {"rank", "title", "meta", "heat"}, {"url"})
            rank = _expect_integer(item["rank"], item_path + ".rank", minimum=1)
            if rank in ranks:
                raise XaitError("{0}.rank 重复".format(item_path))
            ranks.add(rank)
            _expect_string(item["title"], item_path + ".title")
            _expect_string(item["meta"], item_path + ".meta", allow_empty=True)
            _expect_string(item["heat"], item_path + ".heat", allow_empty=True)
            if "url" in item:
                url = _validate_public_url(item["url"], item_path + ".url")
                if url in urls:
                    raise XaitError("{0}.url 重复".format(item_path))
                urls.add(url)
        if ranks and ranks != set(range(1, len(items) + 1)):
            raise XaitError("{0}.items 的 rank 必须从 1 连续编号".format(platform_path))
    if not {"xiaohongshu", "douyin"}.issubset(platform_ids):
        raise XaitError("{0}.platforms 必须包含 xiaohongshu 与 douyin".format(path))


SECTION_VALIDATORS = {
    "blocks": _validate_blocks,
    "links": _validate_links,
    "table": _validate_table,
    "wechat": _validate_wechat,
    "social": _validate_social,
}


def _strict_datetime(value: Any, path: str) -> datetime:
    text = _expect_string(value, path)
    if not RFC3339_RE.fullmatch(text):
        raise XaitError("{0} 必须是包含时区的 ISO 8601 时间".format(path))
    _expect_datetime(text, path)
    return datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)


def _validate_editorial(root: Dict[str, Any], path: str) -> None:
    generated = _strict_datetime(root["generatedAt"], path + ".generatedAt")
    if generated.astimezone(CST).date().isoformat() != root["date"]:
        raise XaitError("{0}.generatedAt 的北京时间日期必须与 date 一致".format(path))
    edition = _expect_object(root["edition"], path + ".edition", {"windowStart", "windowEnd"})
    start = _strict_datetime(edition["windowStart"], path + ".edition.windowStart")
    end = _strict_datetime(edition["windowEnd"], path + ".edition.windowEnd")
    expected_end = datetime.fromisoformat(root["date"] + "T08:45:00+08:00")
    if (start.utcoffset() != timedelta(hours=8) or end.utcoffset() != timedelta(hours=8)
            or end != expected_end or start != expected_end - timedelta(days=1)):
        raise XaitError("{0}.edition 必须为前日 08:45 至当日 08:45，时区 +08:00".format(path))
    sources = _expect_array(root["sources"], path + ".sources")
    source_ids: Set[str] = set()
    for index, raw in enumerate(sources):
        item_path = "{0}.sources[{1}]".format(path, index)
        source = _expect_object(raw, item_path, {
            "id", "label", "status", "checkedAt", "lastSuccessAt", "itemCount", "message",
        })
        source_id = _expect_id(source["id"], item_path + ".id")
        if source_id in source_ids:
            raise XaitError("{0}.id 重复".format(item_path))
        source_ids.add(source_id)
        _expect_string(source["label"], item_path + ".label")
        if not isinstance(source["status"], str) or source["status"] not in SOURCE_STATUS:
            raise XaitError("{0}.status 无效".format(item_path))
        provenance = {}
        for field in ("checkedAt", "lastSuccessAt"):
            if source[field] is not None:
                provenance[field] = _strict_datetime(source[field], item_path + "." + field)
                if provenance[field] > generated:
                    raise XaitError("{0}.{1} 不得晚于 generatedAt".format(item_path, field))
        if ("checkedAt" in provenance and "lastSuccessAt" in provenance
                and provenance["lastSuccessAt"] > provenance["checkedAt"]):
            raise XaitError("{0}.lastSuccessAt 不得晚于 checkedAt".format(item_path))
        _expect_integer(source["itemCount"], item_path + ".itemCount", minimum=0)
        _expect_string(source["message"], item_path + ".message", allow_empty=True)
    article_ids: Set[str] = set()
    for index, raw in enumerate(_expect_array(root["articles"], path + ".articles")):
        item_path = "{0}.articles[{1}]".format(path, index)
        article = _expect_object(raw, item_path, {
            "id", "sourceId", "title", "url", "publishedAt", "dateEvidence", "collectedAt", "category",
        }, {"originalUrl", "eventKey", "summary"})
        article_id = _expect_id(article["id"], item_path + ".id")
        if article_id in article_ids:
            raise XaitError("{0}.id 重复".format(item_path))
        article_ids.add(article_id)
        if _expect_id(article["sourceId"], item_path + ".sourceId") not in source_ids:
            raise XaitError("{0}.sourceId 未声明".format(item_path))
        _expect_string(article["title"], item_path + ".title")
        _validate_public_url(article["url"], item_path + ".url")
        evidence = article["dateEvidence"]
        if evidence == "exact":
            _strict_datetime(article["publishedAt"], item_path + ".publishedAt")
        elif evidence == "day":
            _expect_date(article["publishedAt"], item_path + ".publishedAt")
        elif evidence == "unknown":
            if article["publishedAt"] is not None:
                raise XaitError("{0}.publishedAt 日期未知时必须为 null".format(item_path))
        else:
            raise XaitError("{0}.dateEvidence 无效".format(item_path))
        if _strict_datetime(article["collectedAt"], item_path + ".collectedAt") > generated:
            raise XaitError("{0}.collectedAt 不得晚于 generatedAt".format(item_path))
        if not isinstance(article["category"], str) or article["category"] not in ARTICLE_CATEGORIES:
            raise XaitError("{0}.category 无效".format(item_path))
        if "originalUrl" in article:
            _validate_public_url(article["originalUrl"], item_path + ".originalUrl")
        for field in ("eventKey", "summary"):
            if field in article:
                _expect_string(article[field], item_path + "." + field)


def validate_issue(issue: Any, source_name: str = "issue") -> Dict[str, Any]:
    version = issue.get("schemaVersion") if isinstance(issue, dict) else None
    if isinstance(version, bool) or not isinstance(version, int) or version not in {1, 2}:
        raise XaitError("{0}.schemaVersion 只支持 1 或 2".format(source_name))
    required = {"schemaVersion", "date", "generatedAt", "title", "tagline", "sections"}
    if version == 2:
        required.update({"edition", "sources", "articles"})
    root = _expect_object(
        issue,
        source_name,
        required,
    )
    issue_date = _expect_date(root["date"], source_name + ".date")
    generated_at = _expect_datetime(root["generatedAt"], source_name + ".generatedAt")
    if version == 1 and generated_at[:10] != issue_date:
        raise XaitError("{0}.generatedAt 日期必须与 date 一致".format(source_name))
    _expect_string(root["title"], source_name + ".title")
    _expect_string(root["tagline"], source_name + ".tagline")
    sections = _expect_array(root["sections"], source_name + ".sections", minimum=1)
    ids: Set[str] = set()
    kind_counts: Dict[str, int] = {}
    for index, raw_section in enumerate(sections):
        section_path = "{0}.sections[{1}]".format(source_name, index)
        if not isinstance(raw_section, dict):
            raise XaitError("{0} 必须是对象".format(section_path))
        kind = raw_section.get("kind")
        if kind not in SECTION_KINDS:
            raise XaitError("{0}.kind 无效".format(section_path))
        section_id = _expect_id(raw_section.get("id"), section_path + ".id")
        if section_id in ids:
            raise XaitError("{0}.id 重复".format(section_path))
        if version == 2 and section_id in {"collection-status", "today-brief", "source-reading"}:
            raise XaitError("{0}.id 与编辑版块保留 ID 冲突".format(section_path))
        ids.add(section_id)
        _expect_string(raw_section.get("title"), section_path + ".title")
        SECTION_VALIDATORS[kind](raw_section, section_path)
        if kind == "wechat":
            captured_day = raw_section["capturedAt"][:10]
            if captured_day > issue_date:
                raise XaitError("{0}.capturedAt 不得晚于 issue date".format(section_path))
            if captured_day < issue_date:
                # Preserve the actual capture time of a fallback, never rewrite
                # it to today's date just to satisfy a publication contract.
                if any(account["statusTone"] != "stale" for account in raw_section["accounts"]):
                    raise XaitError("{0} 的旧快照必须明确标记 stale".format(section_path))
                if any(item["badge"] == "今日" for account in raw_section["accounts"] for item in account["items"]):
                    raise XaitError("{0} 的旧快照不得标记今日推文".format(section_path))
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
    if kind_counts.get("wechat") != 1 or kind_counts.get("social") != 1:
        raise XaitError("{0} 必须恰好包含一个 wechat 和一个 social 章节".format(source_name))
    if version == 2:
        _validate_editorial(root, source_name)
    return root


def canonical_public_url(url: str) -> str:
    """Identity key: normalize host/default port and remove only known tracking keys.

    Path case, trailing slashes, fragments, query ordering and semantic query
    values are significant. We do not guess redirects or decode URL paths.
    """
    _validate_public_url(url, "article.url")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if ":" in host:
        host = "[" + host + "]"
    if parts.port is not None and (parts.scheme, parts.port) not in {("http", 80), ("https", 443)}:
        host += ":" + str(parts.port)
    query = "&".join(
        piece for piece in parts.query.split("&")
        if unquote(piece.partition("=")[0]).lower() not in TRACKING_QUERY_KEYS
    )
    return urlunsplit((parts.scheme.lower(), host, parts.path, query, parts.fragment))


def _article_order(article: Dict[str, Any]) -> Tuple[str, str, str]:
    return (article["sourceId"], canonical_public_url(article["url"]), article["id"])


def _make_group(articles: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    members = sorted(articles, key=_article_order)
    originals = {canonical_public_url(item["originalUrl"]) for item in members if item.get("originalUrl")}
    representative = min(members, key=lambda item: (
        0 if canonical_public_url(item["url"]) in originals else (1 if item.get("originalUrl") else 2),
        0 if not item.get("originalUrl") else 1,
        _article_order(item),
    ))
    main_url = representative.get("originalUrl", representative["url"])
    seen_urls = {canonical_public_url(main_url)}
    related = []
    for item in members:
        key = canonical_public_url(item["url"])
        if key not in seen_urls:
            related.append({"title": item["title"], "url": item["url"], "sourceId": item["sourceId"]})
            seen_urls.add(key)
    return {"representative": representative, "url": main_url, "articles": members, "relatedLinks": related}


def group_articles(articles: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group only explicit event keys or shared canonical/original URLs.

    No title similarity, title normalization or semantic inference participates.
    Connected components make explicit original-source chains order independent.
    """
    members = sorted(articles, key=_article_order)
    parents = list(range(len(members)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    keys: Dict[Tuple[str, str], int] = {}
    for index, article in enumerate(members):
        identities = [("url", canonical_public_url(article["url"]))]
        if article.get("originalUrl"):
            identities.append(("url", canonical_public_url(article["originalUrl"])))
        if article.get("eventKey"):
            identities.append(("event", article["eventKey"]))
        for identity in identities:
            if identity in keys:
                parents[find(index)] = find(keys[identity])
            else:
                keys[identity] = index
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for index, article in enumerate(members):
        grouped.setdefault(find(index), []).append(article)
    return sorted((_make_group(items) for items in grouped.values()), key=lambda group: _article_order(group["representative"]))


def _brief_source_allowed(article: Dict[str, Any]) -> bool:
    source = article["sourceId"].lower()
    if "aihot" in source or any(source == prefix or source.startswith(prefix + "-")
                                for prefix in ("wechat", "social", "xiaohongshu", "douyin", "weibo")):
        return False
    social_hosts = {"mp.weixin.qq.com", "weibo.com", "weibo.cn", "douyin.com", "xiaohongshu.com"}
    for field in ("url", "originalUrl"):
        if article.get(field):
            host = (urlsplit(article[field]).hostname or "").lower().rstrip(".")
            if any(host == blocked or host.endswith("." + blocked) for blocked in social_hosts):
                return False
    return True


def select_today(issue: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Select up to eight distinct, evidenced AI events from the stored edition.

    No clock/network access and no factual summary generation. Exact published
    times determine newest-first ordering; ties use stable article identity.
    Each representative source contributes at most two selected events. Hacker
    News hot/new/show feeds share one source budget.
    """
    if issue.get("schemaVersion") != 2:
        return []
    start = _strict_datetime(issue["edition"]["windowStart"], "edition.windowStart")
    end = _strict_datetime(issue["edition"]["windowEnd"], "edition.windowEnd")
    sources = {source["id"]: source for source in issue["sources"]}
    eligible = []
    for article in issue["articles"]:
        if (article["dateEvidence"] != "exact" or sources[article["sourceId"]]["status"] != "ok"
                or not _brief_source_allowed(article)):
            continue
        published = _strict_datetime(article["publishedAt"], "article.publishedAt")
        collected = _strict_datetime(article["collectedAt"], "article.collectedAt")
        if start <= published < end and published <= collected and AI_RE.search(article["title"] + " " + article.get("summary", "")):
            eligible.append(article)
    groups = group_articles(eligible)
    groups.sort(key=lambda group: (
        -_strict_datetime(group["representative"]["publishedAt"], "article.publishedAt").timestamp(),
        _article_order(group["representative"]),
    ))
    selected = []
    counts: Dict[str, int] = {}
    for group in groups:
        source_id = group["representative"]["sourceId"]
        family = "hacker-news" if source_id in {"hacker-news", "hacker-news-new", "hacker-news-show"} else source_id
        if counts.get(family, 0) >= 2:
            continue
        counts[family] = counts.get(family, 0) + 1
        group["reason"] = "入选依据：AI 相关；来源记录时间在本期窗口内；采集成功。"
        if len(group["articles"]) > 1:
            group["reason"] += " 已按相同公开链接、明确原文链接或事件标识合并 {0} 条记录。".format(len(group["articles"]))
        selected.append(group)
        if len(selected) == 8:
            break
    return selected


def load_issues(issues_dir: Path = ISSUES_DIR) -> List[Dict[str, Any]]:
    if not issues_dir.is_dir():
        raise XaitError("缺少公开数据目录 content/issues", EXIT_INPUT)
    paths = sorted(issues_dir.glob("*.json"))
    if not paths:
        raise XaitError("content/issues 中没有简报 JSON", EXIT_INPUT)
    issues: List[Dict[str, Any]] = []
    seen_dates: Set[str] = set()
    for path in paths:
        if not DATE_RE.fullmatch(path.stem):
            raise XaitError("简报文件名必须是 YYYY-MM-DD.json：{0}".format(path.name))
        issue = validate_issue(_load_json(path), path.name)
        if issue["date"] != path.stem:
            raise XaitError("{0} 的 date 与文件名不一致".format(path.name))
        if issue["date"] in seen_dates:
            raise XaitError("简报日期重复：{0}".format(issue["date"]))
        seen_dates.add(issue["date"])
        issues.append(issue)
    return sorted(issues, key=lambda item: item["date"])


def _escape_text(value: str) -> str:
    return html.escape(value, quote=True).replace("\n", "<br>\n")


def _link(url: str, text: str, css_class: str = "") -> str:
    class_attr = ' class="{0}"'.format(css_class) if css_class else ""
    return '<a{0} href="{1}" target="_blank" rel="noopener noreferrer">{2}</a>'.format(
        class_attr,
        html.escape(url, quote=True),
        _escape_text(text),
    )


def _render_spans(spans: Sequence[Dict[str, Any]]) -> str:
    rendered: List[str] = []
    for span in spans:
        piece = _escape_text(span["text"])
        if span.get("strong"):
            piece = "<strong>{0}</strong>".format(piece)
        if span.get("url"):
            piece = '<a href="{0}" target="_blank" rel="noopener noreferrer">{1}</a>'.format(
                html.escape(span["url"], quote=True), piece
            )
        rendered.append(piece)
    return "".join(rendered)


def _render_blocks(section: Dict[str, Any]) -> str:
    output: List[str] = []
    for block in section["blocks"]:
        if block["type"] == "paragraph":
            output.append("<p>{0}</p>".format(_render_spans(block["spans"])))
        else:
            tag = "ol" if block["ordered"] else "ul"
            items = "\n".join("<li>{0}</li>".format(_render_spans(item["spans"])) for item in block["items"])
            output.append("<{0}>\n{1}\n</{0}>".format(tag, items))
    return "\n".join(output)


def _render_links(section: Dict[str, Any]) -> str:
    items: List[str] = []
    for item in section["items"]:
        title = _link(item["url"], item["title"]) if item.get("url") else "<span>{0}</span>".format(_escape_text(item["title"]))
        meta = '<span class="link-meta">{0}</span>'.format(_escape_text(item["meta"])) if item.get("meta") else ""
        items.append('<li class="link-item">{0}{1}</li>'.format(title, meta))
    return '<ul class="link-list">\n{0}\n</ul>'.format("\n".join(items))


def _render_table_cell(cell: Any, tag: str) -> str:
    if isinstance(cell, str):
        body = _escape_text(cell)
    else:
        body = _link(cell["url"], cell["text"]) if cell.get("url") else _escape_text(cell["text"])
    return "<{0}>{1}</{0}>".format(tag, body)


def _render_table(section: Dict[str, Any]) -> str:
    head = "".join(_render_table_cell(column, "th") for column in section["columns"])
    rows = "\n".join(
        "<tr>{0}</tr>".format("".join(_render_table_cell(cell, "td") for cell in row))
        for row in section["rows"]
    )
    return (
        '<div class="table-wrap"><table class="data-table">'
        "<thead><tr>{0}</tr></thead><tbody>{1}</tbody></table></div>"
    ).format(head, rows)


def _render_wechat(section: Dict[str, Any]) -> str:
    panels: List[str] = []
    for account in section["accounts"]:
        entries: List[str] = []
        for item in account["items"]:
            title = _link(item["url"], item["title"]) if item.get("url") else "<span>{0}</span>".format(_escape_text(item["title"]))
            entries.append(
                '<li class="wechat-item"><span class="wechat-badge">{0}</span>'
                '<span class="wechat-copy">{1}<span class="wechat-meta">{2}</span></span></li>'.format(
                    _escape_text(item["badge"]), title, _escape_text(item["meta"])
                )
            )
        item_html = '<ol class="wechat-list">{0}</ol>'.format("".join(entries)) if entries else '<div class="wechat-empty">当前快照没有公开文章</div>'
        panels.append(
            '<section class="wechat-panel" aria-label="{0}每日推文">'
            '<div class="wechat-panel-head"><span class="wechat-account">{0}</span>'
            '<span class="wechat-state {1}">{2}</span></div>{3}'
            '<div class="wechat-origin">{4}</div></section>'.format(
                _escape_text(account["name"]),
                html.escape(account["statusTone"], quote=True),
                _escape_text(account["status"]),
                item_html,
                _link(account["sourceUrl"], "公开文章列表"),
            )
        )
    return '<p class="wechat-overview">{0}</p><div class="wechat-grid">{1}</div>'.format(
        _escape_text(section["overview"]), "".join(panels)
    )


def _render_social(section: Dict[str, Any], compact_empty: bool = False) -> str:
    panels: List[str] = []
    for platform in section["platforms"]:
        entries: List[str] = []
        for item in platform["items"]:
            title = _link(item["url"], item["title"]) if item.get("url") else "<span>{0}</span>".format(_escape_text(item["title"]))
            entries.append(
                '<li class="social-item"><span class="social-rank">{0}</span>'
                '<span class="social-copy">{1}<span class="social-meta">{2}</span></span>'
                '<span class="social-heat">{3}</span></li>'.format(
                    item["rank"], title, _escape_text(item["meta"]), _escape_text(item["heat"])
                )
            )
        item_html = '<ol class="social-list">{0}</ol>'.format("".join(entries)) if entries else '<div class="social-empty">该来源当前不可用，等待下一次有效快照</div>'
        origin = '<div class="social-origin">{0}</div>'.format(_escape_text(platform["origin"]))
        if compact_empty and not entries:
            origin = '<details class="social-origin-details"><summary>采集说明</summary>{0}</details>'.format(origin)
        panels.append(
            '<section class="social-panel" aria-labelledby="platform-{0}">'
            '<div class="social-panel-head"><span class="social-title" id="platform-{0}">{1}</span>'
            '<span class="social-status {2}">{3}</span></div>{4}'
            '{5}</section>'.format(
                html.escape(platform["id"], quote=True),
                _escape_text(platform["title"]),
                html.escape(platform["status"], quote=True),
                _escape_text(platform["snapshotLabel"]),
                item_html,
                origin,
            )
        )
    return '<p class="social-overview">{0}</p><div class="social-grid">{1}</div>'.format(
        _escape_text(section["overview"]), "".join(panels)
    )


SECTION_RENDERERS = {
    "blocks": _render_blocks,
    "links": _render_links,
    "table": _render_table,
    "wechat": _render_wechat,
    "social": _render_social,
}


def render_editorial(issue: Dict[str, Any]) -> str:
    """Render the v2 collection ledger and derived daily briefing only."""
    if issue.get("schemaVersion") != 2:
        return ""
    status_labels = {"ok": "成功", "empty": "无新增", "unavailable": "不可用", "stale": "沿用旧快照", "not_run": "未运行"}
    counts = {status: sum(source["status"] == status for source in issue["sources"]) for status in status_labels}
    summary = " / ".join("{0} {1}".format(label, counts[status]) for status, label in status_labels.items())
    headings = ("来源", "状态", "检查时间", "最近成功", "条数", "说明")
    rows = []
    for source in issue["sources"]:
        values = (source["label"], status_labels[source["status"]], source["checkedAt"] or "未记录",
                  source["lastSuccessAt"] or "未记录", str(source["itemCount"]), source["message"] or "—")
        rows.append('<tr>{0}</tr>'.format("".join(
            '<td data-label="{0}">{1}</td>'.format(label, _escape_text(value)) for label, value in zip(headings, values)
        )))
    if not rows:
        rows.append('<tr><td colspan="6">本期没有来源记录</td></tr>')
    window = "{0} 至 {1}（北京时间；含起点，不含终点）".format(
        _strict_datetime(issue["edition"]["windowStart"], "edition.windowStart").astimezone(CST).strftime("%Y-%m-%d %H:%M"),
        _strict_datetime(issue["edition"]["windowEnd"], "edition.windowEnd").astimezone(CST).strftime("%Y-%m-%d %H:%M"),
    )
    collection = (
        '<section class="section collection-status" id="collection-status"><h2>采集概况</h2>'
        '<p class="collection-summary">{0}</p><p class="collection-window">{1}</p>'
        '<details class="collection-details"><summary>查看来源状态与采集时间</summary>'
        '<div class="table-wrap"><table class="data-table collection-table"><thead><tr>{2}</tr></thead>'
        '<tbody>{3}</tbody></table></div></details></section>'
    ).format(_escape_text(summary), _escape_text(window), "".join('<th scope="col">{0}</th>'.format(label) for label in headings), "".join(rows))
    sources = {source["id"]: source for source in issue["sources"]}
    category_labels = {"models": "模型", "products": "产品", "research": "研究", "tutorials": "教程", "industry": "行业", "opensource": "开源", "other": "综合"}
    cards = []
    for group in select_today(issue):
        item = group["representative"]
        timestamp = _strict_datetime(item["publishedAt"], "article.publishedAt").astimezone(CST).strftime("%m-%d %H:%M")
        meta = '{0} · <time datetime="{1}">{2}</time>（北京时间） · {3}'.format(
            _escape_text(sources[item["sourceId"]]["label"]), html.escape(item["publishedAt"], quote=True),
            timestamp, category_labels[item["category"]],
        )
        body = '<h3>{0}</h3><p class="brief-meta">{1}</p>'.format(_link(group["url"], item["title"]), meta)
        if item.get("summary"):
            body += '<p class="brief-summary">{0}</p>'.format(_escape_text(item["summary"]))
        body += '<p class="brief-reason">{0}</p>'.format(_escape_text(group["reason"]))
        if group["relatedLinks"]:
            links = "".join('<li>{0}<span class="brief-related-source"> · {1}</span></li>'.format(
                _link(link["url"], link["title"]), _escape_text(sources[link["sourceId"]]["label"])
            ) for link in group["relatedLinks"])
            body += '<details class="brief-related"><summary>相关报道（{0}）</summary><ul>{1}</ul></details>'.format(len(group["relatedLinks"]), links)
        cards.append('<article class="brief-event">{0}</article>'.format(body))
    brief_body = '<div class="brief-grid">{0}</div>'.format("".join(cards)) if cards else (
        '<p class="brief-empty">本期没有满足条件的今日必读。仅采用窗口内发布时间明确、采集成功且与 AI 相关的公开文章；日期不明或来源受限的内容请在按来源阅读中查看。</p>'
    )
    briefing = (
        '<section class="section today-brief" id="today-brief"><h2>今日必读</h2>'
        '<p class="brief-policy">标题或摘要含 AI 相关词，按来源记录的发布时间排序，最多 8 条；每个代表来源最多 2 条，Hacker News 各频道共用额度。相同公开链接、明确原文链接或事件标识可合并；不按相似标题合并。来源收录时间不等同于原文首发时间。</p>{0}</section>'
    ).format(brief_body)
    return collection + "\n" + briefing


def _render_sections(issue: Dict[str, Any]) -> str:
    chunks: List[str] = []
    for section in issue["sections"]:
        if issue["schemaVersion"] == 2 and section["kind"] == "social":
            body = _render_social(section, compact_empty=True)
        else:
            body = SECTION_RENDERERS[section["kind"]](section)
        if section["id"] == "source-health":
            body = (
                '<details class="source-health"><summary>查看各来源状态、条数与采集时间</summary>'
                + body + "</details>"
            )
        chunks.append(
            '          <section class="section section-{0}" id="{1}">\n'
            "            <h2>{2}</h2>\n"
            '            <div class="content">{3}</div>\n'
            "          </section>".format(
                section["kind"],
                html.escape(section["id"], quote=True),
                _escape_text(section["title"]),
                body,
            )
        )
    source_body = "\n".join(chunks)
    if issue["schemaVersion"] == 1:
        return source_body
    nav = '<nav class="reading-nav" aria-label="按来源跳转">{0}</nav>'.format("".join(
        '<a href="#{0}">{1}</a>'.format(html.escape(section["id"], quote=True), _escape_text(section["title"]))
        for section in issue["sections"]
    ))
    return render_editorial(issue) + '\n<section class="section source-reading" id="source-reading"><h2>按来源阅读</h2>{0}\n{1}\n</section>'.format(nav, source_body)


def _render_history_links(dates: Sequence[str], selected: str, prefix: str) -> str:
    lines: List[str] = []
    for issue_date in reversed(dates):
        active = " active" if issue_date == selected else ""
        href = "{0}archive/{1}/".format(prefix, issue_date)
        lines.append(
            '      <a class="sidebar-link{0}" href="{1}"{2}>{3}</a>'.format(
                active,
                html.escape(href, quote=True),
                ' aria-current="page"' if active else "",
                issue_date,
            )
        )
    return "\n".join(lines)


def _render_page(template: str, issue: Dict[str, Any], dates: Sequence[str], is_home: bool) -> str:
    issue_date = issue["date"]
    prefix = "" if is_home else "../../"
    canonical = PUBLIC_BASE_URL if is_home else "{0}archive/{1}/".format(PUBLIC_BASE_URL, issue_date)
    page_title = issue["title"] if is_home else "{0} · {1}".format(issue["title"], issue_date)
    replacements = {
        "{{PAGE_TITLE}}": _escape_text(page_title),
        "{{TAGLINE}}": _escape_text(issue["tagline"]),
        "{{CANONICAL_URL}}": html.escape(canonical, quote=True),
        "{{ASSET_PREFIX}}": prefix,
        "{{HOME_HREF}}": "./" if is_home else "../../",
        "{{HISTORY_LINKS}}": _render_history_links(dates, issue_date, prefix),
        "{{ISSUE_TITLE}}": _escape_text(issue["title"]),
        "{{ISSUE_LABEL}}": "最新一期" if is_home else "历史归档",
        "{{ISSUE_DATE}}": issue_date,
        "{{ISSUE_JSON_HREF}}": "{0}issues/{1}.json".format(prefix, issue_date),
        "{{CARD_TAG}}": "最新一期" if is_home else "历史简报",
        "{{SECTIONS}}": _render_sections(issue),
        "{{GENERATED_AT}}": _escape_text(issue["generatedAt"]),
        "{{HEALTH_HREF}}": prefix + "health.json",
    }
    rendered = template
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    unresolved = re.findall(r"\{\{[A-Z0-9_]+\}\}", rendered)
    if unresolved:
        raise XaitError("页面模板包含未替换标记：{0}".format(", ".join(sorted(set(unresolved)))), EXIT_BUILD)
    return rendered.rstrip() + "\n"


def _find_section(issue: Dict[str, Any], kind: str) -> Dict[str, Any]:
    for section in issue["sections"]:
        if section["kind"] == kind:
            return section
    raise XaitError("{0} 缺少 {1} 章节".format(issue["date"], kind), EXIT_BUILD)


def _wechat_compat(issue: Dict[str, Any]) -> Dict[str, Any]:
    section = _find_section(issue, "wechat")
    return {
        "schemaVersion": 1,
        "date": issue["date"],
        "generatedAt": issue["generatedAt"],
        "sourcePolicy": section["overview"],
        "capturedAt": section["capturedAt"],
        "accounts": [
            {
                "account": account["name"],
                "status": account["status"],
                "statusTone": account["statusTone"],
                "sourceUrl": account["sourceUrl"],
                "items": account["items"],
            }
            for account in section["accounts"]
        ],
    }


def _social_compat(issue: Dict[str, Any]) -> Dict[str, Any]:
    section = _find_section(issue, "social")
    return {
        "schemaVersion": 1,
        "date": issue["date"],
        "generatedAt": issue["generatedAt"],
        "rankingPolicy": section["overview"],
        "platforms": [
            {
                "key": platform["id"],
                "label": platform["title"],
                "collectedAt": platform["snapshotLabel"],
                "status": platform["status"],
                "origin": platform["origin"],
                "items": [
                    {
                        "rank": item["rank"],
                        "title": item["title"],
                        **({"url": item["url"]} if item.get("url") else {}),
                        "meta": item["meta"],
                        "engagementLabel": item["heat"],
                    }
                    for item in platform["items"]
                ],
            }
            for platform in section["platforms"]
        ],
    }


def _write_bytes(root: Path, relative: str, data: bytes) -> None:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def _write_json(root: Path, relative: str, value: Any) -> None:
    _write_bytes(root, relative, _canonical_json(value))


def build_site(destination: Path, issues: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Build a complete deterministic site into an empty destination directory."""
    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise XaitError("构建目标必须为空：{0}".format(destination), EXIT_BUILD)
    destination.mkdir(parents=True, exist_ok=True)
    issues = issues if issues is not None else load_issues()
    if not issues:
        raise XaitError("没有可构建的简报", EXIT_INPUT)
    for index, issue in enumerate(issues):
        validate_issue(issue, "issues[{0}]".format(index))
    issues = sorted(issues, key=lambda item: item["date"])
    dates = [issue["date"] for issue in issues]
    latest = issues[-1]
    try:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise XaitError("无法读取页面模板：{0}".format(exc), EXIT_BUILD) from exc

    _write_bytes(destination, ".nojekyll", b"")
    for asset_name in ("app.css", "app.js"):
        source = ASSETS_DIR / asset_name
        try:
            _write_bytes(destination, "assets/" + asset_name, source.read_bytes())
        except OSError as exc:
            raise XaitError("无法复制静态资源 {0}：{1}".format(asset_name, exc), EXIT_BUILD) from exc

    _write_bytes(destination, "index.html", _render_page(template, latest, dates, True).encode("utf-8"))
    issue_hashes: Dict[str, str] = {}
    for issue in issues:
        issue_date = issue["date"]
        issue_bytes = _canonical_json(issue)
        issue_hashes[issue_date] = hashlib.sha256(issue_bytes).hexdigest()
        _write_bytes(destination, "issues/{0}.json".format(issue_date), issue_bytes)
        _write_bytes(
            destination,
            "archive/{0}/index.html".format(issue_date),
            _render_page(template, issue, dates, False).encode("utf-8"),
        )
        _write_json(destination, "wechat-daily-{0}.json".format(issue_date), _wechat_compat(issue))
        _write_json(destination, "social-research-{0}.json".format(issue_date), _social_compat(issue))

    _write_json(destination, "wechat-daily.json", _wechat_compat(latest))
    _write_json(destination, "social-research.json", _social_compat(latest))
    _write_json(
        destination,
        "history.json",
        {
            "schemaVersion": 1,
            "latest": latest["date"],
            "dates": list(reversed(dates)),
            "archives": {item: "archive/{0}/".format(item) for item in reversed(dates)},
        },
    )
    _write_json(
        destination,
        "health.json",
        {
            "schemaVersion": 1,
            "status": "ok",
            "buildMode": "offline",
            "latest": latest["date"],
            "generatedAt": latest["generatedAt"],
            "issueCount": len(issues),
            "issueSha256": issue_hashes,
        },
    )
    return {"latest": latest["date"], "issueCount": len(issues), "destination": str(destination)}


class _SiteHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: List[Dict[str, str]] = []
        self.resources: List[str] = []
        self.themes: List[str] = []
        self.inline_scripts = 0

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, Optional[str]]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "a" and values.get("href"):
            self.anchors.append(values)
        elif tag == "script":
            if values.get("src"):
                self.resources.append(values["src"])
            else:
                self.inline_scripts += 1
        elif tag == "link" and values.get("href") and "stylesheet" in values.get("rel", "").split():
            self.resources.append(values["href"])
        if values.get("data-theme"):
            self.themes.append(values["data-theme"])


def _iter_files(root: Path) -> Iterable[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _unescape_scan_text(text: str) -> str:
    text = html.unescape(text).replace("\\/", "/")
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match.group(1), 16)), text)


def _decode_scan_text(text: str) -> str:
    previous = None
    while text != previous:
        previous = text
        text = unquote(_unescape_scan_text(text))
    return text


PUBLIC_TEXT_URL_RE = re.compile(r"https?://[^\s<>\"'\\]+", re.IGNORECASE)
LOCAL_PATH_RE = re.compile(
    r"(?i)(?:/(?:users|home|private|volumes|var/folders)/"
    r"|\b[a-z]:[\\/](?:users|documents and settings|windows|temp)[\\/]"
    r"|\\\\[^\\\s]+\\[^\\\s]+|(?:^|[\s\"'=])~[/\\])"
)


def _path_scan_text(text: str) -> str:
    """Mask literal /users/ only inside a validated public URL's path.

    Do this before percent decoding: encoded local paths never receive this
    narrow exception. Queries, fragments, surrounding prose and all other
    sensitive scans keep their complete text. No domains are exempted.
    """
    text = text.replace("\\/", "/")

    def mask_url(match: Any) -> str:
        url = match.group(0)
        try:
            _validate_public_url(url, "text.url")
        except XaitError:
            return url
        parts = urlsplit(url)
        start = len(parts.scheme) + 3 + len(parts.netloc)
        finish = start + len(parts.path)
        path = re.sub(r"(?i)/users/", "/public-users/", url[start:finish])
        return url[:start] + path + url[finish:]

    return _decode_scan_text(PUBLIC_TEXT_URL_RE.sub(mask_url, text))


def _scan_sensitive_text(text: str, relative: str) -> None:
    previous_personal_prefix = "".join(
        chr(code)
        for code in (110, 105, 99, 111, 108, 101, 45, 98, 114, 105, 101, 102, 105, 110, 103)
    )
    forbidden_literals = {
        "fonts.googleapis.com": "远程 Google Fonts",
        "fonts.gstatic.com": "远程 Google Fonts",
        "file" + "://": "本机文件 URL",
        previous_personal_prefix + "-theme": "旧个人主题键",
        previous_personal_prefix: "旧个人命名",
    }
    decoded = _decode_scan_text(text)
    lowered = decoded.lower()
    for literal, label in forbidden_literals.items():
        if literal.lower() in lowered:
            raise XaitError("{0} 含{1}".format(relative, label), EXIT_SECURITY)
    if LOCAL_PATH_RE.search(_path_scan_text(text)):
        raise XaitError("{0} 含本机绝对路径".format(relative), EXIT_SECURITY)
    for match in PUBLIC_TEXT_URL_RE.finditer(decoded):
        _validate_public_url(match.group(0), relative + ".url")
    credential_patterns = [
        re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|authorization|cookie|password|secret)\s*['\"]?\s*[:=]\s*['\"]?[^\s<'\",}]{1,}"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ]
    if any(pattern.search(decoded) for pattern in credential_patterns):
        raise XaitError("{0} 疑似包含凭据".format(relative), EXIT_SECURITY)
    for match in re.finditer(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", decoded):
        try:
            address = ipaddress.ip_address(match.group(0))
        except ValueError:
            continue
        if not address.is_global:
            raise XaitError("{0} 含私网或保留 IP".format(relative), EXIT_SECURITY)


def _resolve_local_link(site_root: Path, html_path: Path, href: str) -> Optional[Path]:
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        _validate_public_url(href, str(html_path.relative_to(site_root)) + ".link")
        return None
    path_part = unquote(parts.path)
    if not path_part or path_part.startswith("#"):
        return None
    if path_part.startswith("/"):
        raise XaitError("{0} 含根绝对链接 {1}".format(html_path.relative_to(site_root), href), EXIT_BUILD)
    candidate = (html_path.parent / path_part).resolve()
    site_resolved = site_root.resolve()
    try:
        candidate.relative_to(site_resolved)
    except ValueError as exc:
        raise XaitError("{0} 的链接越出站点目录：{1}".format(html_path.relative_to(site_root), href), EXIT_SECURITY) from exc
    if path_part.endswith("/"):
        candidate = candidate / "index.html"
    return candidate


def validate_built_site(site_root: Path, issues: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    site_root = Path(site_root)
    if not site_root.is_dir():
        raise XaitError("缺少生成站点：{0}".format(site_root), EXIT_BUILD)
    issues = issues if issues is not None else load_issues()
    dates = [issue["date"] for issue in sorted(issues, key=lambda item: item["date"])]
    latest = dates[-1]
    expected: Set[str] = {".nojekyll", "index.html", "assets/app.css", "assets/app.js", "history.json", "health.json", "wechat-daily.json", "social-research.json"}
    for issue_date in dates:
        expected.update(
            {
                "issues/{0}.json".format(issue_date),
                "archive/{0}/index.html".format(issue_date),
                "wechat-daily-{0}.json".format(issue_date),
                "social-research-{0}.json".format(issue_date),
            }
        )
    actual = {path.relative_to(site_root).as_posix() for path in _iter_files(site_root)}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details = []
        if missing:
            details.append("缺少 " + ", ".join(missing))
        if extra:
            details.append("多出 " + ", ".join(extra))
        raise XaitError("生成文件集合异常：{0}".format("；".join(details)), EXIT_BUILD)

    for path in _iter_files(site_root):
        relative = path.relative_to(site_root).as_posix()
        if path.is_symlink():
            raise XaitError("生成站点含符号链接：{0}".format(relative), EXIT_SECURITY)
        if path.suffix in {".html", ".css", ".js", ".json"}:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise XaitError("无法读取生成文件 {0}：{1}".format(relative, exc), EXIT_BUILD) from exc
            _scan_sensitive_text(text, relative)
            if "{{" in text or "}}" in text:
                raise XaitError("{0} 含未处理模板标记".format(relative), EXIT_BUILD)
            if path.suffix == ".json":
                _load_json(path)

    css = (site_root / "assets" / "app.css").read_text(encoding="utf-8")
    javascript = (site_root / "assets" / "app.js").read_text(encoding="utf-8")
    for theme in THEMES:
        if ".{0}".format(theme) not in css:
            raise XaitError("共享 CSS 缺少主题 {0}".format(theme), EXIT_BUILD)
    if "xait-today-theme" not in javascript:
        raise XaitError("共享 JS 缺少中性主题存储键", EXIT_BUILD)

    html_paths = [site_root / "index.html"] + [site_root / "archive" / item / "index.html" for item in dates]
    for html_path in html_paths:
        parser = _SiteHTMLParser()
        parser.feed(html_path.read_text(encoding="utf-8"))
        if parser.inline_scripts:
            raise XaitError("{0} 含内联脚本".format(html_path.relative_to(site_root)), EXIT_SECURITY)
        if set(parser.themes) != THEMES or len(parser.themes) != len(THEMES):
            raise XaitError("{0} 未完整提供七套主题".format(html_path.relative_to(site_root)), EXIT_BUILD)
        for resource in parser.resources:
            target = _resolve_local_link(site_root, html_path, resource)
            if target is None or not target.is_file():
                raise XaitError("{0} 引用不存在的资源：{1}".format(html_path.relative_to(site_root), resource), EXIT_BUILD)
        for anchor in parser.anchors:
            href = anchor["href"]
            external = bool(urlsplit(href).scheme or urlsplit(href).netloc)
            target = _resolve_local_link(site_root, html_path, href)
            if target is not None and not target.exists():
                raise XaitError("{0} 含无效站内链接：{1}".format(html_path.relative_to(site_root), href), EXIT_BUILD)
            if external:
                rel = set(anchor.get("rel", "").split())
                if anchor.get("target") != "_blank" or not {"noopener", "noreferrer"}.issubset(rel):
                    raise XaitError("{0} 的外链缺少安全窗口属性：{1}".format(html_path.relative_to(site_root), href), EXIT_SECURITY)

    history = _load_json(site_root / "history.json")
    if history.get("latest") != latest or history.get("dates") != list(reversed(dates)):
        raise XaitError("history.json 与真实归档不一致", EXIT_BUILD)
    health = _load_json(site_root / "health.json")
    if health.get("status") != "ok" or health.get("latest") != latest or health.get("issueCount") != len(issues):
        raise XaitError("health.json 与构建结果不一致", EXIT_BUILD)
    return {"latest": latest, "issueCount": len(issues), "fileCount": len(actual)}


def _directory_diff(left: Path, right: Path) -> List[str]:
    left_files = {path.relative_to(left).as_posix(): path for path in _iter_files(left)} if left.is_dir() else {}
    right_files = {path.relative_to(right).as_posix(): path for path in _iter_files(right)} if right.is_dir() else {}
    differences: List[str] = []
    for relative in sorted(set(left_files) | set(right_files)):
        if relative not in left_files:
            differences.append("missing:{0}".format(relative))
        elif relative not in right_files:
            differences.append("extra:{0}".format(relative))
        elif left_files[relative].read_bytes() != right_files[relative].read_bytes():
            differences.append("changed:{0}".format(relative))
    return differences


def check_repository(docs_dir: Path = DOCS_DIR) -> Dict[str, Any]:
    """Validate inputs and compare committed docs with a fresh deterministic build."""
    issues = load_issues()
    temporary = Path(tempfile.mkdtemp(prefix=".xait-check-", dir=str(ROOT)))
    try:
        build_site(temporary, issues)
        result = validate_built_site(temporary, issues)
        differences = _directory_diff(temporary, Path(docs_dir))
        if differences:
            preview = ", ".join(differences[:12])
            if len(differences) > 12:
                preview += ", …"
            raise XaitError("docs 与确定性构建不一致：{0}".format(preview), EXIT_DRIFT)
        result["deterministic"] = True
        result["docs"] = _display_path(Path(docs_dir))
        return result
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _validate_output_target(destination: Path) -> None:
    destination = destination.resolve()
    root_resolved = ROOT.resolve()
    protected = {root_resolved, ISSUES_DIR.resolve(), ASSETS_DIR.resolve(), TEMPLATE_PATH.parent.resolve()}
    if destination in protected or destination in root_resolved.parents:
        raise XaitError("拒绝覆盖源码目录：{0}".format(destination), EXIT_SECURITY)
    for source_root in (ROOT / "content", ROOT / "site", ROOT / "tests", ROOT / ".git"):
        try:
            destination.relative_to(source_root.resolve())
        except ValueError:
            continue
        raise XaitError("拒绝覆盖源码目录：{0}".format(destination), EXIT_SECURITY)
    if destination.is_symlink():
        raise XaitError("拒绝覆盖符号链接目录：{0}".format(destination), EXIT_SECURITY)


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def build_atomic(destination: Path = DOCS_DIR) -> Dict[str, Any]:
    """Build and validate first, then replace destination with rollback protection."""
    destination = Path(destination).resolve()
    _validate_output_target(destination)
    issues = load_issues()
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".{0}-stage-".format(destination.name), dir=str(destination.parent)))
    backup = destination.parent / ".{0}-backup-{1}".format(destination.name, uuid.uuid4().hex)
    moved_old = False
    try:
        result = build_site(stage, issues)
        validate_built_site(stage, issues)
        if destination.exists():
            if not destination.is_dir():
                raise XaitError("构建目标不是目录：{0}".format(destination), EXIT_BUILD)
            os.replace(str(destination), str(backup))
            moved_old = True
        try:
            os.replace(str(stage), str(destination))
        except Exception:
            if moved_old and backup.exists() and not destination.exists():
                os.replace(str(backup), str(destination))
                moved_old = False
            raise
        if moved_old:
            shutil.rmtree(backup, ignore_errors=True)
            moved_old = False
        result["destination"] = _display_path(destination)
        return result
    except XaitError:
        raise
    except OSError as exc:
        raise XaitError("无法安全替换构建目录：{0}".format(exc), EXIT_BUILD) from exc
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if moved_old and backup.exists() and not destination.exists():
            try:
                os.replace(str(backup), str(destination))
                moved_old = False
            except OSError:
                pass
        if backup.exists() and destination.exists():
            shutil.rmtree(backup, ignore_errors=True)


def _lan_address() -> Optional[str]:
    private_ranges = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    )
    candidates: List[str] = []
    try:
        candidates.extend(
            item[4][0]
            for item in socket.getaddrinfo(
                socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM
            )
        )
    except OSError:
        pass

    # Some systems do not publish their host address through DNS.  A UDP
    # connect only asks the kernel which interface it would use; it sends no
    # packet.  Overlay/VPN benchmark addresses are intentionally ignored.
    for target in (("1.1.1.1", 80), ("192.0.2.1", 9)):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(target)
            candidates.append(sock.getsockname()[0])
        except OSError:
            pass
        finally:
            sock.close()

    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if any(address in network for network in private_ranges):
            return candidate
    return None


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    server_version = "xAIT"
    sys_version = ""

    def version_string(self) -> str:
        return self.server_version

    def log_message(self, format_string: str, *args: Any) -> None:
        # Request targets can contain sensitive query strings supplied by a LAN
        # client.  The portable preview server therefore emits no access log.
        return

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def list_directory(self, path: str) -> None:
        # Static directories are implementation details, never browsable APIs.
        self.send_response(http.HTTPStatus.NOT_FOUND)
        self.send_header("Content-Length", "0")
        self.end_headers()
        return None


class _ReusableThreadingServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def server_bind(self) -> None:
        # HTTPServer resolves a display name with getfqdn() during startup.
        # A static preview only needs its numeric bind address; reverse DNS
        # must not delay or prevent serving offline on a local interface.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def serve(port: int = 8022, lan: bool = False) -> None:
    if not 1 <= port <= 65535:
        raise XaitError("端口必须在 1 到 65535 之间", EXIT_SERVE)
    result = build_atomic(DOCS_DIR)
    check_repository(DOCS_DIR)
    host = "0.0.0.0" if lan else "127.0.0.1"
    handler = functools.partial(_QuietHandler, directory=str(DOCS_DIR))
    try:
        server = _ReusableThreadingServer((host, port), handler)
    except OSError as exc:
        raise XaitError("无法监听 {0}:{1}：{2}".format(host, port, exc), EXIT_SERVE) from exc
    urls = ["http://127.0.0.1:{0}/".format(port)]
    if lan:
        address = _lan_address()
        urls.append("http://{0}:{1}/".format(address or "<本机局域网IP>", port))
    print("xAIT 今日已启动（{0} 期，最新 {1}）".format(result["issueCount"], result["latest"]))
    for url in urls:
        print("  " + url)
    print("按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nxAIT 今日已停止。")
    finally:
        server.server_close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="xAIT 今日离线构建与本机部署工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="校验数据并对比确定性构建结果")
    check_parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")

    build_parser = subparsers.add_parser("build", help="离线重建静态站点")
    build_parser.add_argument("--output", type=Path, default=DOCS_DIR, help=argparse.SUPPRESS)
    build_parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")

    serve_parser = subparsers.add_parser("serve", help="构建、校验并以前台方式运行")
    serve_parser.add_argument("--lan", action="store_true", help="监听 0.0.0.0，允许局域网访问")
    serve_parser.add_argument("--port", type=int, default=8022, help="监听端口（默认 8022）")
    return parser


def _emit_success(command: str, result: Dict[str, Any], as_json: bool) -> None:
    payload = {"ok": True, "command": command, **result}
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    elif command == "check":
        print("检查通过：{0} 期，最新 {1}，docs 与离线构建一致。".format(result["issueCount"], result["latest"]))
    else:
        print("构建完成：{0} 期，最新 {1}。".format(result["issueCount"], result["latest"]))


def main(argv: Optional[Sequence[str]] = None) -> int:
    # Windows redirects stdout using the active legacy code page by default.
    # The CLI has a UTF-8 contract for both human-readable Chinese and JSON,
    # independent of terminal locale or whether output is captured by CI.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
    arguments = _parser().parse_args(argv)
    as_json = bool(getattr(arguments, "json", False))
    try:
        if arguments.command == "check":
            _emit_success("check", check_repository(), as_json)
        elif arguments.command == "build":
            result = build_atomic(arguments.output)
            _emit_success("build", result, as_json)
        elif arguments.command == "serve":
            serve(port=arguments.port, lan=arguments.lan)
        return EXIT_OK
    except XaitError as exc:
        if as_json:
            print(json.dumps({"ok": False, "command": arguments.command, "error": str(exc), "exitCode": exc.exit_code}, ensure_ascii=False, sort_keys=True))
        else:
            print("错误：{0}".format(exc), file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        return EXIT_OK
    except Exception as exc:  # Defensive boundary: keep CLI failures concise.
        if as_json:
            print(json.dumps({"ok": False, "command": arguments.command, "error": str(exc), "exitCode": EXIT_BUILD}, ensure_ascii=False, sort_keys=True))
        else:
            print("错误：{0}".format(exc), file=sys.stderr)
        return EXIT_BUILD


if __name__ == "__main__":
    raise SystemExit(main())
