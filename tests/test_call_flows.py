"""scripts/call_flows.py: 部品どうしの呼び出しの流れを機械で拾い、全体の絵に無い流れを赤にするか（注入の試験）。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_dougu_bun_okiba import 根治の入口を指す

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "call_flows.py"


def git(cwd, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=cwd, check=True,
                   capture_output=True)


def put(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def fake(tmp_path):
    r = tmp_path / "repo"
    for n in ("alpha", "beta"):
        put(r, f"plugins/{n}/.claude-plugin/plugin.json", "{}")
    put(r, "plugins/beta/scripts/judge.py", "print(1)\n")
    put(r, "plugins/beta/scripts/common.py", "x = 1\n")
    put(r, "scripts/common.py", "x = 2\n")                      # plugin の外にも同じ名＝名だけでは拾わない
    put(r, "plugins/beta/notes.md", "# 文書\n")
    put(r, "plugins/alpha/skills/s/SKILL.md", "1. 決まりの照らしは `python3 judge.py check` を回す。\n")
    put(r, "plugins/alpha/scripts/a.py", "import common  # 外の common.py\nDOC = 'plugins/beta/notes.md'\n")
    git(r, "init", "-q")
    git(r, "add", "-A")
    return r


def picture(tmp_path, arrows, boxes=("alpha", "beta")):
    pic = {"boxes": [{"id": f"x{i}", "tab": "arch", "t": f"{n}（作り物）"} for i, n in enumerate(boxes)],
           "arrows": [{"from": a, "to": b} for a, b in arrows]}
    p = tmp_path / "絵.json"
    p.write_text(json.dumps(pic, ensure_ascii=False), encoding="utf-8")
    return p


def run(*args):
    return subprocess.run([sys.executable, "-B", str(TOOL), *args], capture_output=True, text=True)


def test_別の部品の道具を呼ぶ手順を拾い_文書と外の同じ名は拾わない(fake):
    res = run("list", "--repo", str(fake))
    assert res.returncode == 0
    assert res.stdout.strip().splitlines() == ["alpha → beta  plugins/alpha/skills/s/SKILL.md:1 judge.py"]


def test_絵に流れの矢印が在れば緑(fake, tmp_path):
    res = run("check", str(picture(tmp_path, [("x0", "x1")])), "--repo", str(fake))
    assert res.returncode == 0, res.stdout


@pytest.mark.parametrize("label,arrows", [("矢印が無い", []), ("向きが逆", [("x1", "x0")])])
def test_絵に無い流れは赤で根治の入口を指す(fake, tmp_path, label, arrows):
    res = run("check", str(picture(tmp_path, arrows)), "--repo", str(fake))
    assert res.returncode == 1, label
    assert "絵に無い流れ: alpha → beta" in res.stdout
    assert 根治の入口を指す(res.stdout.strip().splitlines()[-1])


def test_path_ごと書いた呼び出しも拾う(fake, tmp_path):
    put(fake, "plugins/alpha/scripts/b.py", "CMD = ['python3', 'plugins/beta/scripts/common.py']\n")
    git(fake, "add", "-A")
    res = run("list", "--repo", str(fake))
    assert "plugins/alpha/scripts/b.py:1 common.py" in res.stdout


@pytest.mark.parametrize("label,boxes", [("箱が無い", ("alpha",)), ("箱が重なる", ("alpha", "beta", "beta"))])
def test_部品の箱と結べない絵は照らせない(fake, tmp_path, label, boxes):
    res = run("check", str(picture(tmp_path, [("x0", "x1")], boxes)), "--repo", str(fake))
    assert res.returncode == 2, label
