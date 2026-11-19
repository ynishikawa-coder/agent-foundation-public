"""手で写す一覧を畳んだ形が戻らないか（並ぶ PR が同じ所を書き換えて衝突する・差分に付いて来ない写しの注入の試験）。

- PR 本文の「触る path」（差分の写し）と「残り」の行き先（台帳の写し）を手で書かせない。
- plugin の説明・一覧の表・skill の説明に見張りの数（「hook 6 つ」の類）を書かない（見張りを足す PR が全部そこを書き換える）。
"""
import json
import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# 見張りの数の書き方は字の並びを足して追わず、字を 1 つの形に寄せて（全角→半角・漢数字→数字・空白を詰める）から、
# 見張りを指す語と数＋助数詞が近くに在るかの類で見る（「hook が 6 つ」「六つの見張り」「守り ６ 本」も同じ類）。
WATCH = r"(?:hook|フック|見張り|守り|watcher)"
NUM = r"\d+(?:つ|個|本|種|件)"
COUNT = re.compile(WATCH + r"[^。\n]{0,10}?" + NUM + "|" + NUM + r"[^。\n]{0,4}?" + WATCH + r"|の" + NUM + "）", re.I)
_KANJI = {c: str(i) for i, c in enumerate("〇一二三四五六七八九")}
_KANJI.update({"十": "10"})


def flat(text):
    """数の照らしの前に字を 1 つの形へ寄せる。"""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[〇一二三四五六七八九十](?=[つ個本種件])", lambda m: _KANJI[m.group(0)], t)
    return re.sub(r"\s+", "", t)


# ── PR の型の欄は字で探さず、型（.github/pull_request_template.md）を欄の構造で読み、CONTRIBUTING の宣言と照らす ──
# 字は照らす前に 1 つの形へ寄せる（全角→半角・全角のコロン→半角・＝も欄の区切り・空白を詰める）。
FIELD = re.compile(r"^([^:=<`|#]+?)[:=]")


def norm(text):
    """欄の照らしの前の寄せ: NFKC（全角のコロン・＝・英数を半角へ）と空白を詰める。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def template():
    return (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")


def head_fields(text):
    """型の頭（最初の見出しの前）の欄の名の並び。欄の形（名＋区切り）でない行も、名を持たない行として数える。"""
    out = []
    for ln in text.split("\n## ", 1)[0].splitlines():
        if not ln.strip():
            continue
        m = FIELD.match(norm(ln))
        out.append(m.group(1) if m else norm(ln))
    return out


def declared_head(contrib):
    """CONTRIBUTING が宣言する冒頭の欄（「冒頭 N 行: a・b・c」）の (N, 名の並び)。"""
    m = re.search(r"冒頭(\d+)行:([^。]*?)。", norm(contrib))
    assert m, "CONTRIBUTING.md に PR の型の冒頭の欄の宣言（冒頭 N 行: …）が無い"
    return int(m.group(1)), m.group(2).split("・")


def head_problems(text, contrib):
    n, names = declared_head(contrib)
    got = head_fields(text)
    out = []
    if len(names) != n:
        out.append(f"CONTRIBUTING の冒頭の宣言の数（{n}）と名の数（{len(names)}）が合わない")
    if got != names:
        out.append(f"型の頭の欄 {got} が CONTRIBUTING の宣言 {names} と違う（差分の写し・手で書く欄を足さない）")
    return out


def section(text, word):
    """見出しに word を含む節の本文（次の見出しまで）。無ければ None。"""
    parts = re.split(r"^## ", text, flags=re.M)
    hit = [p for p in parts[1:] if word in p.split("\n", 1)[0]]
    return hit[0].split("\n", 1)[1] if len(hit) == 1 else None


def rest_problems(text):
    """「残り」の節が示す 1 行の形（コードの囲みで「- 」から始まる物）は、台帳の行の id の置き場 1 つだけを持つ。
    行き先・直す窓・題などを足した形（区切りの字・2 つ目の置き場・後ろに続く語）は、言い回しを問わず台帳の写しとして拒む。"""
    body = section(text, "残り（")
    if body is None:
        return ["「残り」の節が 1 つ無い"]
    forms = [c for c in re.findall(r"`([^`]+)`", body) if norm(c).startswith("-")]
    if not forms:
        return ["「残り」の節に 1 行の形（`- …`）が無い"]
    out = []
    for f in forms:
        # 決まった形は「- <名 1 語> <行の id の置き場>」だけ（置き場は 1 つで末尾・前に語は 1 つ）。外の形は全部拒む。
        if not re.fullmatch(r"-\s+[^\s<>]+\s+<[^<>]*id[^<>]*>", unicodedata.normalize("NFKC", f).strip()):
            out.append(f"「残り」の 1 行の形 `{f}` が台帳の行の id 1 つでない（行き先などを写させる）")
    return out


def test_PR_の型は触った_path_と残りの行き先を手で写させない():
    t = template()
    c = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert head_problems(t, c) == []
    assert rest_problems(t) == []


def review_path_problems(row):
    """レビューの点 2 の材料の欄は差分（git diff --name-only）から取り、本文の欄（`名:` の形）を材料にしない。"""
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    src = cells[1] if len(cells) > 1 else ""
    out = []
    if "gitdiff--name-only" not in norm(src):
        out.append("点 2 が差分（git diff --name-only）から path を取らない")
    if any(re.search(r"[:=]$", norm(c)) for c in re.findall(r"`([^`]+)`", src)):
        out.append("点 2 が PR 本文の欄（`名:`）を材料に読む")
    return out


def test_レビューは触った_path_を差分から取る():
    s = (ROOT / "plugins" / "checker" / "skills" / "review-pr" / "SKILL.md").read_text(encoding="utf-8")
    row = next(ln for ln in s.splitlines() if ln.startswith("| 2 "))
    assert review_path_problems(row) == []


def _descriptions():
    for p in sorted(ROOT.glob("plugins/*/.claude-plugin/plugin.json")):
        yield str(p.relative_to(ROOT)), json.loads(p.read_text(encoding="utf-8")).get("description", "")
    for p in sorted(ROOT.glob("plugins/*/skills/*/SKILL.md")):
        head = p.read_text(encoding="utf-8").split("\n---", 1)[0]
        yield str(p.relative_to(ROOT)), head
    yield "plugins/README.md", (ROOT / "plugins" / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("where,text", list(_descriptions()))
def test_説明と一覧に見張りの数を書かない(where, text):
    assert not COUNT.search(flat(text)), f"{where}: 見張りの数を書くと、足す PR が全部ここを書き換えて衝突する"


def test_数の注入は拾う():
    assert COUNT.search(flat("守りの hook 6 つ。")) and COUNT.search(flat("守りの hook（guard の 6 つ）"))
