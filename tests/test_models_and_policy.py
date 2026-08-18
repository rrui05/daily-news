from __future__ import annotations

from datetime import timedelta
from typing import get_type_hints

import pytest

from dailynews.models import Module, RawItem, ResearchRequest, ValidatedItem
from dailynews.policy import create_window


def test_module_exposes_four_sections_and_all() -> None:
    names = set(Module.__members__)
    assert {"RESEARCH", "COMPANIES", "MARKETS", "ALL"} <= names
    assert {"OPEN_SOURCE", "OPENSOURCE"} & names
    assert len(Module) == 5


@pytest.mark.parametrize("topic", [None, "", "   \t"])
def test_unrestricted_topic_uses_rolling_24_hour_window(topic, fixed_now) -> None:
    window = create_window(topic, now=fixed_now)

    assert window.hours == 24
    assert window.ended_at == fixed_now
    assert window.started_at == fixed_now - timedelta(hours=24)
    assert window.started_at.tzinfo is not None
    assert window.ended_at.tzinfo is not None


def test_restricted_topic_uses_rolling_seven_day_window(fixed_now) -> None:
    window = create_window("具身智能", now=fixed_now)

    assert window.hours == 168
    assert window.ended_at == fixed_now
    assert window.started_at == fixed_now - timedelta(days=7)


def test_model_contract_contains_fields_needed_for_auditable_news() -> None:
    request_fields = get_type_hints(ResearchRequest)
    raw_fields = get_type_hints(RawItem)
    validated_fields = get_type_hints(ValidatedItem)

    assert {"module", "topic", "window"} <= request_fields.keys()
    required_item_fields = {
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
    assert required_item_fields <= raw_fields.keys()
    assert required_item_fields <= validated_fields.keys()


def test_raw_item_can_be_created_from_schema_payload(fixed_now) -> None:
    payload = {
        "module": "research",
        "title": "A verifiable new result",
        "summary": "A concise factual summary.",
        "published_at": fixed_now.isoformat(),
        "event_time_basis": "The primary source records the submission timestamp.",
        "source_name": "arXiv",
        "source_url": "https://arxiv.org/abs/2608.01234",
        "source_type": "primary",
        "is_primary_source": True,
        "evidence": "The abstract reports the measured result.",
        "relevance": "Directly concerns the requested topic.",
        "why_it_matters": "It changes the reported state of the art.",
        "publication_status": "preprint",
        "confidence": "high",
        "corroborating_sources": [],
    }

    item = RawItem.from_dict(payload)

    assert item.title == payload["title"]
    assert item.source_url == payload["source_url"]
