"""Browser packaging and startup errors must be checked outside the checkout."""
import runpy
import importlib.util
import platform
import sqlite3
import sys
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "blackjack_browser_builder", Path(__file__).resolve().parents[1] / "scripts/build_browser.py")
build_browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_browser)


def test_vm_timezone_handles_localized_text_without_spaces():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for runtime JavaScript compatibility checks")
    source = ('var extractZone=date=>date.toLocaleTimeString(undefined,{hour12:false,timeZoneName:"short"})'
              '.split(" ")[1];')
    patched = build_browser.patch_vm_timezone(source)
    # Chinese browser formatting triggered undefined tzname strings during VM
    # startup. Preserve the timezone field regardless of spaces or locale.
    check = '''
const date = new Date(2026, 0, 1);
date.toLocaleTimeString = () => 'GMT+808:00:00';
for (const locale of ['zh-CN', 'en-US', 'fr-FR', 'ja-JP']) {
  for (const zone of ['Asia/Shanghai', 'America/New_York', 'Europe/Paris']) {
    const NativeFormatter = Intl.DateTimeFormat;
    Intl.DateTimeFormat = function(requested, options) {
      return new NativeFormatter(requested || locale, {...options, timeZone: zone});
    };
    const result = extractZone(date);
    Intl.DateTimeFormat = NativeFormatter;
    if (typeof result !== 'string' || !result.length) throw Error('Missing timezone');
  }
}
'''
    subprocess.run([node, "-e", patched + check], check=True, capture_output=True, text=True)


def test_vm_timezone_patch_rejects_an_unreviewed_runtime():
    with pytest.raises(RuntimeError, match="Pinned VM timezone function changed"):
        build_browser.patch_vm_timezone("const unrelated = 1;")


def test_new_database_resources_are_packaged_without_manual_manifest_update(tmp_path, monkeypatch):
    (tmp_path / "browser").mkdir()
    (tmp_path / "browser/package-files.txt").write_text("assets/card.png\n")
    for name in ("migrations/0001_init.sql", "migrations/0006_new_feature.sql", "seed/default.sql"):
        target = tmp_path / "chaos_blackjack/data" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("-- shipped database resource\n")
    (tmp_path / "chaos_blackjack/data/local.db").write_text("private database")
    (tmp_path / ".env").write_text("private configuration")
    monkeypatch.setattr(build_browser, "ROOT", tmp_path)
    selected = build_browser.package_files()
    assert "chaos_blackjack/data/migrations/0006_new_feature.sql" in selected
    assert "chaos_blackjack/data/seed/default.sql" in selected
    assert "assets/card.png" in selected
    assert not any(name.endswith(".db") or name == ".env" for name in selected)


def test_browser_import_failure_notifies_host_and_closes(monkeypatch):
    events = []
    window = SimpleNamespace(chaosFailed=lambda: events.append("failed"),
                             chaosClosed=lambda: events.append("closed"))
    monkeypatch.setattr(platform, "window", window, raising=False)
    monkeypatch.setitem(sys.modules, "chaos_blackjack.gui.app", None)
    monkeypatch.setattr(sqlite3, "__path__", list(sqlite3.__path__))
    monkeypatch.setenv("CHAOS_DB", ":memory:")
    monkeypatch.setenv("CHAOS_USE_LLM", "0")
    entry = Path(__file__).resolve().parents[1] / "browser/main.py"
    with pytest.raises(ModuleNotFoundError):
        runpy.run_path(str(entry))
    assert events == ["failed", "closed"]
