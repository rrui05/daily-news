"""Validate Codex research output before it is allowed into a report."""

from __future__ import annotations

import re
import unicodedata
import ipaddress
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import (
    CorroboratingSource,
    Module,
    RawItem,
    ResearchRequest,
    ValidatedItem,
    ValidationIssue,
    ValidationResult,
)


class ValidationPayloadError(ValueError):
    """The response is not structurally usable as a research result."""


ALLOWED_SOURCE_TYPES = {
    "primary",
    "official",
    "official_social",
    "social",
    "reputable_media",
}
ALLOWED_CONFIDENCE = {"high", "medium"}
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}
SEARCH_HOSTS = {
    "bing.com",
    "duckduckgo.com",
    "google.com",
    "search.yahoo.com",
}
RESERVED_SOURCE_HOSTS = {
    "example.com",
    "example.net",
    "example.org",
    "localhost",
}
TOP_LEVEL_KEYS = {
    "module",
    "topic",
    "search_queries",
    "platforms_checked",
    "items",
}
ITEM_KEYS = {
    "module",
    "title",
    "summary",
    "published_at",
    "event_time_basis",
    "source_name",
    "source_url",
    "source_type",
    "is_primary_source",
    "evidence",
    "relevance",
    "why_it_matters",
    "publication_status",
    "confidence",
    "corroborating_sources",
}


