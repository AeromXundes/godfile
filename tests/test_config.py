"""Config-file loading, precedence, and default vendor excludes."""

import pytest

from godfile.cli import main
from godfile.config import ConfigError, load_config

FOUR_STRUCTS = """\
#pragma once
struct A { int a; };
struct B { int b; };
struct C { int c; };
struct D { int d; };
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "four.h").write_text(FOUR_STRUCTS)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_no_config_files_means_defaults(repo):
    assert load_config() == {}
    assert main(["four.h"]) == 1  # score 4 >= default fail-at 4


def test_pyproject_tool_table_applies(repo):
    (repo / "pyproject.toml").write_text(
        "[tool.godfile]\nmax-types = 5\nfail-at = 6\n"
    )
    assert main(["four.h"]) == 0


def test_pyproject_without_table_is_ignored(repo):
    (repo / "pyproject.toml").write_text("[tool.other]\nx = 1\n")
    assert load_config() == {}


def test_godfilerc_beats_pyproject(repo):
    (repo / "pyproject.toml").write_text("[tool.godfile]\nmax-types = 5\nfail-at = 6\n")
    (repo / ".godfilerc").write_text("max-types = 1\nfail-at = 2\n")
    assert load_config() == {"max_types": 1, "fail_at": 2}
    assert main(["four.h"]) == 1


def test_config_found_walking_up(repo, monkeypatch):
    (repo / "pyproject.toml").write_text("[tool.godfile]\nmax-types = 5\nfail-at = 6\n")
    sub = repo / "src" / "nested"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert load_config() == {"max_types": 5, "fail_at": 6}


def test_cli_overrides_config(repo):
    (repo / ".godfilerc").write_text("max-types = 5\nfail-at = 6\n")
    assert main(["four.h", "--max-types", "1", "--fail-at", "2"]) == 1


def test_explicit_config_path(repo):
    other = repo / "ci.toml"
    other.write_text("max-types = 5\nfail-at = 6\n")
    assert main(["four.h", "--config", str(other)]) == 0


def test_explicit_pyproject_without_table_errors(repo, capsys):
    (repo / "pyproject.toml").write_text("[tool.other]\nx = 1\n")
    assert main(["four.h", "--config", "pyproject.toml"]) == 2
    assert "no [tool.godfile] table" in capsys.readouterr().err


def test_unknown_key_rejected(repo, capsys):
    (repo / ".godfilerc").write_text("max-typos = 3\n")
    assert main(["four.h"]) == 2
    assert "unknown option" in capsys.readouterr().err


def test_type_validation(repo):
    (repo / ".godfilerc").write_text("max-types = true\n")
    with pytest.raises(ConfigError, match="must be a int"):
        load_config()
    (repo / ".godfilerc").write_text('exclude = "notalist"\n')
    with pytest.raises(ConfigError, match="must be a list"):
        load_config()


def test_malformed_toml_errors(repo, capsys):
    (repo / ".godfilerc").write_text("max-types = [unclosed\n")
    assert main(["four.h"]) == 2
    assert "godfile:" in capsys.readouterr().err


def test_config_sourced_thresholds_validated(repo, capsys):
    (repo / ".godfilerc").write_text("max-types = 4\nfail-at = 3\n")
    assert main(["four.h"]) == 2
    assert "must be greater than" in capsys.readouterr().err


def test_config_exclude_merges_with_cli(repo, capsys):
    sub = repo / "legacy"
    sub.mkdir()
    (sub / "old.h").write_text(FOUR_STRUCTS)
    (repo / ".godfilerc").write_text('exclude = ["legacy"]\n')
    assert main([".", "--exclude", "four.h"]) == 2  # everything excluded
    assert "no matching files" in capsys.readouterr().err


def test_default_excludes_skip_vendor_dirs(repo, capsys):
    vendor = repo / "boost"
    vendor.mkdir()
    (vendor / "vendored.h").write_text(FOUR_STRUCTS)
    assert main(["."]) == 1
    out = capsys.readouterr().out
    assert "vendored.h" not in out
    assert "four.h" in out


def test_no_default_excludes_flag_scans_vendor(repo, capsys):
    vendor = repo / "third_party"
    vendor.mkdir()
    (vendor / "vendored.h").write_text(FOUR_STRUCTS)
    assert main([".", "--no-default-excludes"]) == 1
    assert "vendored.h" in capsys.readouterr().out


def test_default_excludes_false_in_config(repo, capsys):
    vendor = repo / "deps"
    vendor.mkdir()
    (vendor / "vendored.h").write_text(FOUR_STRUCTS)
    (repo / ".godfilerc").write_text("default-excludes = false\n")
    assert main(["."]) == 1
    assert "vendored.h" in capsys.readouterr().out
