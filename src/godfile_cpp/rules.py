"""The one-type-per-file rule: which types count, and when a file violates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .scanner import TypeDef

RULE_ID = "GF001"
RULE_NAME = "OneTypePerFile"

# namespaces conventionally holding internal-only helpers, matched as exact
# segments or as suffixes (abseil-style container_internal, strings_internal)
INTERNAL_NAMESPACE_SEGMENTS = {"detail", "details", "impl", "internal", "internals"}
INTERNAL_NAMESPACE_SUFFIXES = ("_detail", "_details", "_impl", "_internal", "_internals")

EXCEPTION_NAME_RE = re.compile(r"(Exception|Error)$")
EXCEPTION_BASE_RE = re.compile(r"(exception|error)", re.IGNORECASE)

# family-wide directive: the same comment suppresses any godfile-<lang> tool
IGNORE_FILE_DIRECTIVE = "godfile:ignore-file"


@dataclass
class Config:
    max_types: int = 1
    count_exceptions: bool = False  # count exception types toward the limit
    count_internal: bool = False  # count types in detail/impl namespaces


@dataclass
class Finding:
    file: str
    counted: list[TypeDef]  # types that count toward the limit, sorted by line
    exempt: list[TypeDef]  # types present but exempt (exceptions, detail helpers)
    max_types: int

    @property
    def over_by(self) -> int:
        return len(self.counted) - self.max_types


def is_exception_type(t: TypeDef) -> bool:
    if EXCEPTION_NAME_RE.search(t.name):
        return True
    return any(EXCEPTION_BASE_RE.search(base) for base in t.inherits)


def is_internal_type(t: TypeDef) -> bool:
    for seg in (s.lower() for s in t.namespace.split("::") if s):
        if seg in INTERNAL_NAMESPACE_SEGMENTS or seg.endswith(INTERNAL_NAMESPACE_SUFFIXES):
            return True
    return False


def file_has_ignore_directive(path: str) -> bool:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return IGNORE_FILE_DIRECTIVE in fh.read()
    except OSError:
        return False


def evaluate(
    types_by_file: dict[str, list[TypeDef]], config: Config
) -> list[Finding]:
    """Return one Finding per file that exceeds the configured type limit."""
    findings = []
    for path, defs in sorted(types_by_file.items()):
        counted, exempt = [], []
        for t in defs:
            if not config.count_exceptions and is_exception_type(t):
                exempt.append(t)
            elif not config.count_internal and is_internal_type(t):
                exempt.append(t)
            else:
                counted.append(t)
        if len(counted) <= config.max_types:
            continue
        if file_has_ignore_directive(path):
            continue
        findings.append(
            Finding(file=path, counted=counted, exempt=exempt, max_types=config.max_types)
        )
    return findings
