from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
ENGINE_ROOT = ROOT / "brainstem" / "engines"
REPORT_PATH = ROOT / "generated" / "reports" / "module_integration_audit.md"


def classify_file(path: Path) -> str:
    if not path.exists():
        return "missing"

    text = path.read_text(encoding="utf-8", errors="ignore")
    meaningful = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
        and not line.strip().startswith("#")
        and line.strip() not in {"pass", "..."}
    ]

    if len(meaningful) == 0:
        return "empty"
    if len(meaningful) < 5:
        return "stub"
    if len(meaningful) < 15:
        return "partial"
    return "implemented"


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    if ENGINE_ROOT.exists():
        for engine_dir in sorted([p for p in ENGINE_ROOT.iterdir() if p.is_dir()]):
            py_files = sorted(engine_dir.glob("*.py"))

            if not py_files:
                status = "empty"
                detail = "no python files"
            else:
                classifications = [classify_file(p) for p in py_files]
                if "implemented" in classifications:
                    status = "partial" if any(c in {"empty", "stub"} for c in classifications) else "implemented"
                elif "partial" in classifications:
                    status = "partial"
                elif "stub" in classifications:
                    status = "stub"
                else:
                    status = "empty"

                detail = ", ".join(f"{p.name}:{classify_file(p)}" for p in py_files)

            rows.append((engine_dir.name, status, detail))

    lines = [
        "# BRAINSTEM Module Integration Audit",
        "",
        "This report classifies engine implementation depth. It does not prove production readiness.",
        "",
        "| Engine | Status | Detail |",
        "|---|---|---|",
    ]

    for name, status, detail in rows:
        safe_detail = detail.replace("|", "/")
        lines.append(f"| {name} | {status} | {safe_detail} |")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("BRAINSTEM Module Integration Audit")
    print("----------------------------------")
    for name, status, _ in rows:
        print(f"{name:42} {status}")
    print(f"\nWrote: {REPORT_PATH}")


if __name__ == "__main__":
    main()
