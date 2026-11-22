"""scripts/call_flows.py: 説明の文（docstring・注釈・人への文・手順の文で名を挙げるだけ）の中の道具の名を流れに数えず、
実際に呼ぶ・import する・実行する形だけを拾うか（注入の試験）。

意図: 実際の呼び出しだけを流れと数え、説明の文に名が出るだけの物を流れにしない（絵に偽の流れを足させない）。
課題: core の refs.py の docstring が guard の values_keys.py を「同じ exit の約束」と書くだけで core → guard、
guard の values_keys.py の docstring が core の道具を挙げるだけで guard → core が「絵に無い流れ」で赤になり、
絵に偽の流れを足すか、注釈の言い方を替えて逃げる圧になった。
原因: call_flows は file の各行を字で探し、名が在れば呼んだと数えていた。
"""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("_call_flows_base_prose", Path(__file__).resolve().parent / "test_call_flows.py")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
put, git, run = _base.put, _base.git, _base.run
fake = pytest.fixture(_base.fake.__wrapped__ if hasattr(_base.fake, "__wrapped__") else _base.fake)

# 説明の文だけで beta の judge.py を挙げる（呼ばない）。どれも流れに数えてはいけない。
PROSE = {
    "plugins/alpha/scripts/p.py": (
        '"""judge.py と同じ exit の約束（plugins/beta/scripts/judge.py）。"""\n'
        "# judge.py の決まりに揃える\n"
        "def f():\n"
        '    """judge.py を参考にした。"""\n'
        '    return "judge.py を回して照らす"  # 人への文\n'),
    "plugins/alpha/scripts/q.mjs": (
        "// beta の judge.py と同じ決まり\n"
        "/* plugins/beta/scripts/judge.py を写さない */\n"
        "const msg = 'judge.py を回して照らす';\n"
        "const re = /judge.py/;\n"),
    "plugins/alpha/scripts/r.sh": (
        "# judge.py と同じ exit の約束\n"
        'echo "judge.py を回して照らす"\n'),
    "plugins/alpha/lib/schema.json": '{"k": {"description": "judge.py が見る値（plugins/beta/scripts/judge.py）"}}\n',
    "plugins/alpha/skills/u/SKILL.md": (
        "- 形の正本は beta の judge.py（`judge.py`・`plugins/beta/scripts/judge.py`）と同じ。\n"),
    "plugins/alpha/skills/u/page.html": "<p>python3 plugins/beta/scripts/judge.py check</p>\n",
}

# 本当に呼ぶ形。どれも 1 つずつ拾う。
CALLS = {
    "py の path の値": ("plugins/alpha/scripts/c1.py", "P = 'plugins/beta/scripts/judge.py'\n"),
    "py の名の値": ("plugins/alpha/scripts/c2.py", "TOOL = ['python3', 'judge.py']\n"),
    "py の join": ("plugins/alpha/scripts/c3.py", "import os\nP = os.path.join('scripts', 'judge.py')\n"),
    "py の隣の plugin の口": ("plugins/alpha/scripts/c4.py",
                           "P = sibling_plugin_file('beta', os.path.join('scripts', 'common.py'))\n"),
    "py の import": ("plugins/alpha/scripts/c5.py", "import judge\n"),
    "js の字の値": ("plugins/alpha/scripts/c6.mjs", "const P = 'plugins/beta/scripts/judge.py';\n"),
    "sh の命令": ("plugins/alpha/scripts/c7.sh", "python3 \"$ROOT/plugins/beta/scripts/judge.py\" --x  # 照らす\n"),
    "json の命令": ("plugins/alpha/hooks/hooks.json", '{"command": "python3 plugins/beta/scripts/judge.py check"}\n'),
    "手順の命令": ("plugins/alpha/skills/v/SKILL.md", "1. `python3 <beta>/scripts/judge.py check` を回す。\n"),
    "手順の直の実行": ("plugins/alpha/skills/w/SKILL.md", "1. `judge.py check` の出力を見る。\n"),
    "手順のコードの塊": ("plugins/alpha/skills/x/SKILL.md", "```bash\nnode plugins/beta/scripts/judge.py\n```\n"),
}


def _only(repo, files):
    put(repo, "plugins/alpha/skills/s/SKILL.md", "1. 呼ばない。\n")         # fake の既定の 1 本を外す
    for rel, text in files.items():
        put(repo, rel, text)
    git(repo, "add", "-A")
    return run("list", "--repo", str(repo))


def test_説明の文だけで名を挙げる_file_は流れに数えない(fake):
    res = _only(fake, PROSE)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "", res.stdout


@pytest.mark.parametrize("label", list(CALLS))
def test_本当に呼ぶ形は拾う(fake, label):
    rel, text = CALLS[label]
    res = _only(fake, {**PROSE, rel: text})
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip().splitlines() and all(ln.startswith("alpha → beta  ") for ln in res.stdout.strip().splitlines()), \
        (label, res.stdout)
    assert f"{rel}:" in res.stdout, (label, res.stdout)
    assert "ほか" not in res.stdout, (label, res.stdout)         # 説明の文の行は証拠に混ざらない


def test_読めないコードは黙って飛ばさず照らせない(fake, tmp_path):
    put(fake, "plugins/alpha/scripts/broken.py", "def (:\n")
    git(fake, "add", "-A")
    res = run("check", str(_base.picture(tmp_path, [("x0", "x1")])), "--repo", str(fake))
    assert res.returncode == 2, res.stdout
    assert "broken.py" in res.stdout
