"""skill が核・細目の中身を写して意味をずらさず、正本（核・細目）を指しているかを見る。

言い回しは縛らない。見るのは形だけ:
- 記録の既定が各社の置き場（核 §8）を指し、PR 本文・返事の中を記録の置き場にしていないか
- 完了の印・締めの 1 行・規律の分け方・誤りが入れない形が、決めた置き場（表の行・節・欄）で正本の節を指しているか（写しの並びが残っていないか）
各照らしは、直す前の古い形を作り物で入れて拒むこと（注入の試験）も一緒に見る。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "plugins"
VERIFY = P / "dev-flow" / "skills" / "verify" / "SKILL.md"
REGISTER = P / "dev-flow" / "skills" / "register-rule" / "SKILL.md"
TITLE = P / "session-watch" / "skills" / "title-mark" / "SKILL.md"
COMPOSE = P / "docs-kit" / "skills" / "compose-message" / "SKILL.md"


def read(p):
    return p.read_text(encoding="utf-8")


def default_of(text, key):
    """値の表（| 鍵 | 使う所 | 無い時の既定 |）の、鍵の行の既定の欄。行が無ければ止まる。"""
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] == "`%s`" % key:
            return "|".join(cells[2:])
    raise AssertionError("値の表に鍵 %s の行が無い" % key)


def record_default_ok(cell):
    """記録の既定が各社の置き場を指し、PR 本文・返事の中を置き場にしていないか。
    （核 §8 は本文の行き先の文が指す。値の表の既定に核・細目を挙げない＝tests/test_skill_values_no_rule_copy.py）"""
    if "各社" not in cell:
        return False
    # 「PR 本文で代わりにしない」のような打ち消しの句は置き場にしていない（言い回しは問わず、句に打ち消しが在るかで見る）。
    placed = re.sub(r"[^。、（）]*PR 本文[^。、（）]*?(せず|しない|書かない|見える)[^。、（）]*", "", cell)
    return "PR 本文" not in placed and "返事の中" not in placed


RECORD_KEYS = [(VERIFY, "learning_record"), (REGISTER, "decision_record"), (REGISTER, "learning_record")]


def test_記録の既定は各社の置き場を指す():
    for path, key in RECORD_KEYS:
        cell = default_of(read(path), key)
        assert record_default_ok(cell), "%s の %s の既定が各社の置き場を指していない: %s" % (path.parent.name, key, cell)


def test_記録の既定の照らしは古い形を拒む():
    assert record_default_ok("各社の決定の記録。PR 本文には書かない")   # 言い換えても通る
    for old in ["無し（返事の中に 1 行）", "PR 本文に原文と経緯を書く", "PR 本文の「学び:」の 1 行", "PR 本文に書く（核 §8）"]:
        assert not record_default_ok(old), "古い既定を通してしまう: %s" % old


def test_本文の記録の行き先も返事の中や_PR_本文にしない():
    for path, pat in [(VERIFY, r"learning_record` へ（無ければ([^）]*)）"), (REGISTER, r"decision_record`（無ければ([^）]*)）"), (REGISTER, r"learning_record` へ（無ければ([^）]*)）")]:
        m = re.search(pat, read(path))
        assert m, "%s に記録の行き先の文が無い" % path.parent.name
        assert "PR 本文" not in m.group(1) and "返事の中に 1 行" not in m.group(1), m.group(0)
        assert "核 §8" in m.group(1), "記録の行き先の文が核 §8 を指していない: " + m.group(0)


from test_skill_shohon_okiba import (S03, S07, 完了の印の外れ, 完了の指しの外れ,  # noqa: E402
                                    形の指しの外れ, 締めの項の外れ)

# 下の 4 つは置き場（表の行・節・欄）で照らす（照らしと注入の試験は tests/test_skill_shohon_okiba.py）。


def test_題の完了の印は終わったに結ぶ():
    assert 完了の印の外れ(read(TITLE)) == []


def test_文面の後の_1_行は返事の締めを置き換えない():
    assert 締めの項の外れ(read(COMPOSE)) == []


def test_register_rule_は核と細目の写しを持たず指す():
    assert 形の指しの外れ(read(REGISTER), read(S03)) == []


def test_verify_は完了と根治の終わりを核と細目の節で指す():
    assert 完了の指しの外れ(read(VERIFY), read(S07)) == []


# ── 点検の道具（session_watch.py）も ✅＝終わった に結ぶ（title-mark と同じ正本・核 §7）──
def _sw():
    import copy
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("session_watch_shohon", P / "session-watch" / "scripts" / "session_watch.py")
    sw = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(sw)
    base = sw.read_rows(ROOT / "tests" / "session_watch" / "child_ok.jsonl")

    def make(title, text):
        rs = copy.deepcopy(base)
        for r in rs:
            for b in (r.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b["input"].get("title") == "🤖✅ 作り物の作業":
                    b["input"]["title"] = title
        rs[-1]["message"]["content"] = [{"type": "text", "text": text}]
        return [m for c, m in sw.check(sw.Log(rs)) if c == "title"]
    return make


CLOSE = "\nAI がこの後やること: なし\nあなたがやること: なし。この窓は閉じて大丈夫です。"


def test_点検は止まった窓に完了の印を求めない():
    make = _sw()
    assert make("🤖 作り物の作業", "🛑止まった\n権限が無い。外せる人はオーナー。" + CLOSE) == []
    assert make("🤖✅ 作り物の作業", "✅ 終わった\n作り物を終えた。" + CLOSE) == []


def test_点検は終わった以外の札に付いた完了の印を拾う():
    make = _sw()
    assert make("🤖✅ 作り物の作業", "🛑止まった\n権限が無い。外せる人はオーナー。" + CLOSE)
    assert make("🤖✅ 作り物の作業", "✅終わった（一部）\n残りは直す窓へ。" + CLOSE)
    assert make("🤖 作り物の作業", "✅ 終わった\n作り物を終えた。" + CLOSE)


def test_点検は終わったの本文に一部の字があっても終わったと読む():
    make = _sw()
    assert make("🤖✅ 作り物の作業", "✅ 終わった 一部の file だけ触る直しを入れた\n作り物を終えた。" + CLOSE) == []
