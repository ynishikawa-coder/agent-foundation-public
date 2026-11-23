"""決まりの文を写して照らしていた試験（test_core_copies・test_rule_pins・test_checker_eye_and_cards・test_rule_holes の
並走の文）を、置き場（核 §1 の箇条・細目「量の上限」の節・review-pr の説明・振る舞いの「並走」の欄）と動く物の名で照らす。

意図: 決まりが決めた置き場に在る事と、名（道具の file・定数・関数）が動く物と揃う事を守り、言い回しは縛らない。
課題: 試験が決まりの文を丸ごと写し、file の全体から `in` で探していたので、別の節や注記・コードの囲いへ移しても緑、
  言い回しを少し直すと赤だった（文を変えるたびに試験の写しも直す）。
原因: 試験が構造を読む口（tests/md_yomi.py）を使わず、文と名を写していた。
"""
import pathlib
import re

from md_yomi import 地の行, 欄, 節
from saimoku import kaku

ROOT = pathlib.Path(__file__).resolve().parents[1]
KAKU = "plugins/core/核.md"
FURUMAI = "plugins/core/振る舞い.md"
RYOU = "plugins/core/細目/09-量の上限.md"
KIKIKATA = "plugins/core/細目/04-聞き方.md"
REVIEW_SKILL = "plugins/checker/skills/review-pr/SKILL.md"
_NUM = re.compile(r"^\d+\.\s+(.*)$")


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _最初の文(s: str) -> str:
    return re.match(r"[^。]*。|[^。]+$", s).group(0)


# ── 核 §1 の「戻せない操作の前に人に聞く」（copies.py の試験の元の文）──
def 戻せない操作の文(kaku_text: str) -> str | None:
    """核の「1. 安全」の節の番号の箇条のうち、強制 push を挙げる 1 つの最初の文（無い・2 つ在る時は None）。"""
    body = 節(kaku_text, "1. 安全")
    if body is None:
        return None
    hits = [m.group(1) for l in body.splitlines() if (m := _NUM.match(l.strip())) and "強制 push" in m.group(1)]
    return _最初の文(hits[0]) if len(hits) == 1 and "戻せない操作" in hits[0] else None


# ── 細目「量の上限」の節（名は kaku.py から読む）──
def 量の上限の名():
    for name in ("check", "LIMITS"):
        assert hasattr(kaku, name), name   # 動く物に名が無い＝文書が古い
    return {"道具": pathlib.Path(kaku.__file__).name, "関数": "check", "定数": "LIMITS"}


def 量の上限の外れ(text: str, names: dict) -> list[str]:
    """「量の上限」の節が、道具と関数と定数の名・使う側の根の CLAUDE.md・越えた時の移し先を持つか。"""
    body = 節(text, "量の上限")
    if body is None:
        return ["「量の上限」の節が 1 つでない"]
    need = [f"`{names['道具']}`", f"`{names['関数']}`", f"`{names['定数']}`", "根の `CLAUDE.md`", "細目へ", "その repo の文書へ"]
    return [f"「量の上限」の節に無い: {w}" for w in need if w not in body]


# ── review-pr の説明（書いた窓が立てた助手は別の目にならない）──
古い別の目 = "書いた窓と別の目を立てる時は読むだけの助手"


def 説明の外れ(skill: str) -> list[str]:
    """SKILL の頭（--- の間）の description に、書いた窓が立てた助手は別の目にならない事が在り、古い言い方が地の文に無いか。"""
    parts = skill.split("---")
    head = parts[1] if skill.startswith("---") and len(parts) >= 3 else ""
    desc = [l for l in 地の行(head) if l.startswith("description:")]
    out = [] if len(desc) == 1 else ["説明（description）の行が 1 つでない"]
    d = desc[0] if len(desc) == 1 else ""
    out += [f"説明に無い: {w}" for w in ("書いた窓が立てた助手", "別の目にならない") if w not in d]
    if any(古い別の目 in l for l in 地の行(skill)):
        out.append(f"古い言い方が在る: {古い別の目}")
    return out


# ── 振る舞いの「並走」の欄の最初の文（test_rule_holes が消して照らす文）──
def 並走の文(text: str) -> str | None:
    """振る舞いの「並走」の欄の行の、欄の名から最初の「。」までの文（文の並びの切り方と同じ）。欄が 1 つでない時は None。"""
    if 欄(text, "並走") is None:
        return None
    line = next(l for l in 地の行(text) if re.match(r"^- \*\*並走\*\*", l))
    return _最初の文(line)


