"""skill が核・細目の正本を指す照らし（tests/test_skill_shohon.py の title-mark・compose-message・register-rule・verify）を、
文の写しや file の全体の字でなく、置き場（表の行・節・欄）と、指す先の正本に在る名（核の見出し・細目の欄・箇条の子）で照らす。

意図: skill が決めた置き場で正本（核・細目）の名を指し、指す名が正本に実在する事を守り、言い回しは縛らない。
課題: 試験が「| `✅` |」の字で表の行を探し、compose-message・register-rule・verify の文を写して file の全体から照らしていたので、
  表の形・言い回しを変えると赤、別の節や注記へ移しても緑だった。誤りが入れない形の 4 つの名も試験に写していた。
原因: 試験が構造を読む口（tests/md_yomi.py）を使わず、指す先の名も正本から読まずに写していた。
"""
import re
from pathlib import Path

from md_yomi import 地の行, 欄, 箇条の子, 節, 表の行, 見出し

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "plugins"
VERIFY = P / "dev-flow" / "skills" / "verify" / "SKILL.md"
REGISTER = P / "dev-flow" / "skills" / "register-rule" / "SKILL.md"
TITLE = P / "session-watch" / "skills" / "title-mark" / "SKILL.md"
COMPOSE = P / "docs-kit" / "skills" / "compose-message" / "SKILL.md"
KAKU = P / "core" / "核.md"
S03 = P / "core" / "細目" / "03-直すは根治.md"
S07 = P / "core" / "細目" / "07-完了の4状態.md"

状態の節 = "状態（2 文字目）と付けてよい種類"
共通の節 = "共通の決まり（全文面に当てる）"
STEP1 = "Step 1: これは止める物か（最初に問う）"
終わる前の節 = "2. 終わる前（Completion Report）"
_NUM = re.compile(r"^\d+\.\s+(.*)$")


def read(p):
    return p.read_text(encoding="utf-8")


def 核の節(n: int) -> str:
    """核の 2 段の見出しのうち番号 n の名（正本から読む）。"""
    hits = [h for h in 見出し(read(KAKU), 2) if h.startswith(f"{n}. ")]
    assert len(hits) == 1, hits
    return hits[0]


# ── title-mark: 状態の表の ✅ の行 ──
def 完了の印の外れ(text: str) -> list[str]:
    body = 節(text, 状態の節)
    if body is None:
        return [f"「{状態の節}」の節が 1 つでない"]
    rows = [r for r in 表の行(body, "状態") if r[0] == "`✅`"]
    if len(rows) != 1:
        return ["状態の表に ✅ の行が 1 つでない"]
    row = "|".join(rows[0])
    out = [] if "核 §7" in row and "終わった" in row else ["✅ の行が終わった（核 §7）に結ばれていない"]
    return out + (["✅ の行が締めの 1 行に結ばれている"] if "AI がこの後やること: なし" in row else [])


# ── compose-message: 共通の決まりの、返事の締め（核 §5）を置き換えない項 ──
def 締めの項の外れ(text: str) -> list[str]:
    body = 節(text, 共通の節)
    if body is None:
        return [f"「{共通の節}」の節が 1 つでない"]
    items = [m.group(1) for l in body.splitlines() if (m := _NUM.match(l.strip())) and "核 §5" in m.group(1)]
    if len(items) != 1:
        return ["核 §5 を指す項が 1 つでない"]
    return [f"核 §5 を指す項に無い: {w}" for w in ("1 行", "置き換えない") if w not in items[0]]


# ── register-rule: Step 1 は核 §3 を指し、誤りが入れない形は細目 §3 の欄を指して 4 つを写さない ──
def 形の指しの外れ(text: str, s03: str) -> list[str]:
    step1 = 節(text, STEP1)
    if step1 is None:
        return [f"「{STEP1}」の節が 1 つでない"]
    out = [] if "核 §3" in step1 else ["Step 1 が核 §3 を指していない"]
    if 表の行(step1, "足す物"):
        out.append("Step 1 が核 §3 の分け方を表で写している")
    form = 欄(step1, "誤りが入れない形のどれか")
    if form is None:
        return out + ["Step 1 に「誤りが入れない形のどれか」の欄が 1 つでない"]
    if "細目 §3「誤りが入れない形」" not in form:
        out.append("誤りが入れない形の欄が細目 §3 を指していない")
    names = [n for n, _ in (箇条の子(s03, "誤りが入れない形") or [])]
    if 欄(s03, "誤りが入れない形") is None or len(names) != 4:
        out.append("細目 §3 に「誤りが入れない形」の欄と 4 つの子が無い（指す先が無い）")
    if sum(n in form for n in names) >= 2:
        out.append("誤りが入れない形の 4 つを写している")
    return out


# ── verify: 説明は核 §7、終わる前の節は細目 §7「根治の終わり」を指す ──
def _説明(text: str) -> str:
    parts = text.split("---")
    head = parts[1] if text.startswith("---") and len(parts) >= 3 else ""
    d = [l for l in 地の行(head) if l.startswith("description:")]
    return d[0] if len(d) == 1 else ""


