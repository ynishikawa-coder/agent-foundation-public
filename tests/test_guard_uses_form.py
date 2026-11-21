"""守りの見張りが「実際に使う形」だけを見て、説明の文（行全体を読み切れる commit の文・grep の語・echo・注釈・
docstring）で名を挙げるだけの所では止めないか。緩める向きの直しなので、止めるべき形（実際に動かす・つなぐ形）が
全部まだ止まることを同じ file の注入の試験で示す。入力は全部作り物（道具の名・鍵の名・host は字を割って書く＝この
試験を書く命令が今入っている守りに当たらない）。"""
import importlib.util
import json
import subprocess
import sys

import pytest

from test_guard import ROOT, ask_result, bash, denied, env, hook  # noqa: F401  （env は fixture）

GATE = "check_spec" + "_doc.py"
LOCK = "--" + "lock"
SQL = "DROP " + "TABLE t"
KEY = "OPENAI" + "_API_KEY"
MARK = "PAID_UPSTREAM" + "_GUARD"
OA = "api." + "openai.com"
AN = "api." + "anthropic.com"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str((ROOT / rel).parent))
    spec.loader.exec_module(mod)
    return mod


# ── spec_gate ──
@pytest.mark.parametrize("cmd", [
    'git commit -m "%s を %s で直に呼ぶ手を止める"' % (GATE, LOCK),
    'grep -rn "%s.*%s" plugins/' % (GATE, LOCK),
    'echo "%s %s は止まる"' % (GATE, LOCK),
    "ls  # python3 %s 設計書 %s" % (GATE, LOCK),
    'gh pr create --title t --body "%s %s を挙げるだけ"' % (GATE, LOCK),
])
def test_spec_gate_名を挙げるだけの命令は通す(env, cmd):
    assert not denied(env, bash(cmd)), cmd


@pytest.mark.parametrize("cmd", [
    "python3 型/%s 設計書 %s" % (GATE, LOCK),
    "FOO=1 python3 型/%s 設計書 %s  # 注釈" % (GATE, LOCK),
    'bash -c "python3 型/%s 設計書 %s"' % (GATE, LOCK),
    'echo "python3 型/%s 設計書 %s" | sh' % (GATE, LOCK),
    "python3 - <<'EOF'\nimport subprocess\nsubprocess.run(['python3', '%s', 'x', '%s'])\nEOF" % (GATE, LOCK),
    'X=$(python3 型/%s 設計書 %s)' % (GATE, LOCK),
    "cd d && python3 %s . %s 2>&1 | tail -3" % (GATE, LOCK),
    "for d in a b; do python3 %s $d %s; done" % (GATE, LOCK),
    "(python3 %s 設計書 %s)" % (GATE, LOCK),               # 読み切れない形は字全体で見る（止める側）
    "echo `python3 %s 設計書 %s`" % (GATE, LOCK),
    # 行全体を読み切れない形（heredoc・$( )・redirect）は名を挙げるだけでも前の main と同じく字全体で見る
    "git commit -m \"$(cat <<'EOF'\n%s %s の見張りを直す\nEOF\n)\"" % (GATE, LOCK),
    "cat > /tmp/台帳の行.md <<'EOF'\npython3 %s 設計書 %s\nEOF" % (GATE, LOCK),
])
def test_spec_gate_実際に動かす形は全部まだ止まる(env, cmd):
    assert denied(env, bash(cmd)), cmd


# ── irreversible（離席の間の DB の破棄） ──
@pytest.mark.parametrize("cmd", [
    'git commit -m "離席の間は %s を止める"' % SQL,
    'grep -rn "%s" plugins/' % SQL,
    "git log -S '%s' --oneline" % SQL,
])
def test_irreversible_語を挙げるだけの命令は離席中も通す(env, cmd):
    hook(env, "post", ask_result())
    assert not denied(env, bash(cmd)), cmd


@pytest.mark.parametrize("cmd", [
    "psql -c '%s'" % SQL,
    "cat <<'EOF' | psql\n%s;\nEOF" % SQL,
    "psql <<'EOF'\n%s;\nEOF" % SQL,
    'echo "%s;" | psql' % SQL,
    'git commit -m x && psql -c "%s"' % SQL,
    'R=$(psql -c "%s")' % SQL,
    'sqlite3 a.db "%s"' % SQL,
    "supabase db reset",
])
def test_irreversible_実際に動かす破棄は離席中まだ止まる(env, cmd):
    hook(env, "post", ask_result())
    assert denied(env, bash(cmd)), cmd


def test_irreversible_値の表の足す形も動かす所にだけ当てる(env, tmp_path):
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"guard": {"irreversible_bash_extra": [{"pattern": r"\bmy-db\s+--wipe\b", "why": "DB の破棄"}]}}),
                     encoding="utf-8")
    env["SKILL_VALUES"] = str(table)
    hook(env, "post", ask_result())
    assert denied(env, bash("my-db --wipe"))
    assert not denied(env, bash('git commit -m "my-db --wipe を止める"'))


# ── paid_upstream（試験から有料の上流） ──
def write(path, content):
    return {"tool_name": "Write", "session_id": "s1", "tool_input": {"file_path": path, "content": content}}


