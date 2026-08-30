"""Hash and substring based contamination controls with explicit residual risk."""

from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Iterable

KINDS = (
    "exact_question",
    "answer_key",
    "distinctive_substring",
    "benchmark_canary",
    "reference_patch",
    "evaluator_logic",
    "hidden_test_artifact",
    "prior_model_answer",
    "solution_repository",
)
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
    ".patch",
    ".diff",
}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class ContaminationScanner:
    def scan(
        self,
        roots: Iterable[Path],
        signatures: dict[str, list[str]],
        exclude_paths: Iterable[Path] = (),
    ) -> dict:
        findings = []
        scanned = 0
        excluded = {path.resolve() for path in exclude_paths}
        normalized = {
            k: [(v, digest(v)) for v in values if len(v) >= 8]
            for k, values in signatures.items()
        }
        for root in roots:
            if not root.exists():
                continue
            files = [root] if root.is_file() else root.rglob("*")
            for path in files:
                if (
                    not path.is_file()
                    or path.is_symlink()
                    or path.suffix.lower() not in TEXT_SUFFIXES
                    or path.resolve() in excluded
                ):
                    continue
                try:
                    if path.stat().st_size > 2_000_000:
                        continue
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                scanned += 1
                for kind, values in normalized.items():
                    for value, value_hash in values:
                        if value in text:
                            findings.append(
                                {
                                    "kind": kind,
                                    "path": str(path),
                                    "signature_hash": value_hash,
                                }
                            )
        unknown = set(signatures) - set(KINDS)
        return {
            "status": "CONTAMINATED" if findings else "NO_KNOWN_CONTAMINATION_DETECTED",
            "officially_clean": False,
            "files_scanned": scanned,
            "findings": findings,
            "controls": list(KINDS),
            "remaining_risk": "Public pretraining and unknown paraphrases cannot be ruled out.",
            "unknown_signature_classes": sorted(unknown),
        }
