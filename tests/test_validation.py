from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from dailynews.models import Module, ResearchRequest, ValidatedItem
from dailynews.policy import create_window
from dailynews.validation import ValidationPayloadError, validate_result


def _request(module: Module, topic: str | None, now) -> ResearchRequest:
    return ResearchRequest(
        module=module,
        topic=topic,
        window=create_window(topic, now=now),
    )


def _item(*, published_at, module: str = "research", url: str = "https://arxiv.org/abs/2608.01234") -> dict[str, Any]:
    return {
        "module": module,
        "title": "A verifiable new result",
        "summary": "The paper reports a measurable improvement and links to the primary source.",
        "published_at": published_at.isoformat() if hasattr(published_at, "isoformat") else published_at,
        "event_time_basis": "The primary source records the submission timestamp.",
        "source_name": "arXiv",
        "source_url": url,
        "source_type": "primary",
        "is_primary_source": True,
        "evidence": "The abstract reports the measured result.",
        "relevance": "Directly concerns the requested topic.",
        "why_it_matters": "It changes the reported state of the art.",
        "publication_status": "preprint",
        "confidence": "high",
        "corroborating_sources": [],
    }


def _payload(request: ResearchRequest, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "module": request.module.value,
        "topic": request.topic,
        "search_queries": [request.topic or "latest news"],
        "platforms_checked": ["arxiv.org"],
        "items": items,
    }


def test_valid_item_is_typed_and_accepted(fixed_now) -> None:
    request = _request(Module.RESEARCH, None, fixed_now)
    payload = _payload(request, [_item(published_at=fixed_now - timedelta(hours=1))])

    result = validate_result(payload, request)

    assert result.raw_count == 1
    assert result.valid_count == 1
    assert result.excluded == []
    assert len(result.items) == 1
    assert isinstance(result.items[0], ValidatedItem)
    assert result.items[0].published_at.tzinfo is not None


@pytest.mark.parametrize("source_type", ["social", "official_social"])
def test_social_source_does_not_have_to_be_official_or_primary(
    fixed_now, source_type
) -> None:
    request = _request(Module.COMPANIES, None, fixed_now)
    item = _item(
        published_at=fixed_now - timedelta(hours=1),
        module="companies",
        url="https://x.com/example/status/123456789",
    )
    item.update(
        source_name="X post",
        source_type=source_type,
        is_primary_source=False,
        publication_status="social_post",
    )

    result = validate_result(_payload(request, [item]), request)

    assert result.valid_count == 1
    assert result.excluded == []
    assert result.items[0].source_type == source_type
    assert result.items[0].is_primary_source is False


def test_freshness_window_is_inclusive_but_rejects_old_and_future_items(fixed_now) -> None:
    request = _request(Module.RESEARCH, None, fixed_now)
    payload = _payload(
        request,
        [
            _item(published_at=request.window.started_at, url="https://arxiv.org/abs/2608.00001"),
            _item(
                published_at=request.window.started_at - timedelta(seconds=1),
                url="https://arxiv.org/abs/2608.00002",
            ),
            _item(
                published_at=request.window.ended_at + timedelta(seconds=1),
                url="https://arxiv.org/abs/2608.00003",
            ),
        ],
    )

    result = validate_result(payload, request)

    assert result.raw_count == 3
    assert result.valid_count == 1
    assert len(result.excluded) == 2
    assert [item.source_url for item in result.items] == ["https://arxiv.org/abs/2608.00001"]


@pytest.mark.parametrize(
    "bad_item",
    [
        {"published_at": "2026-08-17T10:00:00+08:00"},
        _item(published_at="2026-08-17", url="https://arxiv.org/abs/2608.00004"),
        _item(published_at="2026-08-17T10:00:00+08:00", url=""),
        _item(published_at="2026-08-17T10:00:00+08:00", url="https://example.com/news"),
        _item(
            published_at="2026-08-17T10:00:00+08:00",
            url="https://arxiv.org/abs/unsafe url",
        ),
    ],
)
def test_unverifiable_or_imprecise_items_are_not_accepted(fixed_now, bad_item) -> None:
    request = _request(Module.RESEARCH, None, fixed_now)

    result = validate_result(_payload(request, [bad_item]), request)

    assert result.raw_count == 1
    assert result.valid_count == 0
    assert result.items == []
    assert len(result.excluded) == 1


def test_duplicates_are_collapsed_by_canonical_source_url(fixed_now) -> None:
    request = _request(Module.RESEARCH, "AI", fixed_now)
    item = _item(published_at=fixed_now - timedelta(hours=2))

    result = validate_result(_payload(request, [item, dict(item)]), request)

    assert result.raw_count == 2
    assert result.valid_count == 1
    assert len(result.items) == 1
    assert len(result.excluded) == 1


def test_selected_module_rejects_cross_module_items(fixed_now) -> None:
    market_item = _item(
        published_at=fixed_now - timedelta(hours=1),
        module="markets",
        url="https://www.sse.com.cn/market/announcement",
    )
    market_item.update(
        source_name="上海证券交易所",
        source_type="official",
        event_time_basis="交易所公告记录了事件时间。",
        evidence="公告给出了可核验的市场事件。",
        publication_status="official",
    )

    research_request = _request(Module.RESEARCH, None, fixed_now)
    research_payload = _payload(research_request, [market_item])
    research_only = validate_result(research_payload, research_request)

    assert research_only.items == []
    assert research_only.valid_count == 0
    assert len(research_only.excluded) == 1


def test_each_concrete_module_can_be_validated_after_all_selection_is_split(fixed_now) -> None:
    market_request = _request(Module.MARKETS, None, fixed_now)
    market_item = _item(
        published_at=fixed_now - timedelta(hours=1),
        module="markets",
        url="https://www.sse.com.cn/market/announcement",
    )
    market_item.update(
        source_name="上海证券交易所",
        source_type="official",
        event_time_basis="交易所公告记录了事件时间。",
        evidence="公告给出了可核验的市场事件。",
        publication_status="official",
    )

    result = validate_result(_payload(market_request, [market_item]), market_request)

    assert result.valid_count == 1
    assert result.items[0].module is Module.MARKETS


def test_empty_result_stays_empty_instead_of_inventing_fillers(fixed_now) -> None:
    request = _request(Module.RESEARCH, None, fixed_now)

    result = validate_result(_payload(request, []), request)

    assert result.items == []
    assert result.excluded == []
    assert result.raw_count == 0
    assert result.valid_count == 0


@pytest.mark.parametrize("payload", [None, [], {}, {"items": []}])
def test_malformed_top_level_payload_is_rejected(fixed_now, payload) -> None:
    request = _request(Module.RESEARCH, None, fixed_now)

    with pytest.raises(ValidationPayloadError):
        validate_result(payload, request)