@pytest.mark.parametrize("path,content", [
    ("/x/tests/test_a.py", "# 本物の %s は読まない（録画を再生する）\nassert 1\n" % KEY),
    ("/x/tests/test_a.py", '"""%s を読まない試験。"""\nassert 1\n' % KEY),
    ("/x/tests/test_a.py", 'def f():\n    """%s へはつながない。"""\n    return 1\n' % OA),
    ("/x/e2e/a.test.ts", "// %s は偽物\n/* %s へはつながない */\nexpect(1).toBe(1)\n" % (KEY, AN)),
])
def test_paid_upstream_注釈と_docstring_で名を挙げるだけは止めない(env, path, content):
    assert not denied(env, write(path, content)), content


@pytest.mark.parametrize("path,content", [
    ("/x/tests/test_a.py", "import os\nK = os.environ['%s']\n" % KEY),
    ("/x/tests/test_a.py", 'X = 1\nY = """%s"""\n' % OA),                               # 式の中の三重引用はコード
    ("/x/e2e/a.test.ts", 'fetch("https://%s/v1/messages")  // 本物\n' % AN),
    ("/x/tests/data.json", '{"note": "%s"}' % KEY),                                     # 注釈の形が決まらない file は字のまま
])
def test_paid_upstream_本物へつなぐコードは止まる(env, path, content):
    assert denied(env, write(path, content)), content


def test_paid_upstream_コードに書いた関所は通す(env):
    assert not denied(env, write("/x/tests/test_a.py",
                                 "import os\nif os.environ.get('%s'):\n    K = os.environ['%s']\n" % (MARK, KEY)))
    assert not denied(env, write("/x/e2e/a.test.ts", "if (process.env.%s) { k = process.env.%s }\n" % (MARK, KEY)))


def test_paid_upstream_Bash_の_heredoc_も同じ読み方(env):
    deny = "cat > tests/test_llm.py <<'EOF'\nKEY = '%s'\nEOF" % KEY
    named = "cat > tests/test_llm.py <<'EOF'\n# %s\nKEY = '%s'\nEOF" % (MARK, KEY)
    ok = "cat > tests/test_llm.py <<'EOF'\n# %s は録画で\nassert 1\nEOF" % KEY
    gate = "cat > tests/test_llm.py <<'EOF'\nimport os\nif os.environ.get('%s'):\n    KEY = '%s'\nEOF" % (MARK, KEY)
    assert denied(env, bash(deny))
    assert not denied(env, bash(named))           # 注釈で名指す＝前から通す形。関所を見つけられないので書いた後に知らせる
    assert MARK in hook(env, "post", bash(named)).get("additionalContext", "")
    assert not denied(env, bash(ok))
    assert not denied(env, bash(gate))
    assert not hook(env, "post", bash(gate))


# ── pr_text（`…` の中の置き場の字は説明。書いた窓の欄は畳んだ＝tests/test_pr_writer.py） ──
def test_pr_text_コードの中の置き場の字は残った置き場でなく_地の文の置き場は残った置き場(tmp_path, monkeypatch):
    pt = _load("pr_text_uf2", "plugins/guard/scripts/pr_text.py")
    tpl = tmp_path / "整地受領証.template.md"
    tpl.write_text("## 1. 問題\n\n〔問題を 1 文で書く所〕\n", encoding="utf-8")
    monkeypatch.setattr(pt, "_find_sibling", lambda *a: str(tpl))
    said = "## 1. 問題\n\n雛形の `〔問題を 1 文で書く所〕` を埋めた\n"
    left = "## 1. 問題\n\n〔問題を 1 文で書く所〕\n"
    assert not any("残っている" in p for p in pt.check_cleanup(said, "", {}, {}))
    assert any("残っている" in p for p in pt.check_cleanup(left, "", {}, {}))


# ── seal（§6 の節の見出しと、理由の未定の印） ──
def test_seal_コードの囲みと別の節の見出しの中の_6_は_6_の節にしない():
    seal = _load("seal_uf", "plugins/dev-flow/skills/spec-doc/seal.py")
    text = ("## 5. 前\n\n```bash\n# §6 決定照合を照らす\npython3 seal.py x\n```\n\n"
            "## 6. 決定照合\n\n- 作り物の決定 A: 関係なし\n\n## 7. 実装（§6 の結果を受けて・決定照合の後）\n\n- x\n")
    body = seal.section6(text)
    assert [ln for _, ln in body if ln.strip()] == ["- 作り物の決定 A: 関係なし"]


def test_seal_6_の節の見出しが_2_つなら今も止める():
    seal = _load("seal_uf2", "plugins/dev-flow/skills/spec-doc/seal.py")
    with pytest.raises(seal.Abort):
        seal.section6("## 6. 決定照合\n\n- a: 関係なし\n\n## §6 決定照合（続き）\n\n- b: 関係なし\n")


@pytest.mark.parametrize("look,ok", [
    ("直した（理由: 前はまだ無かった口を足した）", True),
    ("関係なし（理由: オーナーに聞いた結果、別の仕事の決定だった）", True),
    ("直した（理由: まだ決まっていない）", False),
    ("直した（理由: まだ未定）", False),
    ("関係なし（理由: オーナーに聞く）", False),
    ("覆す（理由: 聞いてから決める）", True),      # 前の main の形（未定・まだ・聞く…）にも当たらない＝前から済み
    ("覆す（理由: 聞く予定）", False),
    ("直した（理由: TODO）", False),
    ("直した（理由: 保留）", False),
])
def test_seal_理由の未定の印は未決の形だけ(look, ok):
    seal = _load("seal_uf3", "plugins/dev-flow/skills/spec-doc/seal.py")
    assert seal.settled(look) is ok, look
