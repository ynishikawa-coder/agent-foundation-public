"""やり直しの無駄を消す決まり（tests/test_no_redo.py）を、字の有無でなく置き場（核の節・振る舞いと細目の欄・
CONTRIBUTING の「2. レビュー」の節・review-pr の欄）の中の要の語で照らす。

意図: 決まりが決めた節・欄に在る事を守り、言い回しは縛らない。
課題: 試験が決まりの文を丸ごと写して file の全体から `in` で探していたので、別の節や注記・コードの囲いへ移しても緑、
  言い回しを少し直すと赤だった。レビューの窓の決まりも CONTRIBUTING と review-pr の全体から字を探していた。
原因: 試験が構造を読む口（tests/md_yomi.py）を使わず、文を写していた。
"""
import pathlib

import pytest

from md_yomi import 欄, 節

ROOT = pathlib.Path(__file__).resolve().parents[1]
KAKU, FURUMAI = "plugins/core/核.md", "plugins/core/振る舞い.md"
S03, S04, S05 = "plugins/core/細目/03-直すは根治.md", "plugins/core/細目/04-聞き方.md", "plugins/core/細目/05-返事の形.md"
S07, S08 = "plugins/core/細目/07-完了の4状態.md", "plugins/core/細目/08-記録.md"
REVIEW_SKILL = "plugins/checker/skills/review-pr/SKILL.md"

# (file, 置き場の種類, 置き場の名, 要の語)。1 行が決まりの 1 文（消すとその文の要の語が置き場から消える）。
決まり = [
    (KAKU, "節", "5. 返事の形", ["最後の 2 行", "`AI がこの後やること:`", "`あなたがやること:`"]),
    (KAKU, "節", "5. 返事の形", ["🤖 の窓", "閉じる"]),
    (KAKU, "節", "7. 完了の 4 状態", ["別の目", "合流の前に 1 回", "見直しも同じ目"]),
    (FURUMAI, "欄", "後継へ渡す残り", ["1 本の列にせず", "持ち主"]),
    (FURUMAI, "欄", "同じ原因の他の問題", ["削らず選ばず全部", "原因の台帳"]),
    (FURUMAI, "欄", "同じ原因の他の問題", ["行ごとでなく", "束ごと"]),
    (S03, "欄", "原因の台帳", ["行ごとに立てない", "まとまりごとに 1 つ", "同じ `直す窓`"]),
    (S03, "欄", "原因の台帳", ["合流したら", "`直した`", "立てた窓へ返す"]),
    (S04, "欄", "大きい仕事の並べ方", ["1 窓 1 枝 1 PR に入らなかった仕事", "互いに関係しないまとまりごと", "`直す窓`"]),
    (S04, "欄", "大きい仕事の並べ方", ["Sonnet", "Opus"]),
    (S04, "欄", "環境", ["話題が変われば新しい窓"]),
    (S07, "欄", "土台の直しの終わり", ["この窓から触れない repo", "repo ごとに 1 つの直す窓"]),
    (S07, "欄", "main へ入れる", ["書いた窓と別の窓のレビュー", "合流の前に 1 回", "同じレビューの窓の見直し"]),
    (S07, "欄", "判定を頼む", ["1 つだけレビューの窓", "合流まで運ぶ"]),
    (S07, "欄", "判定を頼む", ["新しいレビューの窓を立てず", "同じレビューの窓へ `send_message`"]),
    (S05, "欄", "締めの 2 行", ["最後だけ読んで", "自分の番"]),
    (S05, "欄", "締めの 2 行", ["`あなたがやること: なし`", "手を打つ窓の URL"]),
    (S08, "欄", "文脈が重い時", ["後継の窓へ移らず", "自動の要約"]),
]

