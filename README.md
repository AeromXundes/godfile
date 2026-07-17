# godfile

**Finds the god files in your C/C++ codebase** — kitchen-sink headers that
define more top-level types than the one-type-per-file convention allows.

Large, long-lived C++ codebases accumulate "kitchen sink" headers: a file that
starts with one utility class and grows for years as developers bolt on "just
one more small helper." Eventually a single header holds a dozen unrelated
types — a mutex, a socket wrapper, string helpers, date math, a scope guard —
with no relationship beyond "this file was already included everywhere."

The costs are real:

- **Compile-time coupling** — every consumer of one symbol pays the parse cost
  of all of them, and rebuilds when *any* of them changes.
- **Unclear ownership** — a file with 14 unrelated concerns has no single
  responsibility and no obvious owner.
- **Discoverability** — dependency lists stop meaning anything when everything
  hides behind one filename.
- **Review noise** — unrelated concerns share one diff/blame history.

Java and C# linters have enforced one-type-per-file for years (Checkstyle
[`OneTopLevelClass`](https://checkstyle.sourceforge.io/checks/design/onetoplevelclass.html),
StyleCop [SA1402](https://github.com/DotNetAnalyzers/StyleCopAnalyzers/blob/master/documentation/SA1402.md),
SonarSource [S1996](https://rules.sonarsource.com/java/rspec-1996/)). To our
knowledge **no maintained C/C++ tool ships this check** — clang-tidy, cppcheck,
cpplint, semgrep, PVS-Studio, SonarSource cfamily, lizard, and OCLint all
measure other axes (per-function complexity, per-class size, include hygiene).
IWYU and clang-include-cleaner fix what *consumers* include; neither asks
whether a header itself is well-scoped. godfile fills that gap.

## Install

Requires Python ≥ 3.9 and [universal-ctags](https://github.com/universal-ctags/ctags)
on your `PATH` (`apt install universal-ctags` / `brew install universal-ctags`).

```sh
pip install godfile
```

## Usage

```sh
godfile include/ src/                 # scan headers, human-readable output
godfile include/ --max-types 3       # looser threshold
godfile include/ --format sarif > godfile.sarif   # for dashboards / GitHub code scanning
godfile include/ --format json       # machine-readable
godfile src/ --sources               # also scan .c/.cc/.cpp files
godfile . --exclude third_party --exclude '*/bundled/*'   # skip vendored code
```

Exit codes: `0` clean, `1` findings, `2` usage/environment error — drop it
straight into CI.

```text
include/leveldb/env.h: 7 top-level types (limit 1)
  include/leveldb/env.h:51: class leveldb::Env
  include/leveldb/env.h:222: class leveldb::SequentialFile
  include/leveldb/env.h:252: class leveldb::RandomAccessFile
  ...
```

## What counts as a violation

godfile counts **top-level type definitions** — `class`, `struct`, `enum`,
`union`, and `typedef`s that name an otherwise-anonymous type. It correctly
does **not** count:

- forward declarations
- types nested inside another type or function
- template specializations (collapsed into their primary template)
- plain `typedef`/`using` aliases

Two conventional exceptions are **exempt by default** (each has a flag to
count it strictly):

| Exemption | Rationale | Strict flag |
|---|---|---|
| Exception types (`inherits` something matching `exception`/`error`, or named `*Exception`/`*Error`) | a class and the exception it throws belong together | `--count-exceptions` |
| Types in `detail`/`impl`/`internal` namespaces (incl. abseil-style `*_internal` suffixes) | internal-only helpers coupled to the public type | `--count-internal` |

For files that are legitimately many-types-by-design (e.g. generated protocol
structs), add a suppression comment anywhere in the file:

```cpp
// godfile:ignore-file — generated protocol structs, cohesive by design
```

## How it works

godfile shells out to universal-ctags (JSON output) and applies the rules
above to the tag stream. This makes it **zero-build-dependency**: it works on
any source tree without a `compile_commands.json`, without the project
compiling, and without heavyweight AST tooling. The trade-off is heuristic
parsing — heavily macro-obfuscated type definitions can be missed. An
AST-accurate mode (libclang against a compilation database) is a possible
future addition for codebases that want exactness over convenience.

## Roadmap

- SA1402-style carve-outs (e.g. small structs coexisting with one primary class)
- Config file (`[tool.godfile]` in `pyproject.toml` / `.godfilerc`)
- Relatedness heuristics: flag *unrelated* types, not just *many* types
- Aggregating per-consumer symbol-usage data (IWYU-style) to suggest natural
  split boundaries for an offending header
- AST-accurate mode via libclang

## Field results

Shallow clones of six well-known repos, default settings plus vendored-code
excludes (`gtest`, `third_party`, `bundled`, `deps`, …):

| Repo | Files | Flagged | Scan time | Worst offender |
|---|---|---|---|---|
| redis | 86 | 30 | 0.11s | `src/server.h` — 95 types |
| rocksdb | 615 | 261 | 0.34s | `java/rocksjni/portal.h` — 107 types |
| abseil-cpp | 385 | 26 | 0.24s | test/internal helpers |
| spdlog | 97 | 14 | 0.06s | `common.h` — 7 types |
| fmt | 22 | 15 | 0.07s | `base.h` — 22 types (few-header by design) |
| nlohmann/json | 54 | 4 | 0.18s | `json.hpp` (single-header by design) |

Deliberately single-header libraries flag loudly — that's what
`// godfile:ignore-file` or `--max-types` is for. Files like redis's
`server.h` are the actual target: decades of organic accretion.

## Prior art

The check exists in other ecosystems (Checkstyle, StyleCop, SonarSource for
Java — there is an [open request](https://community.sonarsource.com/t/c-version-of-s1996-in-java-one-top-level-class-or-interface-per-file/138155)
for a C++ version). One abandoned student project
([CPP_Coding_Style_Checker](https://github.com/remusao/CPP_Coding_Style_Checker/))
listed a similar rule; nothing maintained or packaged ships it.

## License

MIT
