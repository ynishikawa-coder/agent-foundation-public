"""scripts/call_flows.py: plugin が使う側の repo の物（値の表・CLAUDE.md・文書と script）を読む流れも拾い、
絵に箱か矢印が無ければ赤にするか／読めない file を黙って飛ばさず照らせないにするか（注入の試験）。

意図: core が使う側の repo の値の表と文書・script を読む流れとその箱も、絵から漏らさず拾う。
課題: 使う側の repo を読む流れとその箱が、レビューの窓が人の目で見つけるまで絵から漏れていた。決まった path・
引数で渡された path を読む流れ（docs-kit・dev-flow）も漏れた（同じ類の 3 回目）。読めない file を黙って飛ばし、
その file の流れを照らさないまま緑を返していた（原因の台帳の行）。
原因: call_flows が土台の道具を呼ぶ流れしか拾わず、読む物を字の形で 1 つずつ挙げて拾う形だった
（なので使う側の repo の在り処を引く形で拾う）。読めない file を既定で止めずに飛ばしていた。
"""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("_call_flows_base_using", Path(__file__).resolve().parent / "test_call_flows.py")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
put, git, run, picture = _base.put, _base.git, _base.run, _base.picture
fake = pytest.fixture(_base.fake.__wrapped__ if hasattr(_base.fake, "__wrapped__") else _base.fake)

TABLE, CLAUDE, FILES = "repo ごとの値の表", "repo 固有の CLAUDE.md", "使う側の repo"


@pytest.fixture
def using(fake):
    put(fake, "plugins/beta/olds.json", '{"rows": [{"files": ["*.md", ":(exclude)tests/**", "config/skill-values.json"],'
        ' "pattern": "a.*b c"}]}\n')
    put(fake, "plugins/alpha/scripts/e.py", "import skill_values\nNAME = 'CLAUDE.md'\n"
        "SELF = sorted(HERE.glob('*.md'))  # 土台の自分の file の glob は使う側の物でない\n")
    git(fake, "add", "-A")
    return fake


def test_使う側の_repo_の物を読む流れを拾う(using):
    res = run("list", "--repo", str(using))
    assert res.returncode == 0, res.stdout + res.stderr
    out = res.stdout
    assert f"beta → {FILES}  plugins/beta/olds.json:1 *.md" in out, out
    assert f"beta → {TABLE}  plugins/beta/olds.json:1 config/skill-values.json" in out, out
    assert f"alpha → {TABLE}  plugins/alpha/scripts/e.py:1 skill_values.py" in out, out
    assert f"alpha → {CLAUDE}  plugins/alpha/scripts/e.py:2 CLAUDE.md" in out, out
    assert f"alpha → {FILES}" not in out          # .py の glob（土台の自分の file）は数えない


BOXES = ("alpha", "beta", TABLE, CLAUDE, FILES)
ALL = [("x0", "x1"), ("x1", "x4"), ("x1", "x2"), ("x0", "x2"), ("x0", "x3")]


def test_使う側の物の箱が無ければ_絵に無い箱で赤(using, tmp_path):
    res = run("check", str(picture(tmp_path, ALL[:4], BOXES[:4])), "--repo", str(using))
    assert res.returncode == 1, res.stdout
    assert f"絵に無い箱: {FILES}（使う側の repo の物）" in res.stdout
    assert f"絵に無い流れ: beta → {FILES}" in res.stdout


@pytest.mark.parametrize("drop", range(1, 5))
def test_使う側の物へ読む矢印が欠ければ赤_全部在れば緑(using, tmp_path, drop):
    res = run("check", str(picture(tmp_path, ALL, BOXES)), "--repo", str(using))
    assert res.returncode == 0, res.stdout
    arrows = ALL[:drop] + ALL[drop + 1:]
    res = run("check", str(picture(tmp_path, arrows, BOXES)), "--repo", str(using))
    assert res.returncode == 1 and "絵に無い流れ" in res.stdout, res.stdout


@pytest.mark.parametrize("label,data", [("utf-8 でない", b"\xff\xfe\x00bad"), ("消えた", None)])
def test_読めない_file_は黙って飛ばさず照らせない(fake, tmp_path, label, data):
    p = fake / "plugins/alpha/skills/s/SKILL.md"
    if data is None:
        p.unlink()                                  # git の一覧には在るが読めない
    else:
        p.write_bytes(data)
    for args in (["list"], ["check", str(picture(tmp_path, [("x0", "x1")]))]):
        res = run(*args, "--repo", str(fake))
        assert res.returncode == 2, (label, res.stdout)
        assert "plugins/alpha/skills/s/SKILL.md が読めず" in res.stdout, res.stdout


@pytest.mark.parametrize("rel,text", [
    ("scripts/l.py", "import os\nROOT = os.environ.get('CLAUDE_PROJECT_DIR')\n"),
    ("scripts/l.py", "import subprocess\nR = subprocess.run(['git', 'rev-parse', '--show-toplevel'])\n"),
    ("scripts/l.py", "from pathlib import Path\nR = Path.cwd()\n"),
    ("scripts/l.py", "import os\nR = os.getcwd()\n"),
    ("scripts/l.py", "def f(data):\n    return data.get('cwd')\n"),
    ("scripts/l.mjs", "const r = process.cwd();\n"),
    ("scripts/l.sh", 'cd "$CLAUDE_PROJECT_DIR"\n'),
    ("scripts/l.sh", "root=$(git rev-parse --show-toplevel)\n"),
])
def test_使う側の_repo_の在り処を引く形を読む流れに数える(fake, rel, text):
    put(fake, f"plugins/alpha/{rel}", text)
    git(fake, "add", "-A")
    res = run("list", "--repo", str(fake))
    assert f"alpha → {FILES}" in res.stdout, (rel, text, res.stdout)


@pytest.mark.parametrize("rel,text", [
    ("scripts/l.py", '"""CLAUDE_PROJECT_DIR を読む（説明の文）"""\n# os.getcwd() は呼ばない\n'),
    ("scripts/l.mjs", "// process.cwd() は説明\n/* process.cwd() */\nconst a = 1;\n"),
    ("scripts/l.sh", "# $CLAUDE_PROJECT_DIR は説明\necho hi\n"),
])
def test_説明の文の在り処の名は数えない(fake, rel, text):
    put(fake, f"plugins/alpha/{rel}", text)
    git(fake, "add", "-A")
    res = run("list", "--repo", str(fake))
    assert f"alpha → {FILES}" not in res.stdout, (rel, res.stdout)
