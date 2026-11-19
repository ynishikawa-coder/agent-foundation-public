"""skill が核・細目の中身を写して意味をずらさず、正本（核・細目）を指しているかを見る。

言い回しは縛らない。見るのは形だけ:
- 記録の既定が各社の置き場（核 §8）を指し、PR 本文・返事の中を記録の置き場にしていないか
- 完了の印・締めの 1 行・規律の分け方・誤りが入れない形が、正本の節を指しているか（写しの並びが残っていないか）
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


def done_mark_ok(row):
    """題の ✅ が「終わった」（核 §7）に結ばれ、締めの 1 行（AI の手が尽きた）に結ばれていないか。"""
    return "核 §7" in row and "終わった" in row and "AI がこの後やること: なし" not in row


def test_題の完了の印は終わったに結ぶ():
    rows = [ln for ln in read(TITLE).splitlines() if ln.startswith("| `✅` |")]
    assert len(rows) == 1, "title-mark の状態の表に ✅ の行が 1 つ無い"
    assert done_mark_ok(rows[0]), rows[0]
    assert not done_mark_ok("| `✅` | `🤖` の窓が `AI がこの後やること: なし` で締めるターン | また起こされた時 |")


def test_文面の後の_1_行は返事の締めを置き換えない():
    text = read(COMPOSE)
    rule = next((ln for ln in text.splitlines() if ln.startswith("6. ")), "")
    assert "直したい所あれば言ってください" in rule and "核 §5" in rule, "compose-message の 6 が返事の締め（核 §5）との違いを指していない: " + rule


def test_register_rule_は核と細目の写しを持たず指す():
    text = read(REGISTER)
    step1 = text[text.index("## Step 1"):text.index("## Step 2")]
    assert "| 足す物 | 誰が決める |" not in step1, "核 §3 の分け方を表で写している"
    assert "核 §3" in step1
    form = next(ln for ln in step1.splitlines() if "誤りが入れない形のどれか" in ln)
    assert "細目 §3「誤りが入れない形」" in form, "誤りが入れない形が正本を指していない"
    # 4 つの形の名を並べた写しが無い（2 つ以上の名が同じ行に並べば写し）。
    names = ["写す工程を無くす", "誤った物が入れない", "正しい道だけが", "名指しで人の関所へ"]
    assert sum(n in form for n in names) < 2, "誤りが入れない形の 4 つを写している: " + form


def test_verify_は完了と根治の終わりを核と細目の節で指す():
    text = read(VERIFY)
    desc = next(ln for ln in text.splitlines() if ln.startswith("description:"))
    assert "核 §7" in desc, "verify の description がコードの完了の正本（核 §7）を指していない"
    assert "細目 §7「根治の終わり」" in text, "verify が根治の終わり（原因の台帳）を指していない"


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
