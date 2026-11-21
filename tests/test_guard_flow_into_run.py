"""字を挙げるだけの命令の「出力」と「変数」が動く側へ流れる形、git・rg の一覧の外の前置き、関所の置き方の一覧の外の
正しい試験、seal の理由の語の一部に当たる未決の印を、わざと入れて今の扱いを示す（レビューの red の 4 つ）。
- 出力・変数を通して動かす形と、一覧の外の前置きは止める側（前の main でも止まっていた形）。
- 字を挙げるだけで動く側へ流れない形（commit の文の $( )・commit の文に使う変数・一覧の中の前置き）は今も通す。
- 共通の関所が探し方の外に在る正しい試験は止めない（前の main でも通っていた形）。関所を見つけられない時は書いた後に知らせる。
入力は全部作り物（名は字を割って書く）。"""
import pytest

from test_guard import ask_result, bash, denied, env, hook  # noqa: F401  （env は fixture）
from test_guard_uses_form import GATE, KEY, LOCK, MARK, SQL, _load, write

RUN = "python3 型/%s 設計書 %s" % (GATE, LOCK)
PSQL = "psql -c \"%s\"" % SQL

FLOW = [
    "eval \"$(echo '{x}')\"",
    "bash -c \"$(echo '{x}')\"",
    "sh -c \"$(printf '{x}')\"",
    "$(echo '{x}')",
    "eval \"$(cat <<'EOF'\n{x}\nEOF\n)\"",
    "x='{x}'; $x",
    "x='{x}'; eval $x",
    "x=$(echo '{x}'); $x",
    "x='{x}'; y=$x; eval \"$y\"",
    "printf -v x '{x}'; eval \"$x\"",
    "git push --receive-pack='{x}' .",
    "git fetch --upload-pack='{x}' .",
    "git push --receive-pack '{x}' .",
    "git log --no-such-option='{x}'",
]


@pytest.mark.parametrize("form", FLOW)
def test_spec_gate_出力と変数と一覧の外の前置きで動かす形は止まる(env, form):
    cmd = form.replace("{x}", RUN)
    assert denied(env, bash(cmd)), cmd


@pytest.mark.parametrize("form", FLOW)
def test_irreversible_出力と変数と一覧の外の前置きで動かす形は離席中止まる(env, form):
    hook(env, "post", ask_result())
    cmd = form.replace("{x}", PSQL)
    assert denied(env, bash(cmd)), cmd


@pytest.mark.parametrize("cmd", [
    "git commit -m \"$(cat <<'EOF'\n%s を止める\nEOF\n)\"" % RUN,
    "msg='%s を止める'; git commit -m \"$msg\"" % RUN,
    "git commit -m '%s を止める' && git push -u origin claude/x" % RUN,
    "git -C . log --oneline -5 --grep='%s'" % RUN,
    "rg -n --hidden '%s' plugins" % RUN,
    "x='%s'; echo \"$x\"" % RUN,
])
def test_spec_gate_字を挙げるだけで動く側へ流れない形は今も通す(env, cmd):
    assert not denied(env, bash(cmd)), cmd


# ── paid_upstream: 関所が探し方の外に在る正しい試験（前の main で通っていた形）は止めない ──
def _noted(env, payload):
    return MARK in hook(env, "post", payload).get("additionalContext", "")


PLACES = [
    ("tests/test_a.py", "# %s: 関所は tests/helpers.py\nfrom . import helpers\nK = helpers.key('%s')\n" % (MARK, KEY)),
    ("tests/test_b.py", "# %s: 関所は tests/realgate.py\npytest_plugins = ['tests.realgate']\nK = '%s'\n" % (MARK, KEY)),
    ("e2e/c.test.js", "// %s: 関所は jest の setupFiles\nconst k = process.env.%s\n" % (MARK, KEY)),
    ("e2e/d.test.ts", "// %s\nimport {{ gate }} from '@/test/gate'\nconst k = process.env.%s\n".replace("{{", "{").replace("}}", "}")
     % (MARK, KEY)),
    ("tests/e.sh", "# %s: 関所は lib.sh\n. ./lib.sh\nK=$%s\n" % (MARK, KEY)),
]


@pytest.mark.parametrize("rel,content", PLACES)
def test_paid_upstream_関所が探し方の外に在る正しい試験は止めず知らせる(env, tmp_path, rel, content):
    path = str(tmp_path / rel)
    assert not denied(env, write(path, content)), content
    assert _noted(env, write(path, content)), content


@pytest.mark.parametrize("rel,content", PLACES)
def test_paid_upstream_印がどこにも無い形は今も止まる(env, tmp_path, rel, content):
    bare = "\n".join(ln for ln in content.splitlines() if MARK not in ln) + "\n"
    assert denied(env, write(str(tmp_path / rel), bare)), bare


def test_paid_upstream_手元で関所を見つけて読めた時は黙って通す(env, tmp_path):
    t = tmp_path / "tests"
    t.mkdir()
    (t / "helpers.py").write_text("import os\nREAL = os.environ.get('%s') == '1'\n" % MARK, encoding="utf-8")
    p = write(str(t / "test_a.py"), "# %s\nfrom .helpers import REAL\nK = '%s'\n" % (MARK, KEY))
    assert not denied(env, p) and not _noted(env, p)


# ── seal: 未決の印が語の一部（未定義）に当たらない ──
@pytest.mark.parametrize("look,want", [
    ("関係なし（理由: 未定義の名を消しただけ）", True),
    ("直した（理由: 未定義の参照を直した）", True),
    ("直した（理由: まだ未定）", False),
    ("関係なし（理由: 未定）", False),
    ("直した（理由: 未定事項は別の行）", False),
])
def test_seal_未決の印は語の一部に当たらない(look, want):
    seal = _load("seal_flow", "plugins/dev-flow/skills/spec-doc/seal.py")
    assert seal.settled(look) is want, look
