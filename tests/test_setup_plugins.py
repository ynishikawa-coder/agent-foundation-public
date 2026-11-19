"""土台の入口（scripts/setup_plugins.py）の試験: plugin の名を写さず配りの器から全部入れ、入れ損ねを名指しする。

claude の命令は作り物（打たれた命令を記録し、plugin list に「入った」物を返す）で置き換える。
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "scripts" / "setup_plugins.py"
DOC = ROOT / "docs" / "核の届け方.md"

FAKE = r'''#!/usr/bin/env python3
import json, os, sys
log = os.environ["FAKE_LOG"]
with open(log, "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
broken = set(os.environ.get("FAKE_BROKEN", "").split())
if sys.argv[1:3] == ["plugin", "list"]:
    got = [l.split()[2] for l in open(log) if l.startswith("plugin install ")]
    print(json.dumps([{"id": g, "scope": "user", "enabled": True} for g in got if g.split("@")[0] not in broken]))
'''


def foundation(tmp_path, names):
    """入口と配りの器だけを持つ作り物の目録の checkout。"""
    root = tmp_path / "market"
    (root / "scripts").mkdir(parents=True)
    (root / ".claude-plugin").mkdir()
    shutil.copy2(ENTRY, root / "scripts" / "setup_plugins.py")
    (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
        {"name": "agent-foundation", "plugins": [{"name": n, "source": f"./plugins/{n}"} for n in names]}), encoding="utf-8")
    return root


def run(tmp_path, root, broken=""):
    fake = tmp_path / "claude"
    fake.write_text(FAKE, encoding="utf-8")
    fake.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = dict(os.environ, HOME=str(home), CLAUDE_BIN=str(fake), FAKE_LOG=str(tmp_path / "log"), FAKE_BROKEN=broken)
    r = subprocess.run([sys.executable, str(root / "scripts" / "setup_plugins.py")], capture_output=True, text=True,
                       env=env, timeout=60)
    log = (tmp_path / "log").read_text(encoding="utf-8") if (tmp_path / "log").exists() else ""
    note = home / ".claude" / "CLAUDE.md"
    return r, log, (note.read_text(encoding="utf-8") if note.exists() else ""), home


def test_配りの器の_plugin_を全部入れ_入口の印を書く(tmp_path):
    r, log, note, home = run(tmp_path, foundation(tmp_path, ["core", "guard", "docs-kit"]))
    assert r.returncode == 0, r.stdout
    for n in ["core", "guard", "docs-kit"]:
        assert f"plugin install {n}@agent-foundation --scope user" in log
    assert "af-plugin-missing" not in note
    state = json.loads((home / ".claude" / "af-foundation" / "setup.json").read_text(encoding="utf-8"))
    assert state["plugins"] == ["core", "guard", "docs-kit"] and state["missing"] == []


def test_土台が足した_plugin_は使う側が何も直さずに入る(tmp_path):
    """注入: 配りの器に plugin を足す → 入口が名を写さずに入れる（使う側の setup script は同じまま）。"""
    r, log, _, _ = run(tmp_path, foundation(tmp_path, ["core", "guard", "足した物"]))
    assert r.returncode == 0 and "plugin install 足した物@agent-foundation" in log


def test_入れ損ねは名指しで知らせ_全部入れば知らせを消す(tmp_path):
    root = foundation(tmp_path, ["core", "guard"])
    r, _, note, home = run(tmp_path, root, broken="guard")
    assert r.returncode == 1 and "<!-- af-plugin-missing --> 土台の plugin が入っていない: guard" in note
    (tmp_path / "log").unlink()
    r, _, note, _ = run(tmp_path, root)
    assert r.returncode == 0 and "af-plugin-missing" not in note


def test_配りの器が読めなければ黙って_0_本で進まない(tmp_path):
    root = foundation(tmp_path, ["core"])
    (root / ".claude-plugin" / "marketplace.json").write_text("{", encoding="utf-8")
    r, log, note, _ = run(tmp_path, root)
    assert r.returncode == 2 and "af-plugin-missing" in note and "plugin install" not in log


def _block():
    m = re.search(r"<!-- setup-script.*?-->\s*```bash\n(.*?)\n\s*```", DOC.read_text(encoding="utf-8"), re.S)
    assert m, "docs/核の届け方.md に setup script の塊が無い"
    return m.group(1)


def test_使う側に貼る_setup_script_は_plugin_の名を写さない():
    """注入: setup script の塊に install の行・名の並びを戻すと赤。"""
    block = _block()
    assert "scripts/setup_plugins.py" in block and "ynishikawa-coder/agent-foundation-public" in block
    names = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))["plugins"]
    for n in (p["name"] for p in names):
        assert not re.search(rf"\b{re.escape(n)}\b", block.replace("agent-foundation", "")), f"setup script に plugin の名 {n} が写されている"
    assert "plugin install" not in block and "want=" not in block


def test_setup_script_の塊は目録が取れない時も起動を止めず知らせる(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "claude").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (bin_ / "claude").chmod(0o755)
    env = dict(os.environ, HOME=str(home), PATH=f"{bin_}:{os.environ['PATH']}")
    r = subprocess.run(["bash", "-c", _block()], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "<!-- af-plugin-missing --> 土台の目録が取れず" in (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
