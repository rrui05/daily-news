from __future__ import annotations

import re
from pathlib import Path

import pytest

from dailynews.cli import input_topic, main, select_module
from dailynews.codex_runner import CodexExecutionError
from dailynews.models import (
    Module,
    ResearchReport,
    ResearchRequest,
    ValidatedItem,
    ValidationResult,
)
from dailynews.policy import create_window
from dailynews.report import render_report, safe_filename, write_report


OPEN_SOURCE_MODULE = getattr(Module, "OPEN_SOURCE", getattr(Module, "OPENSOURCE", None))


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("1", Module.RESEARCH),
        ("2", Module.COMPANIES),
        ("3", OPEN_SOURCE_MODULE),
        ("4", Module.MARKETS),
        ("5", Module.ALL),
    ],
)
def test_select_module_maps_all_five_choices(choice, expected) -> None:
    assert select_module(input_fn=lambda _prompt: choice, output_fn=lambda _message: None) is expected


def test_select_module_reprompts_after_invalid_input() -> None:
    answers = iter(["", "x", "6", "2"])
    messages: list[str] = []

    selected = select_module(
        input_fn=lambda _prompt: next(answers),
        output_fn=messages.append,
    )

    assert selected is Module.COMPANIES
    assert messages


@pytest.mark.parametrize("answer", ["", "  ", "\t"])
def test_input_topic_normalizes_blank_to_none(answer) -> None:
    assert input_topic(input_fn=lambda _prompt: answer) is None


def test_input_topic_trims_but_preserves_unicode() -> None:
    assert input_topic(input_fn=lambda _prompt: "  具身智能 🤖  ") == "具身智能 🤖"


def test_safe_filename_contains_topic_module_time_and_no_windows_illegal_chars(fixed_now) -> None:
    filename = safe_filename("大模型/Agent: R&D?", Module.RESEARCH, fixed_now)

    assert filename.endswith(".md")
    assert "大模型" in filename
    assert Module.RESEARCH.value in filename or "科研" in filename
    assert "20260817" in re.sub(r"[-_]", "", filename)
    assert not any(character in filename for character in '<>:"/\\|?*')
    assert not filename.endswith((". ", " "))
    assert len(filename) <= 200


def test_safe_filename_handles_blank_reserved_and_very_long_topics(fixed_now) -> None:
    blank = safe_filename(None, Module.ALL, fixed_now)
    reserved = safe_filename("CON...   ", Module.MARKETS, fixed_now)
    long_name = safe_filename("新" * 500, OPEN_SOURCE_MODULE, fixed_now)

    assert blank.endswith(".md") and ("不限主题" in blank or "all" in blank.lower())
    assert reserved.upper() != "CON.MD"
    assert not reserved.removesuffix(".md").endswith((".", " "))
    assert len(long_name) <= 200


def _research_report(fixed_now, *, title: str = "第一份") -> ResearchReport:
    request = ResearchRequest(
        module=Module.RESEARCH,
        topic="具身智能",
        window=create_window("具身智能", now=fixed_now),
    )
    item = ValidatedItem(
        module=Module.RESEARCH,
        title=title,
        summary="可核验的研究摘要。",
        published_at=fixed_now,
        published_at_original=fixed_now.isoformat(),
        event_time_basis="arXiv 提交时间。",
        source_name="arXiv",
        source_url="https://arxiv.org/abs/2608.01234",
        source_type="primary",
        is_primary_source=True,
        evidence="摘要报告了可复核的实验结果。",
        relevance="与具身智能直接相关。",
        why_it_matters="推进了相关基准。",
        publication_status="preprint",
        confidence="high",
        corroborating_sources=(),
    )
    return ResearchReport(
        request=request,
        results={Module.RESEARCH: ValidationResult(items=[item])},
    )


def test_render_report_contains_window_item_and_direct_source(fixed_now) -> None:
    markdown = render_report(_research_report(fixed_now))

    assert "具身智能" in markdown
    assert "168 小时" in markdown
    assert "第一份" in markdown
    assert "https://arxiv.org/abs/2608.01234" in markdown
    assert "Asia/Shanghai" in markdown


def test_write_report_creates_utf8_markdown_without_overwriting(tmp_path: Path, fixed_now) -> None:
    output_dir = tmp_path / "reports"
    first = write_report(_research_report(fixed_now, title="第一份"), output_dir)
    second = write_report(_research_report(fixed_now, title="第二份"), output_dir)

    assert first.exists() and second.exists()
    assert first != second
    assert first.parent == output_dir and second.parent == output_dir
    assert "第一份" in first.read_text(encoding="utf-8")
    assert "第二份" in second.read_text(encoding="utf-8")


def test_all_mode_partial_result_writes_honest_report_and_returns_two(tmp_path: Path) -> None:
    class PartialRunner:
        def __init__(self, **_kwargs) -> None:
            pass

        def preflight(self) -> None:
            pass

        def run(self, prompt: str, _schema_path) -> dict:
            for module in ("research", "companies", "opensource", "markets"):
                if f"Canonical module: {module}" not in prompt:
                    continue
                if module == "companies":
                    raise CodexExecutionError("simulated module failure")
                return {
                    "module": module,
                    "topic": "AI",
                    "search_queries": ["AI"],
                    "platforms_checked": ["official.example.invalid"],
                    "items": [],
                }
            raise AssertionError("prompt did not identify a concrete module")

    messages: list[str] = []
    exit_code = main(
        [
            "--module",
            "all",
            "--topic",
            "AI",
            "--output-dir",
            str(tmp_path),
        ],
        output_fn=messages.append,
        runner_factory=PartialRunner,
    )

    reports = list(tmp_path.glob("*.md"))
    assert exit_code == 2
    assert len(reports) == 1
    markdown = reports[0].read_text(encoding="utf-8")
    assert "本模块检索失败" in markdown
    assert any("部分报告" in message for message in messages)
