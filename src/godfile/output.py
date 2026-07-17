"""Text, JSON, and SARIF 2.1.0 renderers for findings."""

from __future__ import annotations

import json

from . import __version__
from .rules import RULE_ID, RULE_NAME, Finding

TOOL_NAME = "godfile"
TOOL_URI = "https://github.com/AeromXundes/godfile"


def render_text(findings: list[Finding], files_scanned: int) -> str:
    if not findings:
        return f"{files_scanned} file(s) scanned, no kitchen-sink headers found."
    lines = []
    for f in findings:
        lines.append(
            f"{f.file}: {f.severity}: {len(f.counted)} top-level types, "
            f"score {f.score:g} (limit {f.max_types})"
        )
        for t in f.counted:
            lines.append(f"  {t.file}:{t.line}: {t.kind} {t.qualified_name}")
        for t in f.exempt:
            lines.append(
                f"  {t.file}:{t.line}: {t.kind} {t.qualified_name} (exempt)"
            )
    errors = sum(1 for f in findings if f.severity == "error")
    lines.append(
        f"\n{files_scanned} file(s) scanned: {errors} error(s), "
        f"{len(findings) - errors} warning(s)."
    )
    return "\n".join(lines)


def render_json(findings: list[Finding], files_scanned: int) -> str:
    payload = {
        "tool": TOOL_NAME,
        "version": __version__,
        "filesScanned": files_scanned,
        "findings": [
            {
                "file": f.file,
                "severity": f.severity,
                "typeCount": len(f.counted),
                "score": f.score,
                "maxTypes": f.max_types,
                "types": [
                    {
                        "name": t.qualified_name,
                        "kind": t.kind,
                        "line": t.line,
                        "endLine": t.end_line,
                    }
                    for t in f.counted
                ],
                "exemptTypes": [
                    {
                        "name": t.qualified_name,
                        "kind": t.kind,
                        "line": t.line,
                        "reason": "exception-type-or-internal-helper",
                    }
                    for t in f.exempt
                ],
            }
            for f in findings
        ],
    }
    return json.dumps(payload, indent=2)


def _location(uri: str, line: int, message: str | None = None) -> dict:
    loc: dict = {
        "physicalLocation": {
            "artifactLocation": {"uri": uri},
            "region": {"startLine": max(line, 1)},
        }
    }
    if message:
        loc["message"] = {"text": message}
    return loc


def render_sarif(findings: list[Finding]) -> str:
    results = []
    for f in findings:
        type_list = ", ".join(t.qualified_name for t in f.counted)
        # anchor the result at the first type beyond the allowed count
        anchor = f.counted[f.max_types]
        results.append(
            {
                "ruleId": RULE_ID,
                "level": f.severity,
                "message": {
                    "text": (
                        f"File defines {len(f.counted)} top-level types, "
                        f"score {f.score:g} (limit {f.max_types}): {type_list}. "
                        "Consider splitting each type into its own header."
                    )
                },
                "locations": [_location(f.file, anchor.line)],
                "relatedLocations": [
                    _location(f.file, t.line, f"{t.kind} {t.qualified_name}")
                    for t in f.counted
                ],
            }
        )
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": TOOL_NAME,
                        "version": __version__,
                        "informationUri": TOOL_URI,
                        "rules": [
                            {
                                "id": RULE_ID,
                                "name": RULE_NAME,
                                "shortDescription": {
                                    "text": "File defines too many top-level types"
                                },
                                "fullDescription": {
                                    "text": (
                                        "Each class/type should live in its own "
                                        "header. Files accumulating many unrelated "
                                        "top-level types increase compile-time "
                                        "coupling and blur ownership."
                                    )
                                },
                                "defaultConfiguration": {"level": "warning"},
                            }
                        ],
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(sarif, indent=2)
