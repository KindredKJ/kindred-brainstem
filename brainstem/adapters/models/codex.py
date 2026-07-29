"""Supported Codex CLI adapter; unavailable when the executable is absent."""

from __future__ import annotations

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
        result = subprocess.run(
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
        prompt = "\n".join(f"{item['role']}: {item['content']}" for item in messages)
        result = subprocess.run(
            [self.executable, "exec", "--json", prompt],
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
        return Generation(result.stdout, "codex", {})