# ── 細目 §4「手の窓」の欄（題の種類と済んだ印は session_watch.py の HAND・DONE から読む）──
def 手の窓の外れ(text: str, hand: str, done: str) -> list[str]:
    """細目 §4 の「手の窓」の欄が、題 `<手の種類> <何を>` と済んだ印 `<手の種類><済んだ>` を持ち、
    file に古い作業名の印「手: <何を>」が無いか（欄の外・注記・囲いの中の字は数えない）。"""
    body = 欄(text, "手の窓")
    if body is None:
        return ["「手の窓」の欄が 1 つでない"]
    out = [f"「手の窓」の欄に無い: {w}" for w in (f"`{hand} <何を>`", f"`{hand}{done}`") if w not in body]
    return out + (["古い作業名の印が在る: 手: <何を>"] if "手: <何を>" in text else [])


def test_置き場と名が揃う():
    assert 戻せない操作の文(_read(KAKU))
    assert 量の上限の外れ(_read(RYOU), 量の上限の名()) == []
    assert 説明の外れ(_read(REVIEW_SKILL)) == []
    assert 並走の文(_read(FURUMAI)).startswith("- **並走**")
    assert 手の窓の外れ(_read(KIKIKATA), "✋", "✅") == []


def test_注入_戻せない操作の箇条を別の節_注記へ移すと読めない_言い回しを変えても読める():
    t = _read(KAKU)
    s = 戻せない操作の文(t)
    line = next(l for l in t.splitlines() if s in l)
    moved = t.replace(line + "\n", "", 1).replace("## 8. 記録\n", "## 8. 記録\n\n" + line + "\n", 1)
    assert s in moved and 戻せない操作の文(moved) is None
    assert 戻せない操作の文(t.replace(line, f"<!-- {line} -->", 1)) is None
    reworded = t.replace(line, line.replace("戻せない操作の前に人に聞く", "戻せない操作の前には人に確かめる", 1), 1)
    assert 戻せない操作の文(reworded).startswith("戻せない操作の前には人に確かめる")


def test_注入_量の上限を注記へ移すと赤_名を変えると赤_言い回しを変えても緑():
    t, n = _read(RYOU), 量の上限の名()
    body = 節(t, "量の上限")
    para = next(l for l in body.splitlines() if "`LIMITS`" in l)
    for wrap in (lambda s: f"<!-- {s} -->", lambda s: f"```\n{s}\n```"):
        assert len(量の上限の外れ(t.replace(para, wrap(para), 1), n)) >= 5
    assert any("OTHER" in x for x in 量の上限の外れ(t, {**n, "定数": "OTHER"}))   # 定数の名が変わったら文書が古い
    assert 量の上限の外れ(t.replace("越えたら", "上限を越えた時は", 1), n) == []


def test_注入_説明の語を本文へ移すと赤_古い言い方を足すと赤_言い回しを変えても緑():
    t = _read(REVIEW_SKILL)
    moved = t.replace("書いた窓が立てた助手は別の目にならない", "", 1) + "\n- 書いた窓が立てた助手は別の目にならない。\n"
    assert 説明の外れ(moved)
    assert 説明の外れ(t + "\n- " + 古い別の目 + "。\n") == [f"古い言い方が在る: {古い別の目}"]
    assert 説明の外れ(t + "\n<!-- " + 古い別の目 + " -->\n") == []
    assert 説明の外れ(t.replace("書いた窓が立てた助手は別の目にならない", "書いた窓が立てた助手は、別の目にならない", 1)) == []


def test_注入_並走の欄を注記へ移すと読めない_言い回しを変えると文も変わる():
    t = _read(FURUMAI)
    line = next(l for l in t.splitlines() if l.startswith("- **並走**"))
    assert 並走の文(t.replace(line, f"<!-- {line} -->", 1)) is None
    assert 並走の文(t.replace(line, line.replace("着手と言われたら", "着手を言われたら", 1), 1)).startswith("- **並走** — 着手を言われたら")


def test_注入_手の窓の題を別の欄_注記へ移すと赤_言い回しを変えても緑():
    t = _read(KIKIKATA)
    line = next(l for l in t.splitlines() if l.startswith("- **手の窓**"))
    want = ["「手の窓」の欄に無い: `✋ <何を>`", "「手の窓」の欄に無い: `✋✅`"]
    gone = line.replace("題 `✋ <何を>` の窓を立てて頼む（済んだら `✋✅`）", "窓を立てて頼む", 1)
    moved = t.replace(line, gone, 1) + "\n- **別の欄** — 題 `✋ <何を>` の窓を立てる（済んだら `✋✅`）。\n"
    assert 手の窓の外れ(moved, "✋", "✅") == want
    assert 手の窓の外れ(t.replace(line, f"<!-- {line} -->", 1), "✋", "✅") == ["「手の窓」の欄が 1 つでない"]
    assert 手の窓の外れ(t + "\n- 古い形は 手: <何を>\n", "✋", "✅") == ["古い作業名の印が在る: 手: <何を>"]
    assert 手の窓の外れ(t, "🖐", "✅")   # 動く物の種類の印が変わったら文書が古い
    assert 手の窓の外れ(t.replace("の窓を立てて頼む（済んだら", "の窓を立ててお願いする（済めば", 1), "✋", "✅") == []
