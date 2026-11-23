"""skill が核・細目の中身を写して意味をずらさず、正本（核・細目）を指しているかを見る。

言い回しは縛らない。見るのは形だけ:
- 記録の既定が各社の置き場（核 §8）を指し、PR 本文・返事の中を記録の置き場にしていないか
- 締めの 1 行・完了と根治の終わりが、正本の節を指しているか
各照らしは、直す前の古い形を作り物で入れて拒むこと（注入の試験）も一緒に見る。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "plugins"
VERIFY = P / "dev-flow" / "skills" / "verify" / "SKILL.md"
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


RECORD_KEYS = [(VERIFY, "learning_record")]


def test_記録の既定は各社の置き場を指す():
    for path, key in RECORD_KEYS:
        cell = default_of(read(path), key)
        assert record_default_ok(cell), "%s の %s の既定が各社の置き場を指していない: %s" % (path.parent.name, key, cell)


def test_記録の既定の照らしは古い形を拒む():
    assert record_default_ok("各社の決定の記録。PR 本文には書かない")   # 言い換えても通る
    for old in ["無し（返事の中に 1 行）", "PR 本文に原文と経緯を書く", "PR 本文の「学び:」の 1 行", "PR 本文に書く（核 §8）"]:
        assert not record_default_ok(old), "古い既定を通してしまう: %s" % old


def test_本文の記録の行き先も返事の中や_PR_本文にしない():
    for path, pat in [(VERIFY, r"learning_record` へ（無ければ([^）]*)）")]:
        m = re.search(pat, read(path))
        assert m, "%s に記録の行き先の文が無い" % path.parent.name
        assert "PR 本文" not in m.group(1) and "返事の中に 1 行" not in m.group(1), m.group(0)
        assert "核 §8" in m.group(1), "記録の行き先の文が核 §8 を指していない: " + m.group(0)


def test_文面の後の_1_行は返事の締めを置き換えない():
    text = read(COMPOSE)
    rule = next((ln for ln in text.splitlines() if ln.startswith("6. ")), "")
    assert "直したい所あれば言ってください" in rule and "核 §5" in rule, "compose-message の 6 が返事の締め（核 §5）との違いを指していない: " + rule


def test_verify_は完了と根治の終わりを核と細目の節で指す():
    text = read(VERIFY)
    desc = next(ln for ln in text.splitlines() if ln.startswith("description:"))
    assert "核 §7" in desc, "verify の description がコードの完了の正本（核 §7）を指していない"
    assert "細目 §7「根治の終わり」" in text, "verify が根治の終わり（原因の台帳）を指していない"

