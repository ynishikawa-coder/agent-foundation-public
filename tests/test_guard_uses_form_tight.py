"""守りの見張りを「実際に使う形」だけを見る形にした直し（test_guard_uses_form.py）が、緩めすぎていないか。
前の main で止まっていた形のうち、実際に動かす・つなぐ・雛形を残す形を、わざと入れて今も拒むことを示す
（レビューで挙がった類: git・gh・rg の中で命令を動かす形／書いた file を同じ命令で流す形／値の表が git・gh を狙う行／
括弧の中の三重引用・断片の docstring／`…` を含む雛形の置き場／文の途中の未決の理由）。
同じく、共通の関所が別の file に在る正しい試験は止めないことも示す。入力は全部作り物（名は字を割って書く）。"""
import json

import pytest

from test_guard import ask_result, bash, denied, env, hook  # noqa: F401  （env は fixture）
from test_guard_uses_form import AN, GATE, KEY, LOCK, MARK, OA, SQL, _load, write


# ── spec_gate: git・gh・rg の中で命令を動かす形 ──
@pytest.mark.parametrize("cmd", [
    "git rebase --exec 'python3 型/%s 設計書 %s' HEAD~2" % (GATE, LOCK),
    "git rebase -x 'python3 型/%s 設計書 %s' HEAD~2" % (GATE, LOCK),
    "git -c alias.x='!python3 型/%s 設計書 %s' x" % (GATE, LOCK),
    "git -c core.pager='python3 型/%s 設計書 %s' log" % (GATE, LOCK),
    "GIT_PAGER='python3 型/%s 設計書 %s' git log" % (GATE, LOCK),
    "rg --pre 'python3 型/%s 設計書 %s' x" % (GATE, LOCK),
    "gh alias set x --shell 'python3 型/%s 設計書 %s'" % (GATE, LOCK),
    "printf 'python3 型/%s 設計書 %s' > a.sh && bash a.sh" % (GATE, LOCK),
    "cat > a.sh <<'EOF'\npython3 型/%s 設計書 %s\nEOF\nsh a.sh" % (GATE, LOCK),
])
def test_spec_gate_道具の中で動かす形と書いてから流す形は止まる(env, cmd):
    assert denied(env, bash(cmd)), cmd


def test_spec_gate_書いた後ろに_git_が在っても止まる(env):
    """git add・git commit も書いた file を暗に読める（.git/hooks・.gitattributes の駆動）。file を書く手が在る行は読み切れない形（前の main も止めていた）。"""
    assert denied(env, bash("cat > メモ.md <<'EOF'\npython3 %s 設計書 %s\nEOF\ngit add メモ.md" % (GATE, LOCK)))


@pytest.mark.parametrize("tail", ["", "\ncat メモ.md", "\ngrep -n 設計書 メモ.md | head -3"])
def test_spec_gate_file_へ書く形は後ろに何が在っても前の_main_と同じく字全体で見る(env, tail):
    """file を書く手（redirect・heredoc）が在る行は読み切れない形＝外さない（後ろの道具が暗に読むかを追わない）。"""
    assert denied(env, bash("cat > メモ.md <<'EOF'\npython3 %s 設計書 %s\nEOF%s" % (GATE, LOCK, tail)))


# ── irreversible: 書いてから流す形・git の中で動かす形・値の表が git・gh を狙う行 ──
@pytest.mark.parametrize("cmd", [
    "printf '%s;' > q.sql && psql -f q.sql" % SQL,
    "printf '%s;' > q.sql; psql < q.sql" % SQL,
    "git rebase -x 'psql -c \"%s\"' HEAD~1" % SQL,
    "git -c core.pager='psql -c \"%s\"' log" % SQL,
])
def test_irreversible_書いてから流す形と_git_の中の破棄は離席中止まる(env, cmd):
    hook(env, "post", ask_result())
    assert denied(env, bash(cmd)), cmd


def test_irreversible_値の表が_git_gh_を狙う行は当たる(env, tmp_path):
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"guard": {"irreversible_bash_extra": [
        {"pattern": r"\bgit\s+push\s+(?:\S+\s+)*--force\b", "why": "強制 push"},
        {"pattern": r"\bgh\s+repo\s+delete\b", "why": "repo の削除"}]}}), encoding="utf-8")
    env["SKILL_VALUES"] = str(table)
    hook(env, "post", ask_result())
    assert denied(env, bash("git push origin main --force"))
    assert denied(env, bash("gh repo delete o/r --yes"))
    assert not denied(env, bash('git commit -m "gh repo delete と git push --force を止める"'))


# ── paid_upstream: 括弧の中の三重引用・Edit の断片・共通の関所 ──
@pytest.mark.parametrize("content", [
    'import json\nX = json.dumps(\n    """{"url": "https://%s/v1"}"""\n)\n' % OA,
    'X = f(1,\n      """%s""")\n' % AN,
    'X = \\\n    """%s"""\n' % OA,
])
def test_paid_upstream_括弧の中と続きの行の三重引用はコード(env, content):
    assert denied(env, write("/x/tests/test_a.py", content)), content


