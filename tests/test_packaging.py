import email.parser
import os
import site
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import brainstem_build_backend as backend


def requirements(metadata: str) -> set[str]:
    parsed = email.parser.Parser().parsestr(metadata)
    return {
        requirement
        for requirement in parsed.get_all("Requires-Dist", [])
        if ";" not in requirement
    }


def test_wheel_and_sdist_metadata_match_runtime_dependencies(tmp_path):
    wheel_name = backend.build_wheel(str(tmp_path))
    sdist_name = backend.build_sdist(str(tmp_path))
    with Path("pyproject.toml").open("rb") as stream:
        expected = set(tomllib.load(stream)["project"]["dependencies"])
    with zipfile.ZipFile(tmp_path / wheel_name) as wheel:
        metadata_name = next(
            name for name in wheel.namelist() if name.endswith("/METADATA")
        )
        wheel_requirements = requirements(wheel.read(metadata_name).decode())
    with tarfile.open(tmp_path / sdist_name) as sdist:
        pkg_info = next(
            member for member in sdist.getmembers() if member.name.endswith("/PKG-INFO")
        )
        extracted = sdist.extractfile(pkg_info)
        assert extracted is not None
        sdist_requirements = requirements(extracted.read().decode())
    assert wheel_requirements == expected
    assert sdist_requirements == expected
    assert "cryptography>=46.0.0" in expected


def test_built_wheel_installs_and_imports_outside_source_tree(tmp_path):
    wheel_name = backend.build_wheel(str(tmp_path))
    environment = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--system-site-packages", str(environment)],
        check=True,
    )
    executable = environment / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    subprocess.run(
        [
            str(executable),
            "-m",
            "pip",
            "install",
            "--no-deps",
            str(tmp_path / wheel_name),
        ],
        check=True,
        cwd=tmp_path,
    )
    installed_site = subprocess.run(
        [str(executable), "-c", "import site; print(site.getsitepackages()[0])"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    smoke_environment = os.environ.copy()
    smoke_environment["PYTHONPATH"] = site.getsitepackages()[-1]
    smoke_environment["BRAINSTEM_SMOKE_SITE_PACKAGES"] = installed_site
    subprocess.run(
        [
            str(executable),
            "-c",
            "import os, pathlib; import brainstem; import brainstem.model.authority; import brainstem.runtime.app; import brainstem.strata.gateway; package = pathlib.Path(brainstem.__file__).resolve(); expected = pathlib.Path(os.environ['BRAINSTEM_SMOKE_SITE_PACKAGES']).resolve(); assert expected in package.parents, (package, expected)",
        ],
        check=True,
        cwd=tmp_path,
        env=smoke_environment,
    )
