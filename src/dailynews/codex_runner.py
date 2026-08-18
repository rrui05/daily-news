"""Safe subprocess adapter for the locally authenticated Codex CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping


class CodexError(RuntimeError):
    pass


class CodexNotFoundError(CodexError):
    pass


class CodexAuthenticationError(CodexError):
    pass


class CodexExecutionError(CodexError):
    pass


class CodexOutputError(CodexError):
    pass


_RESEARCH_PERMISSION_PROFILE = "dailynews-research"


class CodexRunner:
    def __init__(
        self,
        binary: str = "codex",
        *,
        model: str | None = None,
        timeout: float | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.binary = binary
        self.model = model
        self.timeout = timeout
        self.environ = dict(environ) if environ is not None else None
        self._preflight_complete = False

    def _resolved_binary(self) -> str:
        candidate = Path(self.binary)
        if candidate.parent != Path(".") or candidate.is_absolute():
            if candidate.is_file():
                return str(candidate)
        resolved = shutil.which(self.binary)
        if not resolved:
            raise CodexNotFoundError(
                "未找到 Codex CLI。请先安装 Codex，并确认 `codex --version` 可运行。"
            )
        return resolved

    def preflight(self) -> None:
        if self._preflight_complete:
            return
        binary = self._resolved_binary()
        try:
            completed = subprocess.run(
                [binary, "login", "status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
                env=self.environ,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CodexExecutionError(f"Codex 登录状态检查失败：{exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise CodexAuthenticationError(
                "Codex 尚未登录。请先运行 `codex login`。"
                + (f"\n详情：{detail}" if detail else "")
            )
        self._preflight_complete = True

    def build_command(
        self,
        schema_path: str | Path,
        output_path: str | Path,
        workdir: str | Path,
    ) -> list[str]:
        # Codex's legacy `read-only` sandbox also disables command networking.
        # A custom permission profile keeps the filesystem read-only while
        # independently enabling outbound access for API-backed research skills.
        # These are global options and therefore must precede `exec`.
        command = [
            self._resolved_binary(),
            "--strict-config",
            "-c",
            f'permissions.{_RESEARCH_PERMISSION_PROFILE}.extends=":read-only"',
            "-c",
            f"permissions.{_RESEARCH_PERMISSION_PROFILE}.network.enabled=true",
            "-c",
            f'default_permissions="{_RESEARCH_PERMISSION_PROFILE}"',
            "--ask-for-approval",
            "never",
            "--search",
        ]
        if self.model:
            command.extend(["--model", self.model])
        command.extend(
            [
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--color",
                "never",
                "-C",
                str(Path(workdir).resolve()),
                "--output-schema",
                str(Path(schema_path).resolve()),
                "--output-last-message",
                str(Path(output_path).resolve()),
                "-",
            ]
        )
        return command

    def run(self, prompt: str, schema_path: str | Path) -> dict[str, Any]:
        self.preflight()
        with tempfile.TemporaryDirectory(prefix="dailynews-codex-") as temp_dir:
            workdir = Path(temp_dir)
            output_path = workdir / "result.json"
            command = self.build_command(schema_path, output_path, workdir)
            try:
                process = subprocess.run(
                    command,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout,
                    check=False,
                    env=self.environ,
                    cwd=workdir,
                )
            except FileNotFoundError as exc:
                raise CodexNotFoundError("Codex CLI 在启动时消失或不可执行。") from exc
            except subprocess.TimeoutExpired as exc:
                raise CodexExecutionError(
                    "Codex 检索超过了显式设置的超时时间，未生成报告。"
                ) from exc
            except OSError as exc:
                raise CodexExecutionError(f"无法启动 Codex：{exc}") from exc

            if process.returncode != 0:
                detail = (process.stderr or process.stdout).strip()
                lowered = detail.casefold()
                if "login" in lowered or "auth" in lowered or "unauthorized" in lowered:
                    raise CodexAuthenticationError(
                        "Codex 认证失效，请运行 `codex login` 后重试。"
                    )
                concise = detail[-2000:] if detail else "无错误详情"
                raise CodexExecutionError(
                    f"Codex 检索失败（退出码 {process.returncode}）：\n{concise}"
                )

            if not output_path.is_file() or output_path.stat().st_size == 0:
                raise CodexOutputError("Codex 未返回结构化结果，未生成报告。")
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CodexOutputError("Codex 返回内容不是有效的 UTF-8 JSON。") from exc
            if not isinstance(payload, dict):
                raise CodexOutputError("Codex 结构化结果顶层必须是对象。")
            return payload
