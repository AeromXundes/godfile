"""Enumerate top-level type definitions in C/C++ files via universal-ctags."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field


class CtagsError(RuntimeError):
    pass


# ctags kinds we treat as type definitions
TYPE_KINDS = {"class", "struct", "enum", "union"}
# scopeKinds that make a tag "nested" rather than top-level
NESTING_SCOPE_KINDS = {"class", "struct", "union", "enum", "function", "prototype"}


@dataclass
class TypeDef:
    name: str  # unqualified name
    qualified_name: str  # namespace-qualified name
    kind: str  # class / struct / enum / union / typedef
    file: str
    line: int
    end_line: int | None = None
    inherits: list[str] = field(default_factory=list)
    namespace: str = ""  # enclosing namespace path, "" if global


def find_ctags(explicit: str | None = None) -> str:
    """Locate a universal-ctags binary and verify it supports JSON output."""
    candidates = [explicit] if explicit else ["ctags", "universal-ctags", "uctags"]
    for cand in candidates:
        path = shutil.which(cand)
        if not path:
            continue
        try:
            probe = subprocess.run(
                [path, "--version"], capture_output=True, text=True, timeout=10
            )
        except OSError:
            continue
        if "Universal Ctags" in probe.stdout:
            return path
    raise CtagsError(
        "universal-ctags not found on PATH. Install it (e.g. "
        "`apt install universal-ctags`, `brew install universal-ctags`) "
        "or pass --ctags-bin."
    )


def run_ctags(ctags_bin: str, files: list[str]) -> list[dict]:
    """Run ctags over the given files, return parsed JSON tag records."""
    cmd = [
        ctags_bin,
        "--output-format=json",
        "--languages=C,C++",
        "--kinds-C=gsu,t",
        "--kinds-C++=cgsu,t",
        "--fields=+neKsiZ",
        "--fields-C++=+{template}",
        "-o",
        "-",
        "-L",
        "-",
    ]
    proc = subprocess.run(
        cmd,
        input="\n".join(files),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise CtagsError(f"ctags failed (exit {proc.returncode}): {proc.stderr.strip()}")
    tags = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("_type") == "tag":
            tags.append(rec)
    return tags


def _is_anonymous(rec: dict) -> bool:
    if rec["name"].startswith("__anon"):
        return True
    extras = rec.get("extras", "")
    return "anonymous" in extras.split(",") if extras else False


def extract_typedefs(tags: list[dict]) -> dict[str, list[TypeDef]]:
    """Reduce raw ctags records to top-level type definitions, grouped by file.

    Rules:
    - only kinds in TYPE_KINDS, plus typedefs that name an anonymous type
      (``typedef struct { ... } Point;`` is a real definition)
    - tags nested inside another type or function are dropped
    - anonymous types themselves are dropped (their typedef, if any, counts)
    - duplicates by qualified name (template specializations) collapse to one
    """
    anon_names: set[str] = {
        rec["name"] for rec in tags if rec["kind"] in TYPE_KINDS and _is_anonymous(rec)
    }

    by_file: dict[str, list[TypeDef]] = {}
    seen: set[tuple[str, str]] = set()  # (file, qualified_name)

    for rec in tags:
        kind = rec.get("kind", "")
        scope_kind = rec.get("scopeKind", "")
        scope = rec.get("scope", "")

        if scope_kind in NESTING_SCOPE_KINDS:
            continue

        if kind in TYPE_KINDS:
            if _is_anonymous(rec):
                continue
        elif kind == "typedef":
            # count only typedefs that give a name to an otherwise-anonymous type
            typeref = rec.get("typeref", "")
            target = typeref.split(":", 1)[-1] if typeref else ""
            if not (target in anon_names or target.startswith("__anon")):
                continue
        else:
            continue

        namespace = scope if rec.get("scopeKind") == "namespace" else ""
        qualified = f"{namespace}::{rec['name']}" if namespace else rec["name"]
        key = (rec["path"], qualified)
        if key in seen:
            continue
        seen.add(key)

        inherits_raw = rec.get("inherits", "")
        inherits = [b.strip() for b in inherits_raw.split(",") if b.strip()] if inherits_raw else []

        by_file.setdefault(rec["path"], []).append(
            TypeDef(
                name=rec["name"],
                qualified_name=qualified,
                kind=kind,
                file=rec["path"],
                line=rec.get("line", 0),
                end_line=rec.get("end"),
                inherits=inherits,
                namespace=namespace,
            )
        )

    for defs in by_file.values():
        defs.sort(key=lambda t: t.line)
    return by_file