# レビューの窓の決まり: CONTRIBUTING は「2. レビュー」の節、review-pr は「1 つの PR に 1 つのレビューの窓」の欄に置く。
レビューの置き場 = [
    ("CONTRIBUTING.md", "節", "2. レビュー"),
    (REVIEW_SKILL, "欄", "1 つの PR に 1 つのレビューの窓"),
]
レビューの語 = ["合流の前に 1 回", "新しいレビューの窓を立て", "同じレビューの窓", "`send_message`"]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def 置き場の外れ(text: str, kind: str, name: str, words: list[str]) -> list[str]:
    """text の節（kind="節"）か欄（kind="欄"）の name の中に words が全部在るか。置き場が無い・2 つ在る時も外れ
    （注記や囲いの中の物は数えない）。"""
    body = (節 if kind == "節" else 欄)(text, name)
    if body is None:
        return [f"「{name}」の{kind}が 1 つでない"]
    return [f"「{name}」の{kind}に無い: {w}" for w in words if w not in body]


def 決まりの外れ(read=_read) -> list[str]:
    """やり直しの無駄を消す決まりが、決めた置き場（核・振る舞い・細目の節と欄、CONTRIBUTING、review-pr）に要の語で在るか
    （file ごとの外れを並べる）。"""
    out = []
    for rel, kind, name, words in 決まり:
        out += [f"{rel}: {x}" for x in 置き場の外れ(read(rel), kind, name, words)]
    for rel, kind, name in レビューの置き場:
        out += [f"{rel}: {x}" for x in 置き場の外れ(read(rel), kind, name, レビューの語)]
    return out


def test_やり直しの無駄を消す決まりは置き場に在る():
    assert 決まりの外れ() == []


@pytest.mark.parametrize("rel, kind, name, words", 決まり)
def test_注入_決まりの語を注記へ_囲いへ移すと赤_言い回しを変えても緑(rel, kind, name, words):
    """核・振る舞い・細目の置き場の要の語を、注記・コードの囲いへ移すと赤、ほかを言い換えても緑。"""
    t = _read(rel)
    body = (節 if kind == "節" else 欄)(t, name)
    w = words[-1]
    line = next(l for l in body.splitlines() if w in l)
    for wrap in (lambda s: f"<!-- {s} -->", lambda s: f"\n```\n{s}\n```\n"):
        hidden = t.replace(line, wrap(line), 1)
        assert w in hidden and 置き場の外れ(hidden, kind, name, words), (rel, name, w)
    # 要の語のほかを言い換えても緑（語の前に 1 字足す）
    reworded = t.replace(line, line.replace(w, "（言い換え）" + w, 1), 1)
    assert 置き場の外れ(reworded, kind, name, words) == []


def test_注入_決まりの語を別の欄へ移すと赤():
    t = _read(S07)
    moved = t.replace("新しいレビューの窓を立てず、", "", 1).replace("- **main へ入れる** —", "- **main へ入れる** — 新しいレビューの窓を立てず、", 1)
    assert "新しいレビューの窓を立てず" in moved
    assert 置き場の外れ(moved, "欄", "判定を頼む", ["新しいレビューの窓を立てず"]) == ["「判定を頼む」の欄に無い: 新しいレビューの窓を立てず"]


def test_注入_レビューの窓の決まりを別の節へ移すと赤():
    c = _read("CONTRIBUTING.md")
    body = 節(c, "2. レビュー")
    line = next(l for l in body.splitlines() if "新しいレビューの窓を立て" in l)
    moved = c.replace(line, "", 1).replace("## 4. 置かない物\n", "## 4. 置かない物\n" + line + "\n", 1)
    assert "新しいレビューの窓を立て" in moved
    assert 置き場の外れ(moved, "節", "2. レビュー", レビューの語)


def test_注入_置き場の名を変えると赤():
    t = _read(S08).replace("**文脈が重い時**", "**文脈の時**", 1)
    assert 置き場の外れ(t, "欄", "文脈が重い時", ["自動の要約"]) == ["「文脈が重い時」の欄が 1 つでない"]
