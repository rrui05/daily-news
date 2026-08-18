"""Command-line interface for Daily News."""

from __future__ import annotations

import argparse
import sys
from importlib import resources
from pathlib import Path
from typing import Callable, Sequence

from . import __version__
from .codex_runner import CodexError, CodexRunner
from .models import MENU_MODULES, Module, ResearchReport, ResearchRequest
from .policy import create_window, normalize_topic
from .prompting import build_prompt
from .report import write_report
from .validation import ValidationPayloadError, validate_result


InputFn = Callable[[str], str]
OutputFn = Callable[[str], None]


def select_module(
    *, input_fn: InputFn = input, output_fn: OutputFn = print
) -> Module:
    output_fn("\n请选择要检索的板块：")
    for key, module in MENU_MODULES.items():
        output_fn(f"  {key}. {module.label}")
    while True:
        choice = input_fn("请输入 1-5：").strip()
        if choice in MENU_MODULES:
            return MENU_MODULES[choice]
        output_fn("无效选项，请输入 1、2、3、4 或 5。")


def input_topic(*, input_fn: InputFn = input) -> str | None:
    return normalize_topic(input_fn("请输入主题（直接回车 = 不限主题）："))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dailynews",
        description="调用本机 Codex 实时检索并生成可核验的每日新闻 Markdown 报告。",
    )
    parser.add_argument(
        "--module",
        choices=[module.value for module in Module],
        help="跳过菜单并选择板块。",
    )
    parser.add_argument(
        "--topic",
        help="跳过主题输入；传入空字符串表示不限主题。",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="报告输出目录（默认：当前目录下的 reports）。",
    )
    parser.add_argument(
        "--model",
        help="可选 Codex 模型；不传时沿用本机 Codex 配置。",
    )
    parser.add_argument(
        "--codex-binary",
        default="codex",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def _configure_console() -> None:
    # Avoid an emoji or an uncommon source name crashing a legacy Windows code page.
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (AttributeError, ValueError):
                pass


def research(
    request: ResearchRequest,
    runner: CodexRunner,
    *,
    output_fn: OutputFn = print,
) -> tuple[ResearchReport, list[str]]:
    results = {}
    failures: list[str] = []
    modules = request.modules

    schema_resource = resources.files("dailynews").joinpath(
        "research_result.schema.json"
    )
    with resources.as_file(schema_resource) as schema_path:
        runner.preflight()
        for index, module in enumerate(modules, start=1):
            output_fn(
                f"[{index}/{len(modules)}] {module.label}：Codex 实时深度检索中，耗时可能较长……"
            )
            child_request = ResearchRequest(
                module=module,
                topic=request.topic,
                window=request.window,
            )
            try:
                payload = runner.run(build_prompt(child_request), schema_path)
                results[module] = validate_result(payload, child_request)
            except (CodexError, ValidationPayloadError) as exc:
                failures.append(f"{module.label}：{exc}")
                if request.module is not Module.ALL:
                    raise
                output_fn(f"  本模块失败，将继续其他模块：{exc}")

    if not results:
        details = "\n".join(failures) or "没有模块返回结果"
        raise CodexError(f"所有检索均失败，未生成报告：\n{details}")
    return ResearchReport(request=request, results=results), failures


def main(
    argv: Sequence[str] | None = None,
    *,
    input_fn: InputFn = input,
    output_fn: OutputFn = print,
    runner_factory=CodexRunner,
) -> int:
    _configure_console()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        module = Module(args.module) if args.module else select_module(
            input_fn=input_fn, output_fn=output_fn
        )
        topic = normalize_topic(args.topic) if args.topic is not None else input_topic(
            input_fn=input_fn
        )
        window = create_window(topic)
        request = ResearchRequest(module=module, topic=topic, window=window)

        output_fn("")
        output_fn(f"主题：{topic or '不限主题'}")
        output_fn(f"模块：{module.label}")
        output_fn(
            "严格时间窗口："
            f"[{window.started_at.isoformat()}, {window.ended_at.isoformat()}] "
            f"（{window.hours} 小时）"
        )
        output_fn("仅保留时间、直达来源和证据均可核验的结果。")

        runner = runner_factory(binary=args.codex_binary, model=args.model)
        report, failures = research(request, runner, output_fn=output_fn)
        output_path = write_report(report, Path(args.output_dir))

        output_fn("")
        if failures:
            output_fn(f"已生成部分报告；{len(failures)} 个模块失败。")
            for failure in failures:
                output_fn(f"- {failure}")
        else:
            output_fn("检索与本地校验完成。")
        output_fn(f"合格条目：{report.total_items}；剔除候选：{report.total_excluded}")
        output_fn(f"报告：{output_path}")
        return 2 if failures else 0
    except (KeyboardInterrupt, EOFError):
        output_fn("\n操作已取消；未完成的检索不会生成报告。")
        return 130
    except (CodexError, ValidationPayloadError, OSError) as exc:
        output_fn(f"\n失败：{exc}")
        output_fn("未生成伪成功报告。")
        return 1


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
