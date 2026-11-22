"""入った版は、台帳（installed_plugins.json）の installPath が読まれる dir と同じ行だけから読む約束。

行が 1 つでも別の dir（project scope で入った・前に別の所へ入った）の行の版で古さ・揃いを決めず、「分からない」と名指す。
plugin core の kaku.py の installed_sha() と、入口 scripts/setup_plugins.py の installed_shas() の両方。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAKU = ROOT / "plugins" / "core" / "scripts" / "kaku.py"
ENTRY = ROOT / "scripts" / "setup_plugins.py"
OTHER = "a" * 40


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def table(home: Path, rows: dict) -> None:
    p = home / ".claude" / "plugins" / "installed_plugins.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 2, "plugins": rows}), encoding="utf-8")


def test_kaku_は別の_dir_の行_1_つの版で古さを決めない(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    kaku = load(KAKU, "kaku_own_dir")
    # 注入: installPath の違う行を 1 つだけ置く
    table(tmp_path, {"core@agent-foundation": [{"scope": "project", "installPath": str(tmp_path / "別の所"),
                                                 "gitCommitSha": OTHER}]})
    assert kaku.installed_sha() is None
    # 合う行があればその版
    table(tmp_path, {"core@agent-foundation": [{"scope": "user", "installPath": str(tmp_path / "別の所"), "gitCommitSha": OTHER},
                                                 {"scope": "user", "installPath": str(kaku.PLUGIN), "gitCommitSha": "b" * 40}]})
    assert kaku.installed_sha() == "b" * 40


def test_kaku_は版が分からない事を起動の知らせで名指す(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    kaku = load(KAKU, "kaku_own_dir_text")
    table(tmp_path, {"core@agent-foundation": [{"scope": "user", "installPath": str(tmp_path / "別の所"), "gitCommitSha": OTHER}]})
    monkeypatch.setattr(kaku, "catalog_source", lambda: ({"installLocation": str(tmp_path / "market")}, None))
    text = kaku.setup_text() or ""
    assert "版が分からない" in text and OTHER[:12] not in text


def test_入口は_user_scope_の最初の行でなく読まれる_dir_の行の版を読む(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    entry = load(ENTRY, "setup_plugins_own_dir")
    here = tmp_path / "cache" / "core" / "now"
    # 注入: installPath の違う行を 1 つだけ置く
    table(tmp_path, {"core@agent-foundation": [{"scope": "user", "installPath": str(tmp_path / "別の所"), "gitCommitSha": OTHER}]})
    shas = entry.installed_shas("agent-foundation", {"core@agent-foundation": str(here)})
    assert shas == {"core": None}
    # 最初の行が別の dir・2 つ目が読まれる dir
    table(tmp_path, {"core@agent-foundation": [{"scope": "user", "installPath": str(tmp_path / "別の所"), "gitCommitSha": OTHER},
                                                 {"scope": "user", "installPath": str(here), "gitCommitSha": "c" * 40}]})
    assert entry.installed_shas("agent-foundation", {"core@agent-foundation": str(here)}) == {"core": "c" * 40}
    # 読まれる dir が分からない（list に installPath が無い）時も、行の版で決めない
    assert entry.installed_shas("agent-foundation", {"core@agent-foundation": None}) == {"core": None}
