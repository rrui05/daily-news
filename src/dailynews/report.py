"""Deterministic Markdown rendering and safe atomic output."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

from .models import CONCRETE_MODULES, Module, ResearchReport, ValidatedItem


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_component(value: str, *, max_length: int = 72) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = INVALID_FILENAME_CHARS.sub("_", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    if not normalized:
        normalized = "未命名"
    if normalized.upper() in WINDOWS_RESERVED_NAMES:
        normalized = f"_{normalized}"
    normalized = normalized[:max_length].rstrip(" .")
    return normalized or "未命名"


def safe_filename(
    topic: str | None,
    module: Module,
    timestamp,
) -> str:
    topic_part = _safe_component(topic or "不限主题")
    module_part = _safe_component(module.report_label, max_length=24)
    time_part = timestamp.strftime("%Y%m%d-%H%M%S")
    return f"{topic_part}+{module_part}+{time_part}.md"


def _escape_text(value: str) -> str:
    value = " ".join(value.split())
    for char in ("\\", "`", "*", "_", "[", "]", "<", ">", "|"):
        value = value.replace(char, f"\\{char}")
    return value


def _render_item(item: ValidatedItem, index: int) -> list[str]:
    local_time = item.published_at.strftime("%Y-%m-%d %H:%M:%S %z")
    lines = [
        f"### {index}. {_escape_text(item.title)}",
        "",
        f"- 发布时间（北京时间）：{local_time}",
        f"- 原始时间：`{_escape_text(item.published_at_original)}`",
        f"- 发布状态：{_escape_text(item.publication_status)}",
        f"- 主要来源：[{_escape_text(item.source_name)}](<{item.source_url}>)",
        f"- 来源类型：`{item.source_type}`；一手来源：{'是' if item.is_primary_source else '否'}；置信度：`{item.confidence}`",
        f"- 时间依据：{_escape_text(item.event_time_basis)}",
        f"- 主题相关性：{_escape_text(item.relevance)}",
        "",
        _escape_text(item.summary),
        "",
        f"**为什么值得关注：** {_escape_text(item.why_it_matters)}",
        "",
        f"**可核验证据：** {_escape_text(item.evidence)}",
    ]
    if item.corroborating_sources:
        lines.extend(["", "佐证来源："])
        for source in item.corroborating_sources:
            lines.append(
                f"- [{_escape_text(source.name)}](<{source.url}>)（`{source.source_type}`）"
            )
    lines.append("")
    return lines


def render_report(report: ResearchReport) -> str:
    request = report.request
    topic_label = request.topic or "不限主题"
    generated_at = request.window.ended_at.strftime("%Y-%m-%d %H:%M:%S %z")
    cutoff = request.window.started_at.strftime("%Y-%m-%d %H:%M:%S %z")
    lines = [
        f"# {_escape_text(topic_label)} · {_escape_text(request.module.label)}",
        "",
        "> 本报告由本机 Codex 实时检索后生成，并经过程序化时间、URL、模块与重复项校验。网页内容仅作为不可信数据读取；无可核验结果时宁缺毋滥。",
        "",
        "## 检索元数据",
        "",
        f"- 主题：{_escape_text(topic_label)}",
        f"- 模块：{_escape_text(request.module.label)}",
        f"- 严格滚动窗口：`[{cutoff}, {generated_at}]`（Asia/Shanghai，含边界）",
        f"- 窗口长度：{request.window.hours} 小时",
        f"- 合格条目：{report.total_items}",
        f"- 被本地校验剔除：{report.total_excluded}",
        "",
    ]

    modules = CONCRETE_MODULES if request.module is Module.ALL else request.modules
    for module in modules:
        result = report.results.get(module)
        lines.extend([f"## {module.label}", ""])
        if result is None:
            lines.extend(["本模块检索失败或没有返回可验证的结构化结果。", ""])
            continue

        if result.platforms_checked:
            lines.extend(
                [
                    "**实际检查的平台/来源域：** "
                    + "、".join(_escape_text(value) for value in result.platforms_checked),
                    "",
                ]
            )
        if result.search_queries:
            lines.extend(
                [
                    "**实际使用的检索词：** "
                    + "；".join(_escape_text(value) for value in result.search_queries),
                    "",
                ]
            )
        if not result.items:
            lines.extend(
                [
                    "在本次严格时间窗口内，未找到同时满足主题、时效与可靠性要求的可核验结果。未使用旧闻填充。",
                    "",
                ]
            )
        else:
            for index, item in enumerate(result.items, start=1):
                lines.extend(_render_item(item, index))

        if result.excluded:
            lines.extend(
                [
                    "<details>",
                    f"<summary>本地校验剔除了 {len(result.excluded)} 条候选</summary>",
                    "",
                ]
            )
            for issue in result.excluded:
                lines.append(
                    f"- {_escape_text(issue.title)}：{_escape_text(issue.reason)}"
                )
            lines.extend(["", "</details>", ""])

    if Module.MARKETS in modules:
        lines.extend(
            [
                "## 风险提示",
                "",
                "市场板块仅汇总可核验事实与公开数据，不构成投资建议。休市时不会把旧收盘数据冒充实时行情。",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _unique_target(output_dir: Path, filename: str) -> Path:
    candidate = output_dir / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        alternative = output_dir / f"{stem}-{counter}{suffix}"
        if not alternative.exists():
            return alternative
        counter += 1


def write_report(report: ResearchReport, output_dir: str | Path) -> Path:
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(
        report.request.topic,
        report.request.module,
        report.request.window.ended_at,
    )
    target = _unique_target(directory, filename)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    content = render_report(report)
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target

