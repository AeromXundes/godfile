"""godfile command-line interface."""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, load_config
from .output import render_json, render_sarif, render_text
from .rules import Config, evaluate
from .scanner import CtagsError, extract_typedefs, find_ctags, run_ctags

HEADER_SUFFIXES = {".h", ".hpp", ".hh", ".hxx", ".h++", ".cuh", ".inl", ".ipp"}
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".c++", ".cu"}

# directory names that virtually always hold vendored code, excluded by
# default so a first run isn't swamped by boost's own headers
DEFAULT_EXCLUDES = [
    ".git",
    "third_party",
    "thirdparty",
    "third-party",
    "vendor",
    "vendored",
    "external",
    "externals",
    "extern",
    "deps",
    "bundled",
    "node_modules",
    "boost",
    "gtest",
    "googletest",
    "doctest",
    "catch2",
]


def _excluded(path: str, patterns: list[str]) -> bool:
    """Match *patterns* against the path and each of its parts (dir names)."""
    parts = Path(path).parts
    return any(
        fnmatch.fnmatch(path, pat) or any(fnmatch.fnmatch(part, pat) for part in parts)
        for pat in patterns
    )


def collect_files(
    paths: list[str], include_sources: bool, exclude: list[str] | None = None
) -> list[str]:
    suffixes = HEADER_SUFFIXES | (SOURCE_SUFFIXES if include_sources else set())
    exclude = exclude or []
    files: list[str] = []
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            files.append(str(p))
        elif p.is_dir():
            files.extend(
                str(f)
                for f in sorted(p.rglob("*"))
                if f.is_file()
                and f.suffix.lower() in suffixes
                and not _excluded(str(f), exclude)
            )
        else:
            print(f"godfile: no such path: {raw}", file=sys.stderr)
    return files


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="godfile",
        description=(
            "Detect C/C++ kitchen-sink headers: files that define more "
            "top-level types than the one-type-per-file convention allows."
        ),
    )
    ap.add_argument("paths", nargs="+", help="files or directories to scan")
    ap.add_argument(
        "--max-types",
        type=int,
        default=None,
        metavar="N",
        help="allowed type-score per file; more than this is reported "
        "(default: 1)",
    )
    ap.add_argument(
        "--fail-at",
        type=int,
        default=None,
        metavar="N",
        help="type-score at which a finding becomes an error and fails the run; "
        "findings between --max-types and this are warnings and exit 0 "
        "(default: 4, i.e. 1 clean / 2-3 warning / 4+ error)",
    )
    ap.add_argument(
        "--format",
        choices=["text", "json", "sarif"],
        default="text",
        help="output format (default: text)",
    )
    ap.add_argument(
        "--enum-weight-lines",
        type=int,
        default=None,
        metavar="N",
        help="an enum counts as its line count divided by N, capped at 1.0 — "
        "small enums barely count, an N-line enum counts like a class "
        "(default: 100; use 1 to count every enum as a full type)",
    )
    ap.add_argument(
        "--count-exceptions",
        action="store_true",
        default=None,
        help="count exception types toward the limit "
        "(default: a class plus its exception type is allowed)",
    )
    ap.add_argument(
        "--count-internal",
        action="store_true",
        default=None,
        help="count types in detail/impl/internal namespaces toward the limit",
    )
    ap.add_argument(
        "--sources",
        action="store_true",
        default=None,
        help="also scan source files (.c/.cc/.cpp/...), not just headers",
    )
    ap.add_argument(
        "--exclude",
        action="append",
        default=None,
        metavar="GLOB",
        help="skip paths matching this glob (matches full path or any directory "
        "name; repeatable), e.g. --exclude generated --exclude '*/legacy/*'; "
        "adds to the built-in vendor-directory excludes",
    )
    ap.add_argument(
        "--no-default-excludes",
        action="store_true",
        default=None,
        help="also scan vendored directories (boost, third_party, deps, ...) "
        "that are excluded by default",
    )
    ap.add_argument(
        "--config",
        metavar="PATH",
        help="config file to use instead of searching for .godfilerc / "
        "pyproject.toml [tool.godfile] upward from the working directory",
    )
    ap.add_argument("--ctags-bin", default=None, metavar="PATH",
                    help="universal-ctags binary to use")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        file_cfg = load_config(args.config)
    except ConfigError as e:
        print(f"godfile: {e}", file=sys.stderr)
        return 2

    def opt(name, default):
        """CLI flag wins, then the config file, then the built-in default."""
        cli_value = getattr(args, name)
        return cli_value if cli_value is not None else file_cfg.get(name, default)

    max_types = opt("max_types", 1)
    fail_at = opt("fail_at", 4)
    enum_weight_lines = opt("enum_weight_lines", 100)
    if fail_at <= max_types:
        print(f"godfile: fail-at ({fail_at}) must be greater than "
              f"max-types ({max_types})", file=sys.stderr)
        return 2
    if enum_weight_lines < 1:
        print("godfile: enum-weight-lines must be >= 1", file=sys.stderr)
        return 2

    if args.no_default_excludes:
        use_default_excludes = False
    else:
        use_default_excludes = file_cfg.get("default_excludes", True)
    exclude = (
        (DEFAULT_EXCLUDES if use_default_excludes else [])
        + file_cfg.get("exclude", [])
        + (args.exclude or [])
    )

    files = collect_files(
        args.paths, include_sources=bool(opt("sources", False)), exclude=exclude
    )
    if not files:
        print("godfile: no matching files found", file=sys.stderr)
        return 2

    try:
        ctags_bin = find_ctags(opt("ctags_bin", None))
        tags = run_ctags(ctags_bin, files)
    except CtagsError as e:
        print(f"godfile: {e}", file=sys.stderr)
        return 2

    types_by_file = extract_typedefs(tags)
    config = Config(
        max_types=max_types,
        fail_at=fail_at,
        enum_weight_lines=enum_weight_lines,
        count_exceptions=bool(opt("count_exceptions", False)),
        count_internal=bool(opt("count_internal", False)),
    )
    findings = evaluate(types_by_file, config)

    if args.format == "text":
        print(render_text(findings, len(files)))
    elif args.format == "json":
        print(render_json(findings, len(files)))
    else:
        print(render_sarif(findings))

    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
