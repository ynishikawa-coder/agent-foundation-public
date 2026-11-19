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

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "scripts" / "setup_plugins.py"
DOC = ROOT / "docs" / "核の届け方.md"

FAKE = r'''#!/usr/bin/env python3
# 作り物の claude: 打たれた命令を記録し、install/update で入った台帳（installed_plugins.json）に目録の clone の HEAD を書く。
import json, os, subprocess, sys
from pathlib import Path
log = os.environ["FAKE_LOG"]
with open(log, "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
broken = set(os.environ.get("FAKE_BROKEN", "").split())
root = os.environ["FAKE_ROOT"]
table_path = Path(os.environ["HOME"]) / ".claude" / "plugins" / "installed_plugins.json"
table = json.loads(table_path.read_text()) if table_path.exists() else {"version": 2, "plugins": {}}
head = lambda: subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
a = sys.argv[1:]
if a[:3] == ["plugin", "marketplace", "update"]:
    if os.environ.get("FAKE_UPDATE_FAIL"):
        sys.exit(1)
    subprocess.run(["git", "-C", root, "pull", "-q", "--ff-only"], check=True, capture_output=True)
elif a[:2] in (["plugin", "install"], ["plugin", "update"]):
    name = a[2].split("@")[0]
    if name in broken or (a[1] == "install" and a[2] in table["plugins"]):
        sys.exit(0 if a[1] == "install" else 1)
    if a[1] == "update" and name in os.environ.get("FAKE_UPDATE_STUCK", "").split():
        sys.exit(0)
    table["plugins"][a[2]] = [{"scope": "user", "gitCommitSha": head()}]
    table_path.parent.mkdir(parents=True, exist_ok=True)
    table_path.write_text(json.dumps(table))
elif a[:2] == ["plugin", "list"]:
    print(json.dumps([{"id": k, "scope": "user", "enabled": True} for k in table["plugins"]]))
'''


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   check=True, capture_output=True)


def foundation(tmp_path, names):
    """入口と配りの器だけを持つ作り物の目録の出所（upstream）と、その clone（入口が置かれる所）。clone を返す。"""
    up = tmp_path / "upstream"
    (up / "scripts").mkdir(parents=True)
    (up / ".claude-plugin").mkdir()
    shutil.copy2(ENTRY, up / "scripts" / "setup_plugins.py")
    write_manifest(up, names)
    git(tmp_path, "init", "-q", "-b", "main", str(up))
    git(up, "add", "-A")
    git(up, "commit", "-qm", "v1")
    root = tmp_path / "market"
    git(tmp_path, "clone", "-q", str(up), str(root))
    return root


def write_manifest(root, names):
    (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
        {"name": "agent-foundation", "plugins": [{"name": n, "source": f"./plugins/{n}"} for n in names]}), encoding="utf-8")


def run(tmp_path, root, broken="", **extra):
    fake = tmp_path / "claude"
    fake.write_text(FAKE, encoding="utf-8")
    fake.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = dict(os.environ, HOME=str(home), CLAUDE_BIN=str(fake), FAKE_LOG=str(tmp_path / "log"), FAKE_BROKEN=broken,
               FAKE_ROOT=str(root), **extra)
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


@pytest.mark.parametrize("flags", ["-c", "-ec"])  # 貼る先の setup script が set -e でも 最後の行の知らせまで届く
def test_setup_script_の塊は目録が取れない時も起動を止めず知らせる(tmp_path, flags):
    home = tmp_path / "home"
    home.mkdir()
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "claude").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (bin_ / "claude").chmod(0o755)
    env = dict(os.environ, HOME=str(home), PATH=f"{bin_}:{os.environ['PATH']}")
    r = subprocess.run(["bash", flags, _block()], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "<!-- af-plugin-missing --> 土台の目録が取れず" in (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")


def test_setup_script_の行の守りを外すと_set_e_の下で知らせに届かない(tmp_path):
    """注入: 2 行目の `|| true` を外した塊は set -e の下で途中で抜ける（上の試験の -ec がこの穴を拾う証明）。"""
    block = _block()
    assert "2>/dev/null || true)" in block
    home = tmp_path / "home"
    home.mkdir()
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "claude").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")  # 目録が取れない
    (bin_ / "claude").chmod(0o755)
    env = dict(os.environ, HOME=str(home), PATH=f"{bin_}:{os.environ['PATH']}")
    r = subprocess.run(["bash", "-ec", block.replace("2>/dev/null || true)", "2>/dev/null)")],
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode != 0 and not (home / ".claude" / "CLAUDE.md").exists()
