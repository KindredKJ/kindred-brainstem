"""Global and repository-local state resolution."""

from pathlib import Path


def global_state_dir() -> Path:
    return Path.home() / ".kindred"


def repository_root(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for path in (current, *current.parents):
        if (path / ".git").exists():
            return path
    return None


def repository_state_dir(start: Path | None = None) -> Path | None:
    root = repository_root(start)
    return root / ".kindred" if root else None
