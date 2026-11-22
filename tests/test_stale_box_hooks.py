"""古い版の dir で立った窓でも、土台の hook は入った台帳のいちばん新しい版の script が回るか（注入の試験）。

問題: 作り置きの箱で立った窓は、hooks.json の命令が箱を作った時の版の dir を指したまま動き、合流した直し
（例: 窓を立て直させる知らせ・返事の差し戻しを畳んだ直し）が箱の作り直しまで効かなかった。
形: hook の命令は目録の clone の入口 plugins/core/scripts/hook_run.py を通り、入口が台帳の今読まれる行の版を回す。
起動の時に古ければ plugin core が裏で入口 setup_plugins.py を回して先端の版を入れ直す（kaku.py の start_refresh）。
ここは本物の claude なしで、正本の hooks.json の命令そのものを作り物の箱（古い版と新しい版の dir・台帳）で回して照らす。
命令を古い形（版の dir の script を直に指す）に戻すと赤になる。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "plugins" / "core"
sys.path.insert(0, str(CORE / "scripts"))
import kaku  # noqa: E402

HOOKED = sorted(p.parent.parent.name for p in ROOT.glob("plugins/*/hooks/hooks.json"))
PROBE = ('import os, sys\nprint("{ver}", os.environ.get("CLAUDE_PLUGIN_ROOT"), *sys.argv[1:])\n'
         'sys.exit(int(os.environ.get("PROBE_EXIT") or 0))\n')


def commands(hooks: dict):
    for event, groups in (hooks.get("hooks") or {}).items():
        for g in groups:
            for h in g.get("hooks") or []:
                yield event, h["command"]


def scripts_of(hooks: dict) -> set[str]:
    out = set()
    for _, cmd in commands(hooks):
        rel = cmd.split("${CLAUDE_PLUGIN_ROOT}/", 1)[1].split('"', 1)[0]
        out.add(rel)
    return out


def make_box(tmp: Path, name: str, old_hooks: dict, new_hooks: dict, launcher: bool = True, keep_old_row: bool = False) -> dict:
    """作り物の箱: 目録の clone（入口と kaku.py）・plugin の古い版と新しい版の dir・台帳（新しい版が後に入った）。
    台帳は Claude Code が入れ直した時の形（古い版の行は新しい版の行に置き換わる・2.1.330 で確かめた）。
    keep_old_row で古い行も残った形にする。"""
    home = tmp / "home"
    plugins = home / ".claude" / "plugins"
    if launcher:
        shutil.copytree(CORE, plugins / "marketplaces" / kaku.MARKET / "plugins" / "core",
                        ignore=shutil.ignore_patterns("__pycache__"))
    dirs = {}
    for ver, hooks in (("old", old_hooks), ("new", new_hooks)):
        d = plugins / "cache" / kaku.MARKET / name / (ver * 4)[:12]
        (d / "hooks").mkdir(parents=True)
        (d / "hooks" / "hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
        (d / ".claude-plugin").mkdir()
        (d / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}), encoding="utf-8")
        for rel in scripts_of(old_hooks) | scripts_of(hooks):
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(PROBE.format(ver=ver), encoding="utf-8")
        dirs[ver] = d
    rows = [{"scope": "user", "installPath": str(dirs["new"]), "gitCommitSha": "b" * 40, "lastUpdated": "2026-11-22T05:10:00Z"}]
    if keep_old_row:
        rows.insert(0, {"scope": "user", "installPath": str(dirs["old"]), "gitCommitSha": "a" * 40,
                        "lastUpdated": "2026-11-21T23:39:00Z"})
    (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {f"{name}@{kaku.MARKET}": rows}}),
                                                    encoding="utf-8")
    return {"home": home, **dirs}


def run(cmd: str, box: dict, **env) -> subprocess.CompletedProcess:
    """Claude Code と同じく、古い版の dir を CLAUDE_PLUGIN_ROOT にして hooks.json の命令を bash で回す。"""
    e = dict(os.environ, HOME=str(box["home"]), CLAUDE_PLUGIN_ROOT=str(box["old"]), **env)
    return subprocess.run(["bash", "-c", cmd], env=e, input="{}", capture_output=True, text=True, timeout=60)


def stale_runs(name: str, hooks: dict, tmp: Path, keep_old_row: bool = False) -> list[str]:
    """古い版の dir で立った窓で、先端（新しい版）の script でなく古い版の script が回る命令の並び（空＝緑）。"""
    box = make_box(tmp, name, hooks, hooks, keep_old_row=keep_old_row)
    bad = []
    for event, cmd in commands(hooks):
        out = run(cmd, box).stdout.split()
        if not out or out[0] != "new" or out[1] != str(box["new"]):
            bad.append(f"{name} {event}: {cmd} → {' '.join(out) or '（何も回らない）'}")
    return bad


@pytest.mark.parametrize("keep_old_row", [False, True], ids=["古い行が消えた台帳", "古い行も残る台帳"])
@pytest.mark.parametrize("name", HOOKED)
def test_正本の_hook_は古い版の窓でも新しい版の_script_を回す(name, keep_old_row, tmp_path):
    hooks = json.loads((ROOT / "plugins" / name / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert list(commands(hooks)), f"{name} の hooks.json に命令が無い"
    assert stale_runs(name, hooks, tmp_path, keep_old_row) == []


def test_注入_版の_dir_を直に指す古い形の命令は赤(tmp_path):
    hooks = json.loads((ROOT / "plugins" / "guard" / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    for _, groups in hooks["hooks"].items():
        for g in groups:
            for h in g["hooks"]:
                h["command"] = 'python3 "${CLAUDE_PLUGIN_ROOT}/' + h["command"].split("${CLAUDE_PLUGIN_ROOT}/", 1)[1]
    bad = stale_runs("guard", hooks, tmp_path)
    assert len(bad) == 3 and all("→ old" in b for b in bad), bad


def _guard_hooks():
    return json.loads((ROOT / "plugins" / "guard" / "hooks" / "hooks.json").read_text(encoding="utf-8"))


def _cmd(hooks, event):
    return hooks["hooks"][event][0]["hooks"][0]["command"]


def test_先端が外した_hook_は何も回さない(tmp_path):
    old = _guard_hooks()
    new = json.loads(json.dumps(old))
    del new["hooks"]["PostToolUse"]
    box = make_box(tmp_path, "guard", old, new)
    p = run(_cmd(old, "PostToolUse"), box)
    assert p.returncode == 0 and p.stdout == ""
    assert run(_cmd(old, "PreToolUse"), box).stdout.startswith("new ")


def test_止める_exit_は先端の_script_のまま返る(tmp_path):
    hooks = _guard_hooks()
    box = make_box(tmp_path, "guard", hooks, hooks)
    p = run(_cmd(hooks, "PreToolUse"), box, PROBE_EXIT="2")
    assert p.returncode == 2 and p.stdout.startswith("new ")


def test_入口が無い箱では自分の版の_script_を回す(tmp_path):
    hooks = _guard_hooks()
    box = make_box(tmp_path, "guard", hooks, hooks, launcher=False)
    assert run(_cmd(hooks, "PreToolUse"), box).stdout.startswith("old ")


@pytest.mark.parametrize("ledger", ["こわれた", "{}", '{"plugins": {"guard@agent-foundation": "x"}}'])
def test_台帳が読めない時は自分の版の_script_で続ける(tmp_path, ledger):
    hooks = _guard_hooks()
    box = make_box(tmp_path, "guard", hooks, hooks)
    (box["home"] / ".claude" / "plugins" / "installed_plugins.json").write_text(ledger, encoding="utf-8")
    p = run(_cmd(hooks, "PreToolUse"), box)
    assert p.returncode == 0 and p.stdout.startswith("old "), p.stderr


def test_古い版の_dir_が掃除で消えても新しい版の_script_を回す(tmp_path):
    hooks = _guard_hooks()
    box = make_box(tmp_path, "guard", hooks, hooks)
    shutil.rmtree(box["old"])
    assert run(_cmd(hooks, "PreToolUse"), box).stdout.startswith("new ")


def test_新しい版の_dir_が消えていれば自分の版で続ける(tmp_path):
    hooks = _guard_hooks()
    box = make_box(tmp_path, "guard", hooks, hooks)
    shutil.rmtree(box["new"])
    assert run(_cmd(hooks, "PreToolUse"), box).stdout.startswith("old ")


# ── 起動の時に古ければ、裏で入口を回して先端を入れ直す（kaku.py）──
@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude" / "af-foundation").mkdir(parents=True)
    return tmp_path / ".claude"


def _entry(tmp_path, code, line):
    clone = tmp_path / "clone"
    (clone / "scripts").mkdir(parents=True)
    (clone / "scripts" / "setup_plugins.py").write_text(f"print({line!r})\nraise SystemExit({code})\n", encoding="utf-8")
    return clone


def test_入れ直しの失敗は_1_行で_1_度だけ名指す(home, tmp_path):
    clone = _entry(tmp_path, 1, "✗ 土台の目録を取り直せなかった")
    (home / "af-foundation" / "refresh.lock").write_text("", encoding="utf-8")
    assert kaku.refresh("c" * 40, clone / "scripts" / "setup_plugins.py") == 0
    assert not (home / "af-foundation" / "refresh.lock").exists()
    state = {}
    text = kaku.refresh_failed_text(state)
    assert text and "取り直せなかった" in text and "前の版のまま動く" in text
    assert kaku.refresh_failed_text(state) is None


def test_入れ直しが済めば名指さない(home, tmp_path):
    clone = _entry(tmp_path, 0, "✅ 入った")
    kaku.refresh("c" * 40, clone / "scripts" / "setup_plugins.py")
    assert kaku.refresh_failed_text({}) is None


def test_裏の入れ直しは錠で_1_本だけ_済んだ先端へは回さない(home, tmp_path, monkeypatch):
    clone = _entry(tmp_path, 0, "✅ 入った")
    monkeypatch.setattr(kaku, "catalog_source", lambda: ({"installLocation": str(clone)}, None))
    spawned = []
    monkeypatch.setattr(kaku.subprocess, "Popen", lambda args, **kw: spawned.append(args))
    assert kaku.start_refresh("c" * 40) is True
    assert kaku.start_refresh("c" * 40) is False  # 錠が在る＝入れ直し中
    assert spawned[0][-3:] == ["refresh", "c" * 40, str(clone / "scripts" / "setup_plugins.py")]
    (home / "af-foundation" / "refresh.lock").unlink()
    (home / "af-foundation" / "refresh.json").write_text(json.dumps({"main": "c" * 40, "code": 0}), encoding="utf-8")
    assert kaku.start_refresh("c" * 40) is False  # 同じ先端へは入れ直し済み
    assert kaku.start_refresh("d" * 40) is True and len(spawned) == 2


def test_目録の入口が無ければ回さない(home, monkeypatch):
    monkeypatch.setattr(kaku, "catalog_source", lambda: ({}, None))
    assert kaku.start_refresh("c" * 40) is False


def test_起動の時に古ければ裏の入れ直しを始め_古くなければ始めない(home, tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(kaku, "start_refresh", lambda tip: started.append(tip) or True)
    monkeypatch.setattr(kaku, "setup_text", lambda: None)
    monkeypatch.setattr(kaku, "tip_core_text", lambda f: "")
    monkeypatch.setattr(kaku, "start_cause", lambda f: "after")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    for sid, plugins in (("s-old", ["guard"]), ("s-new", [])):
        f = {"installed": "a" * 40, "main": "e" * 40, "ref": "main", "shas": {"core": "a" * 40}, "plugins": plugins}
        monkeypatch.setattr(kaku, "freshness", lambda f=f: f)
        monkeypatch.setattr(kaku.sys, "stdin", __import__("io").StringIO(json.dumps({"session_id": sid})))
        assert kaku.inject() == 0
    assert started == ["e" * 40]