def test_paid_upstream_Edit_の断片は手元の全体に当てて読む(env, tmp_path):
    f = tmp_path / "tests" / "test_a.py"
    f.parent.mkdir()
    f.write_text('def f():\n    """説明。"""\n    return 1\n', encoding="utf-8")
    # 断片が docstring を閉じる """ で始まっても、全体で読めば後ろはコード
    frag = {"tool_name": "Edit", "session_id": "s1", "tool_input": {
        "file_path": str(f), "old_string": '"""\n    return 1\n', "new_string": '"""\n    K = "%s"\n    return 1\n' % OA}}
    assert denied(env, frag)
    multi = {"tool_name": "MultiEdit", "session_id": "s1", "tool_input": {
        "file_path": str(f), "edits": [{"old_string": "return 1", "new_string": "return '%s'" % AN}]}}
    assert denied(env, multi)
    # 注釈を足すだけの置き換え・前から在る行を残す置き換えは止めない
    note = {"tool_name": "Edit", "session_id": "s1", "tool_input": {
        "file_path": str(f), "old_string": "return 1", "new_string": "return 1  # %s へはつながない" % OA}}
    assert not denied(env, note)
    # 組めない（old_string が無い）断片は字のまま見る＝止める側
    lost = {"tool_name": "Edit", "session_id": "s1", "tool_input": {
        "file_path": str(f), "old_string": "無い字", "new_string": "# %s\n" % KEY}}
    assert denied(env, lost)


def _noted(env, payload):
    return MARK in hook(env, "post", payload).get("additionalContext", "")


def test_paid_upstream_共通の関所が_conftest_か_import_する補助に在れば注釈の印で黙って通す(env, tmp_path):
    t = tmp_path / "tests"
    t.mkdir()
    body = "# %s: 本物へは conftest の関所で切り替える\nimport os\nK = os.environ.get('%s')\n" % (MARK, KEY)
    # 関所を見つけられない＝止めない（前から通す形）が、書いた後に知らせる
    assert not denied(env, write(str(t / "test_a.py"), body)) and _noted(env, write(str(t / "test_a.py"), body))
    (t / "conftest.py").write_text("# %s を挙げるだけ\n" % MARK, encoding="utf-8")
    assert not denied(env, write(str(t / "test_a.py"), body)) and _noted(env, write(str(t / "test_a.py"), body))
    (t / "conftest.py").write_text("import os\nREAL = bool(os.environ.get('%s'))\n" % MARK, encoding="utf-8")
    assert not denied(env, write(str(t / "test_a.py"), body)) and not _noted(env, write(str(t / "test_a.py"), body))
    assert not denied(env, bash("cat > %s <<'EOF'\n%sEOF" % (t / "test_b.py", body)))   # heredoc で書く形も同じ
    u = tmp_path / "u" / "tests"
    u.mkdir(parents=True)
    (u / "gate.py").write_text("import os\nREAL = os.environ.get('%s') == '1'\n" % MARK, encoding="utf-8")
    assert not denied(env, write(str(u / "test_c.py"), "# %s\nfrom gate import REAL\nK = '%s'\n" % (MARK, KEY)))
    assert denied(env, write(str(u / "test_c.py"), "from gate import REAL\nK = '%s'\n" % KEY))   # 印を名指さない


@pytest.mark.parametrize("path,content", [
    ("/x/tests/run.sh", 'echo "${#ARR[@]}" && curl https://%s/v1\n' % OA),
    ("/x/tests/ci.yml", "url: https://%s/v1#frag\n" % AN),
    ("/x/tests/run.sh", "N=$#; K=$%s\n" % KEY),
])
def test_paid_upstream_shell_と_YAML_の語の中の_シャープ_は注釈でない(env, path, content):
    assert denied(env, write(path, content)), content


# ── pr_text: `…` を含む雛形の置き場 ──
def test_pr_text_逆引用を含む雛形の置き場が残れば数える(tmp_path, monkeypatch):
    pt = _load("pr_text_tight", "plugins/guard/scripts/pr_text.py")
    tpl = tmp_path / "整地受領証.template.md"
    tpl.write_text("## 2. 原因\n\n- 〔`場所` — 何が起きている・起きうるか〕\n\n## 3. 解決\n\n- 〔`畳む物の path や名前`〕\n",
                   encoding="utf-8")
    monkeypatch.setattr(pt, "_find_sibling", lambda *a: str(tpl))
    left = tpl.read_text(encoding="utf-8")
    probs = pt.check_cleanup(left, "", {}, {})
    assert any("残っている" in p for p in probs), probs
    assert any("残っている" in p for p in pt.check_cleanup("## 2. 原因\n\n- x\n\n## 3. 解決\n\n- 〔`畳む物の path や名前`〕\n",
                                                          "", {}, {}))
    done = "## 2. 原因\n\n- `a.py:1` — 字で決める\n\n## 3. 解決\n\n- [同梱] `b.py` — 要らない\n"
    assert not any("残っている" in p for p in pt.check_cleanup(done, "", {}, {}))


def test_pr_text_実物の雛形の置き場は全部数える(tmp_path):
    pt = _load("pr_text_tight2", "plugins/guard/scripts/pr_text.py")
    from test_guard import ROOT
    tpl = ROOT / "plugins/dev-flow/skills/preimpl-cleanup/整地受領証.template.md"
    _heads, holders = pt.template_parts(str(tpl))
    body = tpl.read_text(encoding="utf-8")
    assert holders and all(pt.holder_left(h, pt.COMMENT.sub(" ", body)) for h in holders)


# ── seal: 未決の文の後に文が続く理由 ──
@pytest.mark.parametrize("look", [
    "直した（理由: まだ決まっていないが仮置き）",
    "直した（理由: 後で聞くので仮に直した）",
    "直した（理由: まだ途中だが進める）",
    "関係なし（理由: 後で聞くが今は外す）",
])
def test_seal_未決の後に文が続いても未決(look):
    seal = _load("seal_tight", "plugins/dev-flow/skills/spec-doc/seal.py")
    assert seal.settled(look) is False, look


@pytest.mark.parametrize("look", [
    "直した（理由: 前はまだ無かったので口を足した）",
    "関係なし（理由: オーナーに聞いた結果、別の仕事の決定だった）",
])
def test_seal_経緯の説明は済み(look):
    seal = _load("seal_tight2", "plugins/dev-flow/skills/spec-doc/seal.py")
    assert seal.settled(look) is True, look
