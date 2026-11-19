"""本物の claude で: 前の setup が版（tag）に止めた土台の目録を残した箱でも、使う側の塊（docs/核の届け方.md）を回すと
古い目録を外して足し直し、入った plugin が出所の先端に揃う。今の目録（版に止めず入口を持つ）は外さない。

前の目録が残ると marketplace add は飛ばされ、marketplace update も止めた版から動かない（使う側の pixel-office の容器で
2026-11-19 に同じ形を見た）。出所は手元の git の repo を https の名で見せる（鍵も外の網も要らない）。
本物の claude を要る印 real_claude を付ける（飛ばす条件と CI で拾う所は tests/conftest.py の 1 か所）。
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "scripts" / "setup_plugins.py"
KAKU = ROOT / "plugins" / "core" / "scripts" / "kaku.py"
DOC = ROOT / "docs" / "核の届け方.md"
URL = "https://example.invalid/o/agent-foundation-public.git"
REMOVE = re.compile(r"(?m)^.*marketplace remove agent-foundation.*\n")

pytestmark = pytest.mark.real_claude


def git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a],
                          check=True, capture_output=True, text=True).stdout.strip()


def commit(up, names, msg):
    (up / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
        {"name": "agent-foundation", "owner": {"name": "t"},
         "plugins": [{"name": n, "source": f"./plugins/{n}"} for n in names]}), encoding="utf-8")
    for n in names:
        (up / "plugins" / n / ".claude-plugin").mkdir(parents=True, exist_ok=True)
        (up / "plugins" / n / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": n}), encoding="utf-8")
        (up / "plugins" / n / "版.txt").write_text(msg, encoding="utf-8")
    git(up, "add", "-A")
    git(up, "commit", "-qm", msg)
    return git(up, "rev-parse", "HEAD")


def box(tmp_path):
    """出所（v1 に tag・その後 v2 へ進む）と、空の home。"""
    up = tmp_path / "up"
    (up / "scripts").mkdir(parents=True)
    (up / ".claude-plugin").mkdir()
    (up / "plugins" / "core" / "scripts").mkdir(parents=True)
    shutil.copy2(KAKU, up / "plugins" / "core" / "scripts" / "kaku.py")  # 入口が読む比べ方の正本（本物の出所は repo 全体）
    shutil.copy2(ENTRY, up / "scripts" / "setup_plugins.py")
    git(tmp_path, "init", "-q", "-b", "main", str(up))
    v1 = commit(up, ["core"], "v1")
    git(up, "tag", "v1")
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), GIT_CONFIG_GLOBAL=str(tmp_path / "gitconfig"))
    for k, v in [(f"url.file://{up}.insteadOf", URL), ("protocol.file.allow", "always")]:
        subprocess.run(["git", "config", "--global", k, v], env=env, check=True)
    return up, v1, home, env


def block(drop_remove=False):
    b = re.search(r"<!-- setup-script.*?-->\s*```bash\n(.*?)\n\s*```", DOC.read_text(encoding="utf-8"), re.S).group(1)
    b = "\n".join(s.strip() for s in b.splitlines()).replace("ynishikawa-coder/agent-foundation-public", URL)
    return REMOVE.sub("", b + "\n") if drop_remove else b


def setup(env, home, script):
    r = subprocess.run(["bash", "-ec", script], capture_output=True, text=True, env=env, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    t = json.loads((home / ".claude" / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    return {k: v[0].get("gitCommitSha") for k, v in t["plugins"].items()}


def pin_old(env, up):
    """前の setup の形: 版に止めて足し、その版の plugin を入れた箱。その後に出所が先へ進む。"""
    r = subprocess.run(["claude", "plugin", "marketplace", "add", URL + "#v1", "--scope", "user"],
                       capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    subprocess.run(["claude", "plugin", "install", "core@agent-foundation", "--scope", "user"],
                   capture_output=True, text=True, env=env, timeout=300, check=True)
    return commit(up, ["core", "added"], "v2")


def test_合格_版に止めた古い目録が残っても外して先端から入れ直す(tmp_path):
    up, _, home, env = box(tmp_path)
    tip = pin_old(env, up)
    assert setup(env, home, block()) == {"core@agent-foundation": tip, "added@agent-foundation": tip}
    src = json.loads((home / ".claude" / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8"))
    assert not src["agent-foundation"]["source"].get("ref")


def test_注入_外す行を抜くと止めた版のまま入る(tmp_path):
    """誤りの類の注入: remove の行の無い塊では、add は飛ばされ update も版から動かず、先端の plugin が入らない。"""
    up, v1, home, env = box(tmp_path)
    tip = pin_old(env, up)
    got = setup(env, home, block(drop_remove=True))
    assert got != {"core@agent-foundation": tip, "added@agent-foundation": tip}


def logged(tmp_path, env):
    """本物の claude の前に、打たれた引数を書き残す薄い殻を置く（外したかを打った命令で見る）。"""
    bin_, log = tmp_path / "bin", tmp_path / "claude.log"
    bin_.mkdir()
    (bin_ / "claude").write_text(f'#!/bin/sh\necho "$*" >> {log}\nexec {shutil.which("claude")} "$@"\n', encoding="utf-8")
    (bin_ / "claude").chmod(0o755)
    return dict(env, PATH=f"{bin_}:{env['PATH']}"), log


def test_合格_今の目録は外さない(tmp_path):
    up, _, home, env = box(tmp_path)
    env, log = logged(tmp_path, env)
    setup(env, home, block())
    tip = commit(up, ["core", "added"], "v2")
    assert setup(env, home, block()) == {"core@agent-foundation": tip, "added@agent-foundation": tip}
    assert "marketplace remove" not in log.read_text(encoding="utf-8")


def test_合格_版に止めた目録は外したと打った命令に残る(tmp_path):
    up, _, home, env = box(tmp_path)
    env, log = logged(tmp_path, env)
    pin_old(env, up)
    setup(env, home, block())
    assert "plugin marketplace remove agent-foundation" in log.read_text(encoding="utf-8")
