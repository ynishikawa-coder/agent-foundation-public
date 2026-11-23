"""行で照らす物は、相手（GitHub の表示・JSONL・YAML・git）と同じ行の区切り（\\n・\\r\\n・\\r だけ）で照らす。

str.splitlines() は U+2028・U+2029・U+0085・\\v・\\f などでも切る。相手が 1 行と読む物を AI の道具だけが
2 行に割ると、見えない見出し・偽の締めの行・落ちる JSONL の行・すり抜ける顧客の語が生まれる。
行の区切りの口は skill-values/af_lines.py の 1 本（plugin へは lib/ の symlink で届く）。ここでは
相手が 1 行と読む物に U+2028 を挟み、各々の道具が 1 行のまま照らす事を見る（外すと赤）。
"""
import hashlib
import hmac
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LS = "\u2028"   # GitHub・JSONL・YAML・git では行の区切りでない字
sys.dont_write_bytecode = True   # 写しの置き場（plugins/）に __pycache__ を作らない


def load(name, rel, extra=None):
    for p in [Path(rel).parent] + list(extra or []):
        s = str(ROOT / p)
        if s not in sys.path:
            sys.path.insert(0, s)
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_行の区切りの口は_改行だけで切る():
    af = load("af_lines", "skill-values/af_lines.py")
    assert af.text_lines("a" + LS + "b\n") == ["a" + LS + "b"]
    assert af.text_lines("a\r\nb\rc\n") == ["a", "b", "c"]
    assert af.text_lines("a\u0085b\u2029c\x0bd\x0ce") == ["a\u0085b\u2029c\x0bd\x0ce"]
    assert af.text_lines("") == [] and af.text_lines(None) == []
    for s in ("a\n\nb\n", "a\n", "a", "\n", "a\r\n\r\n"):
        assert af.text_lines(s) == s.splitlines()   # 改行だけの文では行の数も中身も splitlines と同じ


def test_口は_1_本で_plugin_へは_symlink_で届く():
    src = (ROOT / "skill-values" / "af_lines.py").resolve()
    for plug in ("guard", "session-watch", "dev-flow", "checker"):
        p = ROOT / "plugins" / plug / "lib" / "af_lines.py"
        assert p.is_symlink(), p
        assert p.resolve() == src, p


SHIPPED = ["plugins", "scripts", "public-guard", "skill-values"]


def test_配る道具に_splitlines_の呼び出しが無い():
    """__doc__ の 1 行目（argparse の説明）は人が書いた文の頭で、相手の行と照らさない＝外す。"""
    bad = []
    for top in SHIPPED:
        for p in sorted((ROOT / top).rglob("*.py")):
            if p.is_symlink():
                continue
            for n, ln in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
                code = ln.split("#", 1)[0]
                if re.search(r"\.splitlines\(", code) and "__doc__" not in code:
                    bad.append(f"{p.relative_to(ROOT)}:{n}")
    assert not bad, "行は af_lines.text_lines で切る（splitlines は U+2028 などでも切る）: " + ", ".join(bad)


def test_顧客の語は_U2028_で割っても行の照らしをすり抜けない():
    g = load("pg_guard", "public-guard/guard.py")
    key = b"k" * 16
    digests = {hmac.new(key, g.fold("カキクケ").encode("utf-8"), hashlib.sha256).digest()[:g.DIGEST]}
    assert g.customer_hits("x", "カキクケ", [], (key, digests))
    assert g.customer_hits("x", "カキ" + LS + "クケ", [], (key, digests)) == ["x: 顧客の語"]


def test_判定の見出しは_GitHub_で見える行だけ数える():
    vf = load("verdict_form", "plugins/checker/scripts/verdict_form.py")
    good = """レビューした窓: session_REVIEW01 判定: green
見た先端: 0123456789ab
決まりの版: 0123456789ab
job: 作り物

## verdict
green

## 点
- 1 依頼の充足: pass
- 2 触った path: pass
- 3 別の目: 書いた窓 session_WRITER01 ≠ この窓
- 4 回帰: pass（check_all: 緑）
- 5 秘密・顧客の物: pass
- 6 当て物・本番の効き目: pass
- 7 なくす物: pass
- 8 歯と口・注入の試験: N/A
- 9 文書の事実: pass
- 10 退役・迂回・呼ぶ側: N/A
- 11 言語ごとの点: N/A
- 12 既定で止まる: N/A

## 所見
- [台帳へ｜整地] 作り物の気づき
"""
    assert vf.check(good, writer="session_WRITER01") == []
    hidden = good.replace("\n## verdict\n", "\n作り物" + LS + "## verdict\n")   # GitHub では 1 行＝見出しでない
    assert vf.check(hidden, writer="session_WRITER01") != []


