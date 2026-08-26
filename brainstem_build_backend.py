"""Minimal dependency-free PEP 517 backend for BRAINSTEM distributions."""

from __future__ import annotations

import base64
import hashlib
import io
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any


def _project() -> dict[str, Any]:
    with Path("pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]


def _names() -> tuple[str, str, str]:
    project = _project()
    name = project["name"].replace("-", "_")
    version = project["version"]
    return name, version, f"{name}-{version}.dist-info"


def _metadata_text() -> str:
    project = _project()
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {project['name']}",
        f"Version: {project['version']}",
        f"Summary: {project['description']}",
        f"Requires-Python: {project['requires-python']}",
    ]
    lines.extend(f"Requires-Dist: {item}" for item in project["dependencies"])
    for extra, dependencies in project.get("optional-dependencies", {}).items():
        lines.append(f"Provides-Extra: {extra}")
        lines.extend(
            f'Requires-Dist: {item}; extra == "{extra}"' for item in dependencies
        )
    return "\n".join(lines) + "\n"


def _metadata(base: str | Path) -> str:
    _, _, dist = _names()
    directory = Path(base) / dist
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "METADATA").write_text(_metadata_text(), encoding="utf-8")
    (directory / "WHEEL").write_text(
        "Wheel-Version: 1.0\n"
        "Generator: brainstem-build-backend\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n",
        encoding="utf-8",
    )
    scripts = _project()["scripts"]
    entries = "\n".join(f"{name} = {target}" for name, target in scripts.items())
    (directory / "entry_points.txt").write_text(
        f"[console_scripts]\n{entries}\n", encoding="utf-8"
    )
    (directory / "RECORD").write_text("", encoding="utf-8")
    return dist


def _metadata_files() -> list[tuple[str, bytes]]:
    _, _, dist = _names()
    scripts = _project()["scripts"]
    entries = "\n".join(f"{name} = {target}" for name, target in scripts.items())
    return [
        (f"{dist}/METADATA", _metadata_text().encode()),
        (
            f"{dist}/WHEEL",
            (
                b"Wheel-Version: 1.0\n"
                b"Generator: brainstem-build-backend\n"
                b"Root-Is-Purelib: true\n"
                b"Tag: py3-none-any\n"
            ),
        ),
        (f"{dist}/entry_points.txt", f"[console_scripts]\n{entries}\n".encode()),
        (f"{dist}/RECORD", b""),
    ]


def prepare_metadata_for_build_editable(
    metadata_directory: str, config_settings: dict[str, Any] | None = None
) -> str:
    return _metadata(metadata_directory)


def prepare_metadata_for_build_wheel(
    metadata_directory: str, config_settings: dict[str, Any] | None = None
) -> str:
    return _metadata(metadata_directory)


def get_requires_for_build_editable(
    config_settings: dict[str, Any] | None = None,
) -> list[str]:
    return []


def get_requires_for_build_wheel(
    config_settings: dict[str, Any] | None = None,
) -> list[str]:
    return []


def get_requires_for_build_sdist(
    config_settings: dict[str, Any] | None = None,
) -> list[str]:
    return []


def build_editable(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    return build_wheel(
        wheel_directory, config_settings, metadata_directory, editable=True
    )


def build_wheel(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
    editable: bool = False,
) -> str:
    name, version, dist = _names()
    wheel = Path(wheel_directory) / f"{name}-{version}-py3-none-any.whl"
    wheel.parent.mkdir(parents=True, exist_ok=True)
    files: list[tuple[str, bytes]] = []
    if editable:
        files.append(("kindred_brainstem_editable.pth", f"{Path.cwd()}\n".encode()))
    else:
        files.extend(
            (path.as_posix(), path.read_bytes())
            for path in sorted(Path("brainstem").rglob("*.py"))
        )
    metadata_root = Path(metadata_directory) / dist if metadata_directory else None
    if metadata_root is None or not metadata_root.exists():
        metadata_files = _metadata_files()
    else:
        metadata_files = [
            (f"{dist}/{path.name}", path.read_bytes())
            for path in sorted(metadata_root.iterdir())
        ]
    record_lines = []
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as archive:
        for archive_name, data in files + [
            item for item in metadata_files if not item[0].endswith("/RECORD")
        ]:
            archive.writestr(archive_name, data)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
            record_lines.append(
                f"{archive_name},sha256={digest.rstrip(b'=').decode()},{len(data)}"
            )
        record_lines.append(f"{dist}/RECORD,,")
        archive.writestr(f"{dist}/RECORD", "\n".join(record_lines) + "\n")
    return wheel.name


def build_sdist(
    sdist_directory: str, config_settings: dict[str, Any] | None = None
) -> str:
    name, version, _ = _names()
    archive_name = f"{name}-{version}.tar.gz"
    destination = Path(sdist_directory) / archive_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    root = f"{name}-{version}"
    included = [
        Path("pyproject.toml"),
        Path("README.md"),
        Path("brainstem_build_backend.py"),
        *sorted(Path("brainstem").rglob("*.py")),
    ]
    with tarfile.open(destination, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in included:
            archive.add(path, arcname=f"{root}/{path.as_posix()}")
        metadata = _metadata_text().encode()
        info = tarfile.TarInfo(f"{root}/PKG-INFO")
        info.size = len(metadata)
        archive.addfile(info, io.BytesIO(metadata))
    return archive_name
