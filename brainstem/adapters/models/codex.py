"""Supported Codex CLI adapter; unavailable when the executable is absent."""

from __future__ import annotations

import json
import shutil
import subprocess

from .base import Generation, ModelAdapter, ModelHealth


class CodexAdapter(ModelAdapter):
    identity = "codex"

    def __init__(self, executable: str = "codex", cwd: str | None = None) -> None:
        self.executable = executable
        self.cwd = cwd

    def capabilities(self) -> set[str]:
        return (
            {"generate", "repository", "commands", "files"}
            if shutil.which(self.executable)
            else set()
        )

    def health(self) -> ModelHealth:
        path = shutil.which(self.executable)
        if not path:
            return ModelHealth(
                "NOT_CONFIGURED", "Codex CLI executable was not found on PATH."
            )
        result = subprocess.run(  # noqa: S603 -- executable is resolved from PATH
            [path, "--version"], capture_output=True, text=True, timeout=10, check=False
        )
        return ModelHealth(
            "HEALTHY" if result.returncode == 0 else "UNAVAILABLE",
            (result.stdout or result.stderr).strip(),
        )

    def generate(self, messages: list[dict[str, str]]) -> Generation:
        health = self.health()
        if health.status != "HEALTHY":
            raise RuntimeError(f"{health.status}: {health.detail}")
        executable = shutil.which(self.executable)
        if not executable:
            raise RuntimeError("Codex executable disappeared after its health probe")
        prompt = "\n".join(f"{item['role']}: {item['content']}" for item in messages)
        result = subprocess.run(  # noqa: S603 -- executable is resolved from PATH
            [executable, "exec", "--json", prompt],
            cwd=self.cwd,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Codex exited {result.returncode}: {result.stderr.strip()}"
            )
        events = []
        responses = []
        usage: dict[str, int] = {}
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                events.append({"type": "unparsed", "text": line})
                continue
            events.append(event)
            item = event.get("item", event)
            if item.get("type") in {"agent_message", "assistant_message"}:
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    responses.append(text)
            if event.get("type") == "turn.completed" and isinstance(
                event.get("usage"), dict
            ):
                usage = {
                    key: int(value)
                    for key, value in event["usage"].items()
                    if isinstance(value, int)
                }
        if not responses:
            raise RuntimeError(
                "Codex returned no normalized assistant response; raw events retained as telemetry"
            )
        return Generation(
            "\n".join(responses), "codex", usage, {"execution_events": events}
        )
