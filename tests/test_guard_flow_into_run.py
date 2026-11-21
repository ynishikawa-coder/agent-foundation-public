"""字を挙げるだけの命令の「出力」と「変数」が動く側へ流れる形、git・rg の一覧の外の前置き、関所の置き方の一覧の外の
正しい試験、seal の理由の語の一部に当たる未決の印を、わざと入れて今の扱いを示す（レビューの red の 2 回目と 3 回目）。
- 出力・変数を通して動かす形と、一覧の外の前置きは止める側（前の main でも止まっていた形）。
- 代入だけの並び（x=…・printf -v）は使い所を追わず常に動く側（export・set -a・heredoc の中・declare -n で抜けた）。
  file へ書いた後ろに素の道具でない並びが在れば書いた中身も動く側（.git/hooks・Makefile を道具が暗に読む）。
- 字を挙げるだけで動く側へ流れない形（commit の文の $( )・一覧の中の前置き）は今も通す。
- paid_upstream の Edit は置き換えの後にだけ在るコードの行の印を数える。seal は前の main より止める側を広げない。
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
    # 3 回目の red: 変数の使い所を 1 つずつ追う形が抜ける道（代入だけの並びは常に動く側に数える）
    "GIT_PAGER='{x}'; export GIT_PAGER; git log",
    "PAGER='{x}'; export PAGER; git log -p",
    "set -a; GIT_PAGER='{x}'; git log",
    "x='{x}'; bash <<EOF\n$x\nEOF",
    "x='{x}'; cat <<EOF | sh\n$x\nEOF",
    "x='{x}'; declare -n r=x; eval \"$r\"",
    # 3 回目の red: 道具が名を挙げずに暗に読む file（書いた後ろに素の道具でない並びが在れば、書いた中身を動く側に数える）
    "printf '#!/bin/sh\\n{x}\\n' > .git/hooks/pre-commit; git commit -m m",
    "printf 'all:\\n\\t{x}\\n' > Makefile; make",
    "msg='{x}'; git commit -m \"$msg\"",
    "x='{x}'; echo \"$x\"",
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
    "git commit -m '%s を止める' && git push -u origin claude/x" % RUN,
    "git -C . log --oneline -5 --grep='%s'" % RUN,
    "rg -n --hidden '%s' plugins" % RUN,
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


# ── paid_upstream: Edit は置き換えの後にだけ在るコードの行に在る印を数える（印の数の増えでなく） ──
def _edit(path, old, new):
    return {"tool_name": "Edit", "session_id": "s1",
            "tool_input": {"file_path": path, "old_string": old, "new_string": new}}


def test_paid_upstream_Edit_で偽物を同じ数のまま本物へ書き換えると止まる(env, tmp_path):
    t = tmp_path / "tests"
    t.mkdir()
    p = t / "test_x.py"
    p.write_text("K = fake('%s')\n" % KEY, encoding="utf-8")
    assert denied(env, _edit(str(p), "fake('%s')" % KEY, "os.environ['%s']" % KEY))


def test_paid_upstream_Edit_で注釈を足すだけ_前から在る行に触れないなら通す(env, tmp_path):
    t = tmp_path / "tests"
    t.mkdir()
    p = t / "test_x.py"
    p.write_text("import os\nK = os.environ['%s']\n\n\ndef test_a():\n    assert 1\n" % KEY, encoding="utf-8")
    assert not denied(env, _edit(str(p), "    assert 1\n", "    # %s は前から在る\n    assert 1\n" % KEY))
    assert not denied(env, _edit(str(p), "def test_a():", "def test_b():"))


# ── seal: 前の main で見つかっていた §6 の見出しは全部見つかる・別の節の番号の見出しが指すだけの物は除く ──
@pytest.mark.parametrize("head", [
    "6. 決定照合", "§6 決定照合", "決定照合", "6 決定照合", "6章 決定照合", "６. 決定照合", "第6節 決定照合",
    "6) 決定照合", "15 §6 決定照合",
])
def test_seal_前の_main_で見つかった_6_の見出しは今も見つかる(head):
    seal = _load("seal_heads", "plugins/dev-flow/skills/spec-doc/seal.py")
    body = seal.section6("## %s\n\n- 作り物の決定 A: 関係なし\n" % head)
    assert body is not None and any("作り物の決定 A" in ln for _, ln in body), head


@pytest.mark.parametrize("head", ["7. 実装（§6 の結果を受けて）", "2. 決定照合の進め方", "15. 決定照合の後の手順"])
def test_seal_別の節の番号で始まる見出しが指すだけなら_6_の節に数えない(head):
    seal = _load("seal_heads2", "plugins/dev-flow/skills/spec-doc/seal.py")
    body = seal.section6("## 6. 決定照合\n\n- 作り物の決定 A: 関係なし\n\n## %s\n\n- x\n" % head)
    assert [ln for _, ln in body if ln.strip()] == ["- 作り物の決定 A: 関係なし"], head


# ── seal: 未決の印が語の一部（未定義・決める・これから・聞いてから）に新しく当たらない ──
@pytest.mark.parametrize("look", [
    "直した（理由: 型が決める範囲の外）",
    "関係なし（理由: 呼ぶ側が決める値で範囲外）",
    "直した（理由: 値の表で決める形に直した）",
    "関係なし（理由: これからの変更に影響しない）",
    "直した（理由: 聞いてから直した経緯を記録）",
])
def test_seal_前の_main_で済みだった理由は今も済み(look):
    seal = _load("seal_reasons", "plugins/dev-flow/skills/spec-doc/seal.py")
    assert seal.settled(look), look


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
