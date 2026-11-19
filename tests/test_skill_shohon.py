"""skill が核・細目の中身を写して意味をずらさず、正本（核・細目）を指しているかを見る。

言い回しは縛らない。見るのは形だけ（字は照らす前に NFKC・空白を詰めて寄せ、照らす要素は正本から直に読む）:
- 記録の既定が各社の置き場（核 §8・正本が名指す置き場）だけを指す形か（他の所を置き場にさせる文は形の外）
- 完了の印・締めの 1 行・規律の分け方・誤りが入れない形が、正本の節を指しているか（写しの並びが残っていないか）
各照らしは、直す前の古い形を作り物で入れて拒むこと（注入の試験）も一緒に見る。
"""
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "plugins"
VERIFY = P / "dev-flow" / "skills" / "verify" / "SKILL.md"
REGISTER = P / "dev-flow" / "skills" / "register-rule" / "SKILL.md"
TITLE = P / "session-watch" / "skills" / "title-mark" / "SKILL.md"
COMPOSE = P / "docs-kit" / "skills" / "compose-message" / "SKILL.md"
KAKU = P / "core" / "核.md"
SAIMOKU = P / "core" / "細目.md"


def read(p):
    return p.read_text(encoding="utf-8")


def default_of(text, key):
    """値の表（| 鍵 | 使う所 | 無い時の既定 |）の、鍵の行の既定の欄。行が無ければ止まる。"""
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] == "`%s`" % key:
            return "|".join(cells[2:])
    raise AssertionError("値の表に鍵 %s の行が無い" % key)


def nf(text):
    return unicodedata.normalize("NFKC", text)


def flat(text):
    """照らす前の寄せ: NFKC（全角→半角）と空白を詰める。"""
    return re.sub(r"\s+", "", nf(text))


def canon_records():
    """正本（plugins/core の文書）が「各社の X に／へ／と／は」で名指す記録の置き場の名（原因の台帳・決定の記録 など）。
    置き場の名は字で並べず、正本の文から直に読む。"""
    names = set()
    for p in sorted((P / "core").glob("*.md")):
        names.update(re.findall(r"各社の([^、。()「」:=]+?)(?:に|へ|と|は)", flat(read(p))))
    return names


def _sentences(text):
    """括弧の中（注）を外し、。で切った文の並び。"""
    t = re.sub(r"\([^()]*\)", "", nf(text))
    return [s for s in (flat(x) for x in t.split("。")) if s]


def record_dest_ok(text):
    """記録の行き先の文が、形として各社の置き場を指すか（言い回しの字で「PR 本文」等を探さない）:
    - 頭の文（＝の左）は「各社の … <正本が名指す置き場>(の行)(短い結び)」の形だけ（他の置き場を並べる余地が無い）。
    - 後に続く文は打ち消し（…ない）か、聞くで終わる物だけ（別の置き場へ書かせる文は形の外＝拒む）。"""
    ss = _sentences(text)
    if not ss:
        return False
    head = ss[0].split("=", 1)[0]
    recs = "|".join(re.escape(r) for r in sorted(canon_records(), key=len, reverse=True))
    if not recs or not re.fullmatch(r"各社の[^にへ]*?(?:%s)(?:の行)?.{0,4}" % recs, head):
        return False
    return all(re.search(r"(?:ない|聞く)$", s) for s in ss[1:])


def record_default_ok(cell):
    """記録の既定が各社の置き場を指し、ほかの所（PR 本文・返事の中など、名は問わない）を置き場にしていないか。
    （核 §8 は本文の行き先の文が指す。値の表の既定に核・細目を挙げない＝tests/test_skill_values_no_rule_copy.py）"""
    return record_dest_ok(cell)


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


# ── 写しを字の並び（表の頭・形の名）で探さず、正本の要素を正本から直に読み、同じ所に n 個以上在るかを寄せた字で見る ──
def _tokens(text):
    """意味を運ぶ字（漢字 1 字ずつ・2 字以上のカタカナ）の集合。言い換え（送り仮名・助詞・語順）に揺れない。"""
    return set(re.findall(r"[\u4e00-\u9fff]|[\u30a1-\u30ffー]{2,}", nf(text)))


def _present(element, place):
    """正本の要素の字の半分以上が、その所に在るか。"""
    e = _tokens(element)
    return bool(e) and len(e & _tokens(place)) * 2 >= len(e)


def _section(text, num):
    return re.search(r"^## %d\..*?(?=^## |\Z)" % num, text, flags=re.S | re.M).group(0)


def wrong_form_canon():
    """細目 §3 の「誤りが入れない形」の (見出しの名, 要素の名の並び)。正本の箇条の太字から読む。"""
    lines = _section(read(SAIMOKU), 3).splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.startswith("- **") and "形" in ln and lines[k + 1].startswith("  - **"))
    title = re.match(r"- \*\*(.+?)\*\*", lines[i]).group(1)
    names = []
    for ln in lines[i + 1:]:
        if not ln.startswith(" "):
            break
        m = re.match(r"\s+- \*\*(.+?)\*\*", ln)
        if m:
            names.append(m.group(1))
    return title, names


def decider_canon():
    """核 §3 の最後の項（誰が決めるかの分け方）の要素＝「、」で分けた句（AI が入れる物／オーナーの同意が要る物）。"""
    last = [ln for ln in _section(read(KAKU), 3).splitlines() if ln.startswith("- ")][-1]
    return [h for h in last[2:].split("、") if h.strip()]


def places(text):
    """同じ所の単位: 表 1 つ・箇条 1 つ（続く字下げの行を含む）・段落 1 つ。"""
    out, cur = [], []
    for ln in text.splitlines():
        table = ln.startswith("|")
        if cur and (not ln.strip() or re.match(r"(?:- |\d+\. |#)", ln)
                    or table != cur[-1].startswith("|")):
            out.append("\n".join(cur))
            cur = []
        if ln.strip():
            cur.append(ln)
    if cur:
        out.append("\n".join(cur))
    return out


def copies(text):
    """register-rule の Step 1（規律の分け方と根治の形を決める所）で、正本の要素を 2 つ以上並べた所（写し）の並び。"""
    title, names = wrong_form_canon()
    halves = decider_canon()
    out = []
    for pl in places(text):
        if sum(_present(n, pl.replace(title, "")) for n in names) >= 2:
            out.append("誤りが入れない形の写し: " + pl[:60])
        if pl.startswith("|") and sum(_present(h, pl) for h in halves) >= 2:
            out.append("核 §3 の分け方の写しの表: " + pl[:60])
    return out


def test_register_rule_は核と細目の写しを持たず指す():
    text = read(REGISTER)
    step1 = text[text.index("## Step 1"):text.index("## Step 2")]
    assert "核§3" in flat(step1)
    title, names = wrong_form_canon()
    assert len(names) == 4 and len(decider_canon()) == 2, "正本の要素が読めない（照らす相手が空のまま緑にしない）"
    form = next(ln for ln in step1.splitlines() if title in ln and "どれか" in ln)
    assert "細目§3「%s」" % title in flat(form), "誤りが入れない形が正本を指していない"
    assert copies(step1) == [], "正本の要素を並べた写し（表・箇条）が在る"


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