def parse_published_at(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith(("Z", "z")):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("发布时间不是有效的 ISO 8601 时间") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("发布时间缺少可验证的时区")
    return parsed


def canonical_url(value: str) -> str:
    raw = value.strip()
    if any(character.isspace() or ord(character) < 32 for character in raw):
        raise ValueError("来源 URL 不能包含空白或控制字符")
    if any(character in raw for character in '<>"`'):
        raise ValueError("来源 URL 包含不安全字符")
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise ValueError("来源 URL 无法解析") from exc
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("来源 URL 必须是可访问的 HTTP(S) 直达链接")
    if parts.username or parts.password:
        raise ValueError("来源 URL 不得包含认证信息")

    host = parts.hostname.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if host in RESERVED_SOURCE_HOSTS or host.endswith((".example", ".local")):
        raise ValueError("来源 URL 使用了占位或本地保留域名")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError("来源 URL 不能指向非公网地址")
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if host in SEARCH_HOSTS and path.rstrip("/") in {"", "/search"}:
        raise ValueError("来源 URL 不能是搜索结果页")

    kept_query: list[tuple[str, str]] = []
    for key, query_value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_QUERY_KEYS:
            continue
        kept_query.append((key, query_value))

    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("来源 URL 端口无效") from exc
    netloc = host
    if port and not (
        (parts.scheme.lower() == "http" and port == 80)
        or (parts.scheme.lower() == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    return urlunsplit(
        (
            parts.scheme.lower(),
            netloc,
            path.rstrip("/") or "/",
            urlencode(kept_query, doseq=True),
            "",
        )
    )


def _clean_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValidationPayloadError(f"{field_name} 必须是数组")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            continue
        text = item.strip()
        key = text.casefold()
        if key not in seen:
            seen.add(key)
            cleaned.append(text)
    return cleaned


def _non_empty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 缺失或为空")
    return value.strip()


def _title_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w\u3400-\u9fff]+", "", normalized)


def _validate_item(
    value: Any,
    request: ResearchRequest,
) -> tuple[ValidatedItem, str, str]:
    if not isinstance(value, dict):
        raise ValueError("条目不是对象")
    if set(value) != ITEM_KEYS:
        missing = ITEM_KEYS - set(value)
        extra = set(value) - ITEM_KEYS
        detail = []
        if missing:
            detail.append("缺少字段：" + ", ".join(sorted(missing)))
        if extra:
            detail.append("含未知字段：" + ", ".join(sorted(extra)))
        raise ValueError("；".join(detail))

    raw = RawItem.from_dict(value)
    try:
        module = Module(raw.module)
    except ValueError as exc:
        raise ValueError("条目模块无效") from exc
    if module not in request.modules or module is Module.ALL:
        raise ValueError("条目模块与本次检索不一致")

    title = _non_empty(raw.title, "标题")
    summary = _non_empty(raw.summary, "摘要")
    published_at_original = _non_empty(raw.published_at, "发布时间")
    published_at = parse_published_at(published_at_original)
    comparable_time = published_at.astimezone(request.window.ended_at.tzinfo)
    if not request.window.contains(comparable_time):
        raise ValueError("发布时间不在本次滚动时间窗口内")

    source_name = _non_empty(raw.source_name, "来源名称")
    source_url = _non_empty(raw.source_url, "来源 URL")
    canonical = canonical_url(source_url)
    if raw.source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError("来源类型不符合可靠性策略")
    if type(raw.is_primary_source) is not bool:
        raise ValueError("is_primary_source 必须是布尔值")
    if raw.source_type in {"primary", "official"} and not raw.is_primary_source:
        raise ValueError("一手/官方来源必须标记为一手来源")
    if raw.source_type == "reputable_media" and raw.is_primary_source:
        raise ValueError("媒体报道不能冒充一手来源")
    if raw.confidence not in ALLOWED_CONFIDENCE:
        raise ValueError("置信度必须为 high 或 medium")

    corroborating: list[CorroboratingSource] = []
    for source in raw.corroborating_sources:
        name = _non_empty(source.name, "佐证来源名称")
        url = _non_empty(source.url, "佐证来源 URL")
        clean_url = canonical_url(url)
        if source.source_type not in ALLOWED_SOURCE_TYPES:
            raise ValueError("佐证来源类型不符合可靠性策略")
        corroborating.append(
            CorroboratingSource(
                name=name, url=clean_url, source_type=source.source_type
            )
        )

    return (
        ValidatedItem(
            module=module,
            title=title,
            summary=summary,
            published_at=comparable_time,
            published_at_original=published_at_original,
            event_time_basis=_non_empty(raw.event_time_basis, "时间依据"),
            source_name=source_name,
            source_url=canonical,
            source_type=raw.source_type,
            is_primary_source=raw.is_primary_source,
            evidence=_non_empty(raw.evidence, "证据"),
            relevance=_non_empty(raw.relevance, "主题相关性"),
            why_it_matters=_non_empty(raw.why_it_matters, "重要性"),
            publication_status=_non_empty(raw.publication_status, "发布状态"),
            confidence=raw.confidence,
            corroborating_sources=tuple(corroborating),
        ),
        canonical,
        _title_key(title),
    )


def validate_result(payload: Any, request: ResearchRequest) -> ValidationResult:
    if not isinstance(payload, dict):
        raise ValidationPayloadError("Codex 最终输出必须是 JSON 对象")
    if set(payload) != TOP_LEVEL_KEYS:
        raise ValidationPayloadError("Codex 输出字段与约定的结构不一致")

    expected_modules = request.modules
    payload_module = payload.get("module")
    if len(expected_modules) != 1 or payload_module != expected_modules[0].value:
        raise ValidationPayloadError("Codex 输出的模块与本次检索不一致")

    payload_topic = payload.get("topic")
    if payload_topic is not None and not isinstance(payload_topic, str):
        raise ValidationPayloadError("topic 必须是字符串或 null")
    if payload_topic != request.topic:
        raise ValidationPayloadError("Codex 输出的主题与本次检索不一致")

    items = payload.get("items")
    if not isinstance(items, list):
        raise ValidationPayloadError("items 必须是数组")

    result = ValidationResult(
        search_queries=_clean_list(payload.get("search_queries"), "search_queries"),
        platforms_checked=_clean_list(
            payload.get("platforms_checked"), "platforms_checked"
        ),
    )
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for index, item in enumerate(items, start=1):
        fallback_title = f"第 {index} 条"
        if isinstance(item, dict) and isinstance(item.get("title"), str):
            fallback_title = item["title"].strip() or fallback_title
        try:
            validated, url_key, title_key = _validate_item(item, request)
            if url_key in seen_urls or title_key in seen_titles:
                raise ValueError("与已保留条目重复")
        except (KeyError, TypeError, ValueError) as exc:
            result.excluded.append(
                ValidationIssue(title=fallback_title, reason=str(exc))
            )
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        result.items.append(validated)

    result.items.sort(key=lambda item: item.published_at, reverse=True)
    return result