def test_PR_本文の窓の_id_は_偽の頭の欄の行で落ちない():
    pt = load("pr_text", "plugins/guard/scripts/pr_text.py")
    body = "本文 session_01AAAAAAAAAAAAAAAAAAAAAA" + LS + "書いた窓: session_01BBBBBBBBBBBBBBBBBBBBBB\n"
    assert "session_01BBBBBBBBBBBBBBBBBBBBBB" in pt.visible_prose(body)


def test_締めの_2_行は_1_行に並べた物を締めと取らない():
    sw = load("session_watch", "plugins/session-watch/scripts/session_watch.py")
    assert sw.split_close("本文\nAI がこの後やること: なし\nあなたがやること: なし")[1] is not None
    assert sw.split_close("本文\nAI がこの後やること: なし" + LS + "あなたがやること: なし")[1] is None


def test_JSONL_の行は_生の_U2028_を含んでも落ちない(tmp_path):
    gc = load("guard_common", "plugins/guard/scripts/guard_common.py")
    p = tmp_path / "t.jsonl"
    rows = [{"a": "前" + LS + "後"}, {"b": 1}]
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert LS in p.read_text(encoding="utf-8")
    assert list(gc.iter_rows(p)) == rows


def test_設計書の_6_節は_見えない見出しを節と取らない():
    seal = load("seal", "plugins/dev-flow/skills/spec-doc/seal.py")
    assert seal.section6("# 設計\n## 6. 決定照合\n- x\n") == [(3, "- x")]
    assert seal.section6("# 設計\n## 5. 前\n本文" + LS + "## 6. 決定照合\n- x\n") is None


def test_パックの鍵らしい塊の行番号は_相手の行で数える():
    cp = load("codex_pack", "plugins/dev-flow/skills/codex/codex_pack.py")
    tok = "0a1b2c3d4e5f60718293a4b5c6d7e8f901234567"
    hits = cp.entropy_hits("前" + LS + "後\n" + tok + "\n")
    assert hits and {h[1] for h in hits} == {2}


def test_workflow_の値は_U2028_で鍵に割れない():
    wr = load("workflow_reader", "public-guard/workflow_reader.py")
    d = wr.load("name: a" + LS + "b: c\non: push\n")
    assert "b" not in d and "on" in d


def test_人の_CLAUDE_md_の行は_知らせの印で割れて消えない(tmp_path, monkeypatch):
    sp = load("setup_plugins", "scripts/setup_plugins.py")
    monkeypatch.setenv("HOME", str(tmp_path))
    md = tmp_path / ".claude" / "CLAUDE.md"
    md.parent.mkdir()
    mine = "人の行" + LS + sp.MARK + " 人の続き"
    md.write_text(mine + "\n" + sp.MARK + " 古い知らせ\n", encoding="utf-8")
    sp.notice("新しい知らせ")
    text = md.read_text(encoding="utf-8")
    assert mine + "\n" in text
    assert "古い知らせ" not in text and sp.MARK + " 新しい知らせ\n" in text


def test_衝突の印は_1_行に並べた物を印と取らない(tmp_path):
    cm = load("conflict_markers", "scripts/conflict_markers.py")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a.txt").write_text("前" + LS + "=======\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("前\n=======\n", encoding="utf-8")
    found, unread = cm.scan(tmp_path)
    assert unread == []
    assert [f.split(":")[0] for f in found] == ["b.txt"]


def test_読み戻しの_import_は_相手の区切りの口を使う():
    """call_flows・changelog・pr_shape・measure_load・plugin_smoke も同じ口から読む（core の 3 本・入口・af_tally は
    箱へ単独で写されるので import せず、\n に揃った字を \n だけで切る＝下の試験が照らす）。"""
    names = ["scripts/call_flows.py", "scripts/changelog.py", "scripts/pr_shape.py", "scripts/measure_load.py",
             "scripts/plugin_smoke.py", "plugins/guard/scripts/guard_common.py",
             "plugins/session-watch/scripts/session_watch.py", "plugins/checker/scripts/verdict_form.py",
             "plugins/dev-flow/skills/spec-doc/seal.py", "plugins/dev-flow/skills/codex/codex_pack.py",
             "scripts/conflict_markers.py"]
    miss = [n for n in names if "from af_lines import" not in (ROOT / n).read_text(encoding="utf-8")]
    assert not miss, miss
    assert os.path.exists(ROOT / "skill-values" / "af_lines.py")


def test_core_の照らしの行番号は相手の行で数える():
    """copies.py は箱へ単独で写される（lib が無い）: import せず \n だけで切り、U+2028 で行番号をずらさない。"""
    cp = load("core_copies", "plugins/core/scripts/copies.py")
    long = "照らす文は二十字を超えるように長く書いておく"
    got = [no for no, _ in cp.sentences(long + LS + long + "\n" + long + "\n")]
    assert got == [1, 2], got
