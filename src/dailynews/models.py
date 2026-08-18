"""Core value objects used across the application."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Module(str, Enum):
    RESEARCH = "research"
    COMPANIES = "companies"
    OPENSOURCE = "opensource"
    MARKETS = "markets"
    ALL = "all"

    @property
    def label(self) -> str:
        return MODULE_LABELS[self]

    @property
    def report_label(self) -> str:
        return MODULE_REPORT_LABELS[self]

    @property
    def concrete_modules(self) -> tuple["Module", ...]:
        if self is Module.ALL:
            return CONCRETE_MODULES
        return (self,)


CONCRETE_MODULES: tuple[Module, ...] = (
    Module.RESEARCH,
    Module.COMPANIES,
    Module.OPENSOURCE,
    Module.MARKETS,
)

MODULE_LABELS: dict[Module, str] = {
    Module.RESEARCH: "最新科研进展",
    Module.COMPANIES: "最新科技企业新闻",
    Module.OPENSOURCE: "最新潜力开源项目",
    Module.MARKETS: "最新市场新闻",
    Module.ALL: "全部板块",
}

MODULE_REPORT_LABELS: dict[Module, str] = {
    Module.RESEARCH: "科研进展",
    Module.COMPANIES: "科技企业",
    Module.OPENSOURCE: "开源项目",
    Module.MARKETS: "市场新闻",
    Module.ALL: "全部",
}

MENU_MODULES: dict[str, Module] = {
    "1": Module.RESEARCH,
    "2": Module.COMPANIES,
    "3": Module.OPENSOURCE,
    "4": Module.MARKETS,
    "5": Module.ALL,
}


@dataclass(frozen=True, slots=True)
class ResearchWindow:
    started_at: datetime
    ended_at: datetime

    @property
    def hours(self) -> int:
        return round((self.ended_at - self.started_at).total_seconds() / 3600)

    def contains(self, value: datetime) -> bool:
        return self.started_at <= value <= self.ended_at


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    module: Module
    topic: str | None
    window: ResearchWindow

    @property
    def modules(self) -> tuple[Module, ...]:
        return self.module.concrete_modules


@dataclass(frozen=True, slots=True)
class CorroboratingSource:
    name: str
    url: str
    source_type: str


@dataclass(frozen=True, slots=True)
class RawItem:
    module: str
    title: str
    summary: str
    published_at: str
    event_time_basis: str
    source_name: str
    source_url: str
    source_type: str
    is_primary_source: bool
    evidence: str
    relevance: str
    why_it_matters: str
    publication_status: str
    confidence: str
    corroborating_sources: tuple[CorroboratingSource, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RawItem":
        corroborating = tuple(
            CorroboratingSource(
                name=str(source["name"]),
                url=str(source["url"]),
                source_type=str(source["source_type"]),
            )
            for source in value.get("corroborating_sources", [])
        )
        return cls(
            module=str(value["module"]),
            title=str(value["title"]),
            summary=str(value["summary"]),
            published_at=str(value["published_at"]),
            event_time_basis=str(value["event_time_basis"]),
            source_name=str(value["source_name"]),
            source_url=str(value["source_url"]),
            source_type=str(value["source_type"]),
            is_primary_source=value["is_primary_source"],
            evidence=str(value["evidence"]),
            relevance=str(value["relevance"]),
            why_it_matters=str(value["why_it_matters"]),
            publication_status=str(value["publication_status"]),
            confidence=str(value["confidence"]),
            corroborating_sources=corroborating,
        )


@dataclass(frozen=True, slots=True)
class ValidatedItem:
    module: Module
    title: str
    summary: str
    published_at: datetime
    published_at_original: str
    event_time_basis: str
    source_name: str
    source_url: str
    source_type: str
    is_primary_source: bool
    evidence: str
    relevance: str
    why_it_matters: str
    publication_status: str
    confidence: str
    corroborating_sources: tuple[CorroboratingSource, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    title: str
    reason: str


@dataclass(slots=True)
class ValidationResult:
    items: list[ValidatedItem] = field(default_factory=list)
    excluded: list[ValidationIssue] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    platforms_checked: list[str] = field(default_factory=list)

    @property
    def raw_count(self) -> int:
        return len(self.items) + len(self.excluded)

    @property
    def valid_count(self) -> int:
        return len(self.items)


@dataclass(slots=True)
class ResearchReport:
    request: ResearchRequest
    results: dict[Module, ValidationResult]

    @property
    def total_items(self) -> int:
        return sum(result.valid_count for result in self.results.values())

    @property
    def total_excluded(self) -> int:
        return sum(len(result.excluded) for result in self.results.values())