def 完了の指しの外れ(text: str, s07: str) -> list[str]:
    out = [] if "核 §7" in _説明(text) else ["説明（description）が核 §7 を指していない"]
    body = 節(text, 終わる前の節)
    if body is None:
        return out + [f"「{終わる前の節}」の節が 1 つでない"]
    if "細目 §7「根治の終わり」" not in body:
        out.append("終わる前の節が細目 §7「根治の終わり」を指していない")
    if 欄(s07, "根治の終わり") is None:
        out.append("細目 §7 に「根治の終わり」の欄が無い（指す先が無い）")
    return out


def test_今は揃う():
    assert 核の節(5).startswith("5. ") and 核の節(7).startswith("7. ") and 核の節(3).startswith("3. ")
    assert 完了の印の外れ(read(TITLE)) == []
    assert 締めの項の外れ(read(COMPOSE)) == []
    assert 形の指しの外れ(read(REGISTER), read(S03)) == []
    assert 完了の指しの外れ(read(VERIFY), read(S07)) == []


def test_注入_完了の印_表を別の節_注記へ移すと赤_言い回しを変えても緑():
    t = read(TITLE)
    row = next(l for l in t.splitlines() if l.startswith("| `✅` |"))
    assert 完了の印の外れ(t.replace(row, f"<!-- {row} -->", 1)) == ["状態の表に ✅ の行が 1 つでない"]
    moved = t.replace(row + "\n", "", 1) + "\n## 別\n\n| 状態 | 意味 | 付けてよい種類 |\n|---|---|---|\n" + row + "\n"
    assert 完了の印の外れ(moved) == ["状態の表に ✅ の行が 1 つでない"]
    old = "| `✅` | `🤖` の窓が `AI がこの後やること: なし` で締めるターン | また起こされた時 |"
    assert 完了の印の外れ(t.replace(row, old, 1))
    assert 完了の印の外れ(t.replace(row, row.replace("後継へ渡した", "後の窓へ渡した"), 1)) == []
    assert 完了の印の外れ(t.replace(row, "|  `✅`  | 終わった（核 §7） | `🤖` |", 1)) == []   # 升の空きの違いは縛らない


def test_注入_締めの項_別の節_注記へ移すと赤_言い回しを変えても緑():
    t = read(COMPOSE)
    line = next(l for l in t.splitlines() if l.startswith("6. ") and "核 §5" in l)
    assert 締めの項の外れ(t.replace(line, f"<!-- {line} -->", 1)) == ["核 §5 を指す項が 1 つでない"]
    moved = t.replace(line + "\n", "", 1).replace("## 困った時\n", "## 困った時\n\n" + line + "\n", 1)
    assert "核 §5" in moved and 締めの項の外れ(moved) == ["核 §5 を指す項が 1 つでない"]
    assert 締めの項の外れ(t.replace(line, line.replace("置き換えない", "置き換えず", 1), 1)) == ["核 §5 を指す項に無い: 置き換えない"]
    assert 締めの項の外れ(t.replace(line, line.replace("直したい所あれば言ってください", "直す所があれば教えてください", 1), 1)) == []


def test_注入_形の指し_4_つを写すと赤_欄を注記へ移すと赤_正本の欄が無いと赤():
    t, s = read(REGISTER), read(S03)
    form = next(l for l in t.splitlines() if l.startswith("- **誤りが入れない形のどれか**"))
    names = [n for n, _ in 箇条の子(s, "誤りが入れない形")]
    copied = t.replace(form, form + "（" + "・".join(names) + "）", 1)
    assert "誤りが入れない形の 4 つを写している" in 形の指しの外れ(copied, s)
    assert 形の指しの外れ(t.replace(form, f"<!-- {form} -->", 1), s) == ["Step 1 に「誤りが入れない形のどれか」の欄が 1 つでない"]
    assert 形の指しの外れ(t, s.replace("**誤りが入れない形**", "**入れない形**", 1))
    table = "\n| 足す物 | 誰が決める |\n|---|---|\n| 止める物 | オーナー |\n"
    assert 形の指しの外れ(t.replace("## Step 2", table + "\n## Step 2", 1), s) == ["Step 1 が核 §3 の分け方を表で写している"]
    assert 形の指しの外れ(t.replace(form, form.replace("文を足すだけで", "文を足すのみで", 1), 1), s) == []


def test_注入_完了の指し_別の節へ移すと赤_正本の欄が無いと赤():
    t, s = read(VERIFY), read(S07)
    moved = t.replace("（細目 §7「根治の終わり」）", "", 1).replace("## 範囲（クラウドが主）\n", "## 範囲（クラウドが主）\n\n細目 §7「根治の終わり」\n", 1)
    assert "細目 §7「根治の終わり」" in moved
    assert 完了の指しの外れ(moved, s) == ["終わる前の節が細目 §7「根治の終わり」を指していない"]
    assert 完了の指しの外れ(t, s.replace("**根治の終わり**", "**終わり**", 1)) == ["細目 §7 に「根治の終わり」の欄が無い（指す先が無い）"]
    desc = _説明(t)
    assert 完了の指しの外れ(t.replace(desc, desc.replace("核 §7", "核"), 1), s) == ["説明（description）が核 §7 を指していない"]
