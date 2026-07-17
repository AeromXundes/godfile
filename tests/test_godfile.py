import json
from pathlib import Path

import pytest

from godfile.cli import main
from godfile.rules import Config, evaluate
from godfile.scanner import extract_typedefs, find_ctags, run_ctags

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def kitchen_sink_types():
    ctags = find_ctags()
    tags = run_ctags(ctags, [str(FIXTURES / "kitchen_sink.h")])
    by_file = extract_typedefs(tags)
    assert len(by_file) == 1
    return next(iter(by_file.values()))


def names(defs):
    return {t.qualified_name for t in defs}


def test_counts_real_top_level_definitions(kitchen_sink_types):
    got = names(kitchen_sink_types)
    assert {"Mutex", "SocketAddress", "LogLevel", "Value", "RingBuffer",
            "ParseError", "Point", "detail::InternalHelper", "app::Service"} == got


def test_forward_declarations_not_counted(kitchen_sink_types):
    assert not {"Widget", "Gadget"} & names(kitchen_sink_types)


def test_nested_class_not_counted(kitchen_sink_types):
    assert not any("ScopedLock" in n for n in names(kitchen_sink_types))


def test_template_specialization_collapses(kitchen_sink_types):
    assert sum(1 for t in kitchen_sink_types if t.name == "RingBuffer") == 1


def test_plain_alias_not_counted_but_anon_typedef_is(kitchen_sink_types):
    got = names(kitchen_sink_types)
    assert "StringMap" not in got
    assert "Point" in got


def test_exception_and_detail_types_exempt_by_default(kitchen_sink_types):
    findings = evaluate({"kitchen_sink.h": kitchen_sink_types}, Config())
    assert len(findings) == 1
    f = findings[0]
    assert names(f.exempt) == {"ParseError", "detail::InternalHelper"}
    assert len(f.counted) == 7


def test_strict_config_counts_everything(kitchen_sink_types):
    findings = evaluate(
        {"kitchen_sink.h": kitchen_sink_types},
        Config(count_exceptions=True, count_internal=True),
    )
    assert len(findings[0].counted) == 9


def test_clean_header_passes():
    assert main([str(FIXTURES / "clean.h")]) == 0


def test_ignore_directive_suppresses():
    assert main([str(FIXTURES / "ignored.h")]) == 0


def test_kitchen_sink_fails_with_exit_1():
    assert main([str(FIXTURES / "kitchen_sink.h")]) == 1


def test_max_types_threshold():
    ks = str(FIXTURES / "kitchen_sink.h")
    assert main([ks, "--max-types", "7", "--fail-at", "8"]) == 0
    assert main([ks, "--max-types", "6", "--fail-at", "7"]) == 1


def test_warning_band_reports_but_exits_zero(capsys):
    ks = str(FIXTURES / "kitchen_sink.h")
    # 7 counted types: over the green line (6) but under the red line (8)
    assert main([ks, "--max-types", "6", "--fail-at", "8"]) == 0
    out = capsys.readouterr().out
    assert "warning: 7 top-level types" in out
    assert "0 error(s), 1 warning(s)" in out


def test_default_bands():
    ks = str(FIXTURES / "kitchen_sink.h")
    assert main([ks]) == 1  # 7 types >= default fail-at 4 -> error


def test_fail_at_must_exceed_max_types():
    with pytest.raises(SystemExit) as exc:
        main([str(FIXTURES / "clean.h"), "--max-types", "4"])
    assert exc.value.code == 2


def test_sarif_output_is_valid(capsys):
    rc = main([str(FIXTURES / "kitchen_sink.h"), "--format", "sarif"])
    assert rc == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["version"] == "2.1.0"
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "godfile"
    assert run["tool"]["driver"]["rules"][0]["id"] == "GF001"
    (result,) = run["results"]
    assert result["ruleId"] == "GF001"
    assert result["level"] == "error"
    assert "7 top-level types" in result["message"]["text"]
    assert len(result["relatedLocations"]) == 7


def test_json_output_shape(capsys):
    rc = main([str(FIXTURES / "kitchen_sink.h"), "--format", "json"])
    assert rc == 1
    doc = json.loads(capsys.readouterr().out)
    (finding,) = doc["findings"]
    assert finding["typeCount"] == 7
    assert finding["severity"] == "error"
    assert {t["name"] for t in finding["exemptTypes"]} == {
        "ParseError", "detail::InternalHelper",
    }


def test_directory_scan_and_missing_path(capsys):
    assert main([str(FIXTURES)]) == 1
    assert main(["/nonexistent/nowhere"]) == 2
