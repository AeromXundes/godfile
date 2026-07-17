"""godfile command-line interface."""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

from . import __version__
from .output import render_json, render_sarif, render_text
from .rules import Config, evaluate
from .scanner import CtagsError, extract_typedefs, find_ctags, run_ctags

HEADER_SUFFIXES = {".h", ".hpp", ".hh", ".hxx", ".h++", ".cuh", ".inl", ".ipp"}
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".c++", ".cu"}


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
        default=1,
        metavar="N",
        help="allowed top-level types per file (default: 1)",
    )
    ap.add_argument(
        "--format",
        choices=["text", "json", "sarif"],
        default="text",
        help="output format (default: text)",
    )
    ap.add_argument(
        "--count-exceptions",
        action="store_true",
        help="count exception types toward the limit "
        "(default: a class plus its exception type is allowed)",
    )
    ap.add_argument(
        "--count-internal",
        action="store_true",
        help="count types in detail/impl/internal namespaces toward the limit",
    )
    ap.add_argument(
        "--sources",
        action="store_true",
        help="also scan source files (.c/.cc/.cpp/...), not just headers",
    )
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="skip paths matching this glob (matches full path or any directory "
        "name; repeatable), e.g. --exclude 'third_party' --exclude '*/bundled/*'",
    )
    ap.add_argument("--ctags-bin", metavar="PATH", help="universal-ctags binary to use")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    files = collect_files(args.paths, include_sources=args.sources, exclude=args.exclude)
    if not files:
        print("godfile: no matching files found", file=sys.stderr)
        return 2

    try:
        ctags_bin = find_ctags(args.ctags_bin)
        tags = run_ctags(ctags_bin, files)
    except CtagsError as e:
        print(f"godfile: {e}", file=sys.stderr)
        return 2

    types_by_file = extract_typedefs(tags)
    config = Config(
        max_types=args.max_types,
        count_exceptions=args.count_exceptions,
        count_internal=args.count_internal,
    )
    findings = evaluate(types_by_file, config)

    if args.format == "text":
        print(render_text(findings, len(files)))
    elif args.format == "json":
        print(render_json(findings, len(files)))
    else:
        print(render_sarif(findings))

    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
