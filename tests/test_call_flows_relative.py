"""scripts/call_flows.py: 相対の path で開く形（今の dir に暗に頼る）も、使う側の repo を読む流れに数えるか（注入の試験）。

なぜ在るか: 在り処を名指して引く形（CLAUDE_PROJECT_DIR・git rev-parse・Path.cwd() など）だけを拾い、注釈に「在り処を
引かずに使う側の repo を読む道は無い」と書いていた。open("docs/x.md") のように相対の path で開くと在り処を引かずに読め、
拾わずに緑を返しうる（原因の台帳の行・土台 PR #37 の 3 回目のレビュー）。
"""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("_call_flows_base_relative", Path(__file__).resolve().parent / "test_call_flows.py")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
put, git, run, picture = _base.put, _base.git, _base.run, _base.picture
fake = pytest.fixture(_base.fake.__wrapped__ if hasattr(_base.fake, "__wrapped__") else _base.fake)

FILES = "使う側の repo"


@pytest.mark.parametrize("rel,text", [
    ("scripts/l.py", 'T = open("docs/x.md", encoding="utf-8").read()\n'),
    ("scripts/l.py", 'from pathlib import Path\nT = Path("docs/全体の絵.json").read_text()\n'),
    ("scripts/l.py", 'import os\nOK = os.path.exists("config/x.json")\n'),
    ("scripts/l.py", 'import glob\nFS = glob.glob("docs/*.md")\n'),
    ("scripts/l.py", 'import os\nFS = os.listdir("docs")\n'),
    ("scripts/l.mjs", 'import fs from "node:fs";\nconst t = fs.readFileSync("docs/x.md", "utf8");\n'),
    ("scripts/l.mjs", "import { existsSync } from 'node:fs';\nconst ok = existsSync('docs/x.md');\n"),
])
def test_相対の_path_で開く形を読む流れに数える(fake, rel, text):
    put(fake, f"plugins/alpha/{rel}", text)
    git(fake, "add", "-A")
    res = run("list", "--repo", str(fake))
    assert f"alpha → {FILES}" in res.stdout, (rel, text, res.stdout)
    assert "相対の path で開く" in res.stdout


def test_相対の_path_で読む流れの矢印が絵に無ければ赤(fake, tmp_path):
    put(fake, "plugins/alpha/scripts/l.py", 'T = open("docs/x.md").read()\n')
    git(fake, "add", "-A")
    res = run("check", str(picture(tmp_path, [("x0", "x1")], ("alpha", "beta", FILES))), "--repo", str(fake))
    assert res.returncode == 1, res.stdout
    assert f"絵に無い流れ: alpha → {FILES}" in res.stdout


@pytest.mark.parametrize("rel,text", [
    ("scripts/l.py", 'from pathlib import Path\nHERE = Path(__file__).parent\nT = (HERE / "x.md").read_text()\n'),
    ("scripts/l.py", 'from pathlib import Path\nFS = sorted(Path(__file__).parent.glob("skills/*/SKILL.md"))\n'),
    ("scripts/l.py", 'def f(p):\n    with p.open("a") as g:\n        g.write("x")\n'),
    ("scripts/l.py", 'T = open("/etc/hostname").read()\nU = open("~/.x")\n'),
    ("scripts/l.py", '"""open("docs/x.md") は説明の文"""\n# Path("docs/x") も説明\n'),
    ("scripts/l.mjs", '// readFileSync("docs/x.md") は説明\nconst t = fs.readFileSync(new URL("./x.md", import.meta.url));\n'),
])
def test_土台の自分の_file_と説明の文は数えない(fake, rel, text):
    put(fake, f"plugins/alpha/{rel}", text)
    git(fake, "add", "-A")
    res = run("list", "--repo", str(fake))
    assert f"alpha → {FILES}" not in res.stdout, (rel, res.stdout)
