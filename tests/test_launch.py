"""start_game.bat's version launcher (scripts/launch.py): registry, arguments, menu."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location("launch", Path(__file__).resolve().parents[1] / "scripts/launch.py")
launch = importlib.util.module_from_spec(_SPEC)
sys.modules["launch"] = launch  # dataclasses look their module up while it loads
_SPEC.loader.exec_module(launch)  # type: ignore[union-attr]


def test_shipped_registry_has_current_main_and_j54() -> None:
    versions, default = launch.load_versions()
    assert {v.name: v.ref for v in versions} == {"current": None, "main": "main", "j54": "feat/j54-demo"}
    assert default == "current"


def test_registry_default_must_exist(tmp_path) -> None:
    path = tmp_path / "v.json"
    path.write_text(json.dumps({"default": "x", "versions": {"a": {"ref": None}}}), encoding="utf-8")
    with pytest.raises(launch.LaunchError):
        launch.load_versions(path)


def test_first_argument_picks_the_version_and_the_rest_go_to_the_game() -> None:
    versions, _ = launch.load_versions()
    assert launch.split_args(["j54", "--fullscreen"], versions) == ("j54", ["--fullscreen"])
    assert launch.split_args(["--mute"], versions) == (None, ["--mute"])
    assert launch.split_args([], versions) == (None, [])
    with pytest.raises(launch.LaunchError):
        launch.split_args(["nope"], versions)


def test_menu_accepts_number_name_or_enter() -> None:
    versions, default = launch.load_versions()
    out: list[str] = []
    for answers, expected in ((["3"], "j54"), (["main"], "main"), ([""], default), (["9", "x", "2"], "main")):
        replies = iter(answers)
        assert launch.choose(versions, default, read=lambda _p: next(replies), write=out.append) == expected
    assert any("(default)" in line for line in out)


def test_current_runs_this_checkout() -> None:
    assert launch.checkout(launch.Version("current", None)) == launch.ROOT
