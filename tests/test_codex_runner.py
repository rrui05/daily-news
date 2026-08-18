from __future__ import annotations

from pathlib import Path

from dailynews.codex_runner import CodexRunner


def _flag_value(command: list[str], *flags: str) -> str:
    positions = [command.index(flag) for flag in flags if flag in command]
    assert positions, f"none of {flags!r} found in command: {command!r}"
    position = min(positions)
    return command[position + 1]


def _config_values(command: list[str]) -> list[str]:
    return [
        command[index + 1]
        for index, value in enumerate(command)
        if value in {"-c", "--config"}
    ]


def test_build_command_places_live_search_before_exec(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("dailynews.codex_runner.shutil.which", lambda _binary: "codex")
    schema = tmp_path / "schema with spaces.json"
    output = tmp_path / "last message.json"
    workdir = tmp_path / "work tree"

    command = CodexRunner().build_command(schema, output, workdir)

    # codex-cli 0.147.0 rejects `codex exec --search`; --search is a global flag.
    assert command.index("--search") < command.index("exec")
    assert command.index("--ask-for-approval") < command.index("exec")
    assert command.count("--search") == 1


def test_build_command_is_safe_noninteractive_and_preserves_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("dailynews.codex_runner.shutil.which", lambda _binary: "codex")
    schema = tmp_path / "schema with spaces.json"
    output = tmp_path / "output with spaces.json"
    workdir = tmp_path / "working directory"

    command = CodexRunner().build_command(schema, output, workdir)

    assert "--ephemeral" in command
    assert "--strict-config" in command
    assert 'permissions.dailynews-research.extends=":read-only"' in _config_values(command)
    assert "permissions.dailynews-research.network.enabled=true" in _config_values(command)
    assert 'default_permissions="dailynews-research"' in _config_values(command)
    assert "--sandbox" not in command
    assert "-s" not in command
    assert _flag_value(command, "--ask-for-approval", "-a") == "never"
    assert _flag_value(command, "--output-schema") == str(schema)
    assert _flag_value(command, "--output-last-message", "-o") == str(output)
    assert _flag_value(command, "--cd", "-C") == str(workdir)
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert "--yolo" not in command
