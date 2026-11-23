"""先端の名簿から消えた土台の plugin を、入れ直し（scripts/setup_plugins.py）が外し、立っている窓でも hook が回らないか（注入の試験）。

問題: 入れ直しは名簿に在る plugin を先端の版へ替えるだけで、土台が畳んだ plugin（例 session-watch）は古い版のまま
入り続けた。古い版で立った窓では、畳んだ見張りの hook が先端と食い違う知らせを出し続けた。
形: 入れ直しが同じ目録の、名簿に無い plugin を `claude plugin uninstall` で外し、hook の入口 hook_run.py は台帳に行が無く
目録の clone の名簿にも無い plugin の hook を回さない。目録の外の plugin は触らない。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import test_setup_plugins as tsp

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "plugins" / "core"
sys.path.insert(0, str(CORE / "scripts"))
import kaku  # noqa: E402

M = kaku.MARKET
UNINSTALL = r'''
elif a[:2] == ["plugin", "uninstall"]:
    if a[2].split("@")[0] in broken:
        sys.exit(1)
    table["plugins"].pop(a[2], None)
    table_path.write_text(json.dumps(table))
'''
CMD = ('f="$HOME/.claude/plugins/marketplaces/agent-foundation/plugins/core/scripts/hook_run.py"; [ -f "$f" ] || f=; '
       'python3 ${f:+"$f"} "${CLAUDE_PLUGIN_ROOT}/scripts/watch.py" stop')
PROBE = 'import os, sys\nprint("{ver}", os.environ.get("CLAUDE_PLUGIN_ROOT"), *sys.argv[1:])\n'


def seed(tmp_path, plugins: dict) -> Path:
    """入れ直しの前の台帳（前の setup が入れた物）。"""
    p = tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 2, "plugins": {k: [{"scope": "user", "installPath": f"/x/{k}", "gitCommitSha": "a" * 40}]
                                                       for k in plugins}}), encoding="utf-8")
    return p


def setup(tmp_path, monkeypatch, names, before, **extra):
    monkeypatch.setattr(tsp, "FAKE", tsp.FAKE + UNINSTALL)
    root = tsp.foundation(tmp_path, names)
    ledger = seed(tmp_path, before)
    r, log, note, home = tsp.run(tmp_path, root, **extra)
    return r, log, note, json.loads(ledger.read_text(encoding="utf-8"))["plugins"]


def test_1_名簿から消えた土台の_plugin_は入れ直しで外れる(tmp_path, monkeypatch):
    r, log, _, table = setup(tmp_path, monkeypatch, ["core"], [f"core@{M}", f"session-watch@{M}"])
    assert r.returncode == 0, r.stdout
    assert f"plugin uninstall session-watch@{M} --scope user" in log
    assert f"session-watch@{M}" not in table and f"core@{M}" in table


def test_1_外せなければ名指しする(tmp_path, monkeypatch):
    r, _, note, table = setup(tmp_path, monkeypatch, ["core"], [f"core@{M}", f"session-watch@{M}"], broken="session-watch")
    assert r.returncode == 1 and "外せない: session-watch" in note and f"session-watch@{M}" in table


def test_1_名簿を取り直せない時は外さない(tmp_path, monkeypatch):
    _, log, _, table = setup(tmp_path, monkeypatch, ["core"], [f"core@{M}", f"session-watch@{M}"], FAKE_UPDATE_FAIL="1")
    assert "uninstall" not in log and f"session-watch@{M}" in table


def test_2_名簿に在る_plugin_は今までどおり先端へ替えて外さない(tmp_path, monkeypatch):
    r, log, _, table = setup(tmp_path, monkeypatch, ["core", "guard"], [f"core@{M}", f"guard@{M}"])
    assert r.returncode == 0, r.stdout
    assert "uninstall" not in log and f"plugin update guard@{M}" in log
    assert table[f"guard@{M}"][0]["gitCommitSha"] != "a" * 40  # 先端の版に替わった


def test_3_目録の外の_plugin_は触らない(tmp_path, monkeypatch):
    r, log, _, table = setup(tmp_path, monkeypatch, ["core"], [f"core@{M}", "mine@my-market", f"mine@{M}-fork"])
    assert r.returncode == 0, r.stdout
    assert "uninstall" not in log and "mine@my-market" in table and f"mine@{M}-fork" in table


def box(tmp_path, listed: list[str] | None, market=M, name="session-watch", row=False) -> dict:
    """立っている窓の箱: 目録の clone（入口と名簿）・古い版で入った plugin の dir・入れ直しの後の台帳。"""
    home = tmp_path / "home"
    plugins = home / ".claude" / "plugins"
    clone = plugins / "marketplaces" / M
    shutil.copytree(CORE, clone / "plugins" / "core", ignore=shutil.ignore_patterns("__pycache__"))
    (clone / ".claude-plugin").mkdir()
    if listed is not None:
        (clone / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
            {"name": M, "plugins": [{"name": n, "source": f"./plugins/{n}"} for n in listed]}), encoding="utf-8")
    d = plugins / "cache" / market / name / "c749925771cd"
    (d / "scripts").mkdir(parents=True)
    (d / ".claude-plugin").mkdir()
    (d / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    (d / "scripts" / "watch.py").write_text(PROBE.format(ver="old"), encoding="utf-8")
    (d / "hooks").mkdir()
    (d / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": CMD}]}]}}),
                                            encoding="utf-8")
    rows = {f"core@{M}": [{"scope": "user", "installPath": str(clone / "plugins" / "core"), "gitCommitSha": "b" * 40}]}
    if row:
        rows[f"{name}@{market}"] = [{"scope": "user", "installPath": str(d), "gitCommitSha": "a" * 40}]
    (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": rows}), encoding="utf-8")
    return {"home": home, "dir": d}


def hook(b) -> subprocess.CompletedProcess:
    e = dict(os.environ, HOME=str(b["home"]), CLAUDE_PLUGIN_ROOT=str(b["dir"]))
    return subprocess.run(["bash", "-c", CMD], env=e, input="{}", capture_output=True, text=True, timeout=60)


def test_1_外した_plugin_の_hook_は立っている窓でも回らない(tmp_path):
    r = hook(box(tmp_path, ["core", "guard"]))
    assert r.returncode == 0 and r.stdout == "", r.stdout + r.stderr


def test_1_注入_名簿に戻すと回る(tmp_path):
    """名簿で決めている事の注入: 同じ箱で名簿に名を戻すと hook は回る（名簿を見ずに止めていない）。"""
    b = box(tmp_path, ["core", "guard", "session-watch"])
    assert hook(b).stdout.split()[:2] == ["old", str(b["dir"])]


def test_1_名簿が読めなければ今までどおり回す(tmp_path):
    assert hook(box(tmp_path, None)).stdout.startswith("old ")


def test_2_台帳に在る_plugin_は今までどおり回す(tmp_path):
    assert hook(box(tmp_path, ["core"], row=True)).stdout.startswith("old ")


def test_3_目録の外の_plugin_の_hook_は回す(tmp_path):
    assert hook(box(tmp_path, ["core"], market="my-market")).stdout.startswith("old ")
