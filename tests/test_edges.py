"""Error-path and edge-case coverage."""

import subprocess
import types

import pytest

from godfile.cli import main
from godfile.rules import Config, Finding, evaluate
from godfile.scanner import CtagsError, TypeDef, extract_typedefs, find_ctags, run_ctags


def _fake_which(mapping):
    return lambda name: mapping.get(name)


def test_find_ctags_nothing_on_path(monkeypatch):
    monkeypatch.setattr("godfile.scanner.shutil.which", _fake_which({}))
    with pytest.raises(CtagsError, match="not found"):
        find_ctags()


def test_find_ctags_rejects_non_universal(monkeypatch):
    monkeypatch.setattr(
        "godfile.scanner.shutil.which", _fake_which({"ctags": "/usr/bin/ctags"})
    )
    monkeypatch.setattr(
        "godfile.scanner.subprocess.run",
        lambda *a, **k: types.SimpleNamespace(stdout="Exuberant Ctags 5.9", returncode=0),
    )
    with pytest.raises(CtagsError):
        find_ctags()


def test_find_ctags_survives_broken_binary(monkeypatch):
    def boom(*a, **k):
        raise OSError("exec format error")

    monkeypatch.setattr(
        "godfile.scanner.shutil.which", _fake_which({"ctags": "/usr/bin/ctags"})
    )
    monkeypatch.setattr("godfile.scanner.subprocess.run", boom)
    with pytest.raises(CtagsError, match="not found"):
        find_ctags()


def test_find_ctags_explicit_binary_used_first():
    real = find_ctags()
    assert find_ctags(real) == real


def test_run_ctags_failure_raises(monkeypatch):
    monkeypatch.setattr(
        "godfile.scanner.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(a, 25, stdout="", stderr="boom"),
    )
    with pytest.raises(CtagsError, match="exit 25"):
        run_ctags("ctags", ["x.h"])


def test_run_ctags_skips_garbage_and_non_tag_lines(monkeypatch):
    out = '\n'.join([
        '{"_type": "ptag", "name": "JSON_OUTPUT_VERSION"}',
        'not json at all {{{',
        '',
        '{"_type": "tag", "name": "Foo", "kind": "class", "path": "x.h", "line": 1}',
    ])
    monkeypatch.setattr(
        "godfile.scanner.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out, stderr=""),
    )
    tags = run_ctags("ctags", ["x.h"])
    assert [t["name"] for t in tags] == ["Foo"]


def test_typedef_to_dunder_anon_typeref_counts():
    # typeref target not in anon_names but carrying the __anon marker
    tags = [
        {"_type": "tag", "name": "Point", "kind": "typedef", "path": "x.h",
         "line": 3, "typeref": "struct:__anon999"},
        {"_type": "tag", "name": "Alias", "kind": "typedef", "path": "x.h",
         "line": 4, "typeref": "int"},
    ]
    by_file = extract_typedefs(tags)
    assert [t.name for t in by_file["x.h"]] == ["Point"]


def test_unexpected_kinds_ignored():
    tags = [
        {"_type": "tag", "name": "do_thing", "kind": "function", "path": "x.h", "line": 1},
        {"_type": "tag", "name": "ns", "kind": "namespace", "path": "x.h", "line": 2},
    ]
    assert extract_typedefs(tags) == {}


def test_anonymous_extras_marker():
    tags = [
        {"_type": "tag", "name": "OddName", "kind": "struct", "path": "x.h",
         "line": 1, "extras": "fileScope,anonymous"},
    ]
    assert extract_typedefs(tags) == {}


def test_type_weight_semantics():
    from godfile.rules import is_enum_type, type_weight

    def td(kind, loc=1, underlying=""):
        return TypeDef(name="X", qualified_name="X", kind=kind, file="x.h",
                       line=1, loc=loc, underlying=underlying)

    assert type_weight(td("class", loc=500), 100) == 1.0
    assert type_weight(td("enum", loc=10), 100) == 0.1
    assert type_weight(td("enum", loc=250), 100) == 1.0  # capped
    # typedef enum {...} Name; weights like an enum; typedef struct does not
    assert is_enum_type(td("typedef", underlying="enum"))
    assert type_weight(td("typedef", loc=10, underlying="enum"), 100) == 0.1
    assert type_weight(td("typedef", loc=10, underlying="struct"), 100) == 1.0


def test_typedef_enum_loc_spans_anon_body():
    tags = [
        {"_type": "tag", "name": "__anon42", "kind": "enum", "path": "x.h",
         "line": 3, "end": 7},
        {"_type": "tag", "name": "AlphaMode", "kind": "typedef", "path": "x.h",
         "line": 8, "typeref": "enum:__anon42"},
    ]
    (t,) = extract_typedefs(tags)["x.h"]
    assert t.underlying == "enum"
    assert t.loc == 6  # anon body line 3 through typedef name line 8


def test_finding_over_by():
    t = TypeDef(name="A", qualified_name="A", kind="class", file="x.h", line=1)
    f = Finding(file="x.h", counted=[t, t, t], exempt=[], max_types=1, score=3.0)
    assert f.over_by == 2.0


def test_ignore_directive_on_unreadable_file_is_false():
    types_by_file = {
        "/nonexistent/x.h": [
            TypeDef(name=n, qualified_name=n, kind="class", file="/nonexistent/x.h", line=i)
            for i, n in enumerate(["A", "B"], 1)
        ]
    }
    findings = evaluate(types_by_file, Config())
    assert len(findings) == 1  # unreadable file -> directive treated as absent


def test_abseil_style_internal_namespace_exempt():
    from godfile.rules import is_internal_type

    def td(ns):
        return TypeDef(name="X", qualified_name=f"{ns}::X", kind="class",
                       file="x.h", line=1, namespace=ns)

    assert is_internal_type(td("absl::container_internal"))
    assert is_internal_type(td("fmt::detail"))
    assert not is_internal_type(td("absl::container"))
    assert not is_internal_type(td(""))


def test_exclude_globs():
    from godfile.cli import collect_files

    fixtures = "tests/fixtures"
    all_files = collect_files([fixtures], include_sources=False)
    assert len(all_files) == 4
    assert collect_files([fixtures], False, exclude=["fixtures"]) == []
    assert len(collect_files([fixtures], False, exclude=["kitchen_*"])) == 3
    assert len(collect_files([fixtures], False, exclude=["*/clean.h"])) == 3


def test_exclude_flag_end_to_end():
    assert main(["tests/fixtures", "--exclude", "kitchen_sink.h"]) == 0


def test_main_ctags_error_exits_2(capsys):
    assert main(["--ctags-bin", "/nonexistent/ctags", "tests/fixtures/clean.h"]) == 2
    assert "not found" in capsys.readouterr().err


def test_version_flag():
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
