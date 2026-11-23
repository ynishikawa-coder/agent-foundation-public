"""決まりの文書の値を、字の有無でなく置き場（細目 §4 の欄・guard-rules の見張りの表の行と升・値の表の節の囲い・
watch-log の頭の文・CONTRIBUTING の枝の節）から読む口と、その注入の試験。

意図: 道具と文書の値の照らし（test_doc_tool_values.py）が、決まりの置き場に在る値だけを読み、言い回しは縛らない事を守る。
課題: 読む口が文書の全体から最初に当たった字を拾っていたので、別の節・注記・コードの囲いの中の見本の値を先に置くと
  そちらを読み、道具と文書のずれを見落とした。注入の試験は表の 1 行・数・言い回しを写して replace していたので、
  表の形や数が変わると空振りして赤だった。
原因: 読む口が構造を読む口（tests/md_yomi.py）を使わず、注入の置き換えも読んだ値から作らず写していた。
"""
import json
import re

from md_yomi import 地の行, 欄, 節, 表の行, 見出し, _HEAD

HOOK_TABLE = "見張り"


# ── 読む口（置き場を決めてから中を読む）──────────────────────────────────────

def 節の頭(text: str, name: str) -> str | None:
    """見出し name の節の、最初の下の見出しより前の地の本文（見出しの無い頭の文・表）。節が 1 つでなければ None。"""
    body = 節(text, name)
    if body is None:
        return None
    out = []
    for line in body.splitlines():
        if _HEAD.match(line):
            break
        out.append(line)
    return "\n".join(out)


def 名の頭で節(text: str, head: str) -> str | None:
    """名が head で始まる見出しの節（その見出しが 1 つでなければ None）。"""
    names = [n for n in 見出し(text) if n.startswith(head)]
    return 節(text, names[0]) if len(names) == 1 else None


def 節の囲い(text: str, name: str, lang: str) -> str | None:
    """見出し name の節の中の、```lang の囲いの中身（1 つでなければ None）。節の範囲は地の行で決め、中身は元の行から取る。"""
    raw, ground = text.splitlines(), 地の行(text)
    hits = [n for n, l in enumerate(ground) if (m := _HEAD.match(l)) and m.group(2) == name]
    if len(hits) != 1:
        return None
    start, depth = hits[0], len(_HEAD.match(ground[hits[0]]).group(1))
    end = next((n for n in range(start + 1, len(ground)) if (m := _HEAD.match(ground[n])) and len(m.group(1)) <= depth),
               len(ground))
    blocks, cur = [], None
    for line in raw[start + 1:end]:
        s = line.strip()
        if cur is None and s.startswith("```"):
            cur = [] if s == "```" + lang else False
        elif cur is not None and s.startswith("```"):
            if cur is not False:
                blocks.append("\n".join(cur))
            cur = None
        elif cur not in (None, False):
            cur.append(line)
    return blocks[0] if len(blocks) == 1 else None


def 見張りの升(guard: str, watcher: str, col: str) -> str | None:
    """guard-rules の頭の見張りの表で、1 つ目の升の名（（ の前）が watcher の行の、頭の行の名が col の升。
    頭の節の外（値の表・射程の外）や注記・囲いの中の表は読まない。行が 1 つでない・升が無い時は None。"""
    lead = 節の頭(guard, (見出し(guard, 1) or [""])[0])
    if lead is None:
        return None
    head = next(([c.strip() for c in l.strip().strip("|").split("|")] for l in lead.splitlines()
                 if l.strip().startswith("|") and l.strip().strip("|").split("|")[0].strip() == HOOK_TABLE), None)
    if head is None or col not in head:
        return None
    rows = [r for r in 表の行(lead, HOOK_TABLE) if re.split(r"[（(]", r[0])[0].strip() == watcher]
    if len(rows) != 1 or len(rows[0]) <= head.index(col):
        return None
    return rows[0][head.index(col)]


def 分からないの語(saimoku: str) -> str | None:
    """細目 §4 の「選ぶ問いと開いた問い」の欄の「どの問いにも「X」の選択肢」の X。"""
    unit = 節(saimoku, "4. 聞き方")
    body = 欄(unit, "選ぶ問いと開いた問い") if unit is not None else None
    m = re.search(r"どの問いにも「(.+?)」の選択肢", body or "")
    return m.group(1) if m else None


def 分からないの形(guard: str) -> list[str] | None:
    """guard-rules の見張りの表の ask_shape の「する事」の升の、「分からない」の選択肢の見出しの頭の並び。"""
    m = re.search(r"「分からない」の選択肢（見出しの頭が(.+?)）に在る", 見張りの升(guard, "ask_shape", "する事") or "")
    return m.group(1).split("・") if m else None


def 推奨の語の並び(guard: str) -> set[str] | None:
    """guard-rules の見張りの表の ask_shape の「する事」の升の、推奨の語の並び（小文字）。"""
    m = re.search(r"推奨の語（([^。）]+)", 見張りの升(guard, "ask_shape", "する事") or "")
    return {w.lower() for w in m.group(1).split("・")} if m else None


def 書いた既定(guard: str) -> dict[str, int]:
    """見張りの表の「する事」の升に書いた「`鍵`…（既定 N）」の組（表の外・注記・囲いの中は読まない）。"""
    lead = 節の頭(guard, (見出し(guard, 1) or [""])[0]) or ""
    cells = [r[2] for r in 表の行(lead, HOOK_TABLE) if len(r) > 2]
    return {k: int(v) for c in cells for k, v in re.findall(r"`(\w+)`[^`（〔]{0,4}[（〔]既定 (\d+)[）〕]", c)}


def 値の表の数(guard: str) -> dict[str, int] | None:
    """「値の表」の節の ```json の囲いの "guard" の数の値（節の外の見本は読まない）。"""
    block = 節の囲い(guard, "値の表", "json")
    if block is None:
        return None
    g = json.loads(block)["guard"]
    return {k: v for k, v in g.items() if isinstance(v, int) and not isinstance(v, bool)}


def 止める回数(guard: str) -> int | None:
    """見張りの表の prior_ask の「する事」の升の「同じ頼みの中で N 回まで」の N。"""
    m = re.search(r"同じ頼みの中で (\d+) 回まで", 見張りの升(guard, "prior_ask", "する事") or "")
    return int(m.group(1)) if m else None


def Stopの札(watch: str) -> tuple[str, ...] | None:
    """watch-log の頭の文（最初の下の見出しの前）で「は、Stop の hook」を持つ 1 行の、その前の `札` の並び。"""
    lead = 節の頭(watch, (見出し(watch, 1) or [""])[0]) or ""
    lines = [l for l in lead.splitlines() if "は、Stop の hook" in l]
    if len(lines) != 1:
        return None
    return tuple(re.findall(r"`(\w+)`", lines[0].split("は、Stop の hook", 1)[0]))


BRANCH_RE = re.compile(r"枝の名は `(\w+)/<日付>-<話題>`。日付は `(Y+M+D+)`（例: `([^`]+)`）")


def 枝の決まり(contributing: str) -> tuple[str, int, str] | None:
    """CONTRIBUTING の「1. 枝と PR」の節の、枝の名の決まり（頭の名・日付の桁・例）。節の外・注記・囲いは読まない。"""
    body = 節(contributing, "1. 枝と PR")
    hits = BRANCH_RE.findall(body or "")
    if len(hits) != 1:
        return None
    prefix, date, example = hits[0]
    return prefix, len(date), example


# ── 注入の試験 ────────────────────────────────────────────────────────

from pathlib import Path  # noqa: E402

from saimoku import 全文 as 細目の全文  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GUARD = (ROOT / "plugins/guard/skills/guard-rules/SKILL.md").read_text(encoding="utf-8")
WATCH = (ROOT / "plugins/session-watch/skills/watch-log/SKILL.md").read_text(encoding="utf-8")
CONTRIB = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")


def _row_line(text: str, watcher: str) -> str:
    """見張りの表の watcher の行（元の行）。"""
    return next(l for l in text.splitlines() if l.startswith(f"| {watcher}（") or l.startswith(f"| {watcher} |"))


def _decoy_table(watcher: str, cell: str) -> str:
    return f"| {HOOK_TABLE} | 出来事 | する事 | 直し方 |\n|---|---|---|---|\n| {watcher}（見本） | PreToolUse | {cell} | 見本 |\n"


def _before_first_table(text: str, add: str) -> str:
    """見張りの表の頭の行の前に add を差す（同じ頭の節の中で先に読まれる位置）。"""
    head = next(l for l in text.splitlines() if l.startswith(f"| {HOOK_TABLE} |"))
    return text.replace(head, add + "\n" + head, 1)


def _in_other_section(text: str, add: str) -> str:
    """最後の ## の節の頭に add を差す（頭の節の外）。"""
    last = [l for l in text.splitlines() if l.startswith("## ")][-1]
    return text.replace(last, last + "\n\n" + add, 1)


def test_注入_分からないの語は細目_4_の欄だけから読む():
    t = 細目の全文()
    word = 分からないの語(t)
    assert word
    decoy = f"- **見本** — どの問いにも「作り物」の選択肢を置く。"
    # 別の節（§1）の先に古い値を書いても読まない
    first = next(l for l in t.splitlines() if l.startswith("## "))
    assert 分からないの語(t.replace(first, first + "\n\n" + decoy + "\n", 1)) == word
    # §4 の中でも別の欄の値は読まない
    assert 分からないの語(t.replace("## 4. 聞き方\n", "## 4. 聞き方\n\n" + decoy + "\n", 1)) == word
    # 本物を注記・囲いへ移し、注記に見本の値を置くと読めない
    body = 欄(節(t, "4. 聞き方"), "選ぶ問いと開いた問い")
    sentence = f"どの問いにも「{word}」の選択肢"
    gone = t.replace(sentence, "どの問いにも選択肢", 1) + f"\n<!-- {sentence} -->\n"
    assert sentence in gone and 分からないの語(gone) is None
    line = next(l for l in t.splitlines() if body.splitlines()[0] in l)
    assert 分からないの語(t.replace(line, "```\n" + line + "\n```", 1)) is None


def test_注入_分からないの形と推奨の語は見張りの表の_ask_shape_の升だけから読む():
    forms, recs = 分からないの形(GUARD), 推奨の語の並び(GUARD)
    assert forms and len(forms) >= 2 and recs and len(recs) >= 2
    # 頭の節の先・ほかの節に見本の表を置いても読まない
    cell = "「分からない」の選択肢（見出しの頭が作り物）に在る。推奨の語（作り物）"
    for bad in (_before_first_table(GUARD, "```\n" + _decoy_table("ask_shape", cell) + "```\n"),
                _before_first_table(GUARD, "<!--\n" + _decoy_table("ask_shape", cell) + "-->\n"),
                _in_other_section(GUARD, _decoy_table("ask_shape", cell))):
        assert 分からないの形(bad) == forms and 推奨の語の並び(bad) == recs
    # 本物の行を囲いへ入れ、字を注記に残すと読めない
    row = _row_line(GUARD, "ask_shape")
    hidden = GUARD.replace(row, "", 1) + "\n<!-- " + row + " -->\n"
    assert "見出しの頭が" in hidden and 分からないの形(hidden) is None and 推奨の語の並び(hidden) is None
    # 読んだ並びから 1 つ抜くと並びが変わる（写した字で replace しない）
    words = re.search(r"推奨の語（([^。）]+)", row).group(1).split("・")
    cut = GUARD.replace(row, row.replace("・".join(words), "・".join(words[:1] + words[2:]), 1), 1)
    assert 推奨の語の並び(cut) == recs - {words[1].lower()}
    f = 分からないの形(GUARD)
    cut = GUARD.replace(row, row.replace("・".join(f), "・".join(f[:-1]), 1), 1)
    assert 分からないの形(cut) == f[:-1]


def test_注入_既定の数は見張りの表と値の表の節の囲いだけから読む():
    said, nums = 書いた既定(GUARD), 値の表の数(GUARD)
    assert said and nums
    k, v = next(iter(said.items()))
    # 表の外の本文・注記・囲いに古い既定を書いても読まない
    note = f"例: `{k}`（既定 {v + 7}）"
    for bad in (_in_other_section(GUARD, note), GUARD + f"\n<!-- {note} -->\n", _before_first_table(GUARD, f"```\n{note}\n```")):
        assert 書いた既定(bad) == said
    # 表の升の既定を変えると読む値が変わる（読んだ鍵と値から置き換えを作る）
    row = next(l for l in GUARD.splitlines() if l.startswith("| ") and f"`{k}`" in l and "既定" in l)
    bumped = re.sub(rf"(`{k}`[^`（〔]{{0,4}}[（〔]既定 ){v}", lambda m: f"{m.group(1)}{v + 1}", row, count=1)
    assert bumped != row and 書いた既定(GUARD.replace(row, bumped, 1))[k] == v + 1
    # 値の表の節の外に見本の json を置いても読まない・節の囲いの数を変えると読む値が変わる
    nk, nv = next(iter(nums.items()))
    sample = '```json\n{"guard": {"%s": %d}}\n```' % (nk, nv + 9)
    assert 値の表の数(_before_first_table(GUARD, sample)) == nums
    assert 値の表の数(GUARD.replace(f'"{nk}": {nv}', f'"{nk}": {nv + 1}', 1))[nk] == nv + 1
    # 値の表の囲いが 2 つなら読めない
    assert 値の表の数(GUARD.replace("## 値の表\n", "## 値の表\n\n" + sample + "\n", 1)) is None


def test_注入_止める回数は見張りの表の_prior_ask_の行だけから読む():
    n = 止める回数(GUARD)
    assert n is not None
    cell = f"同じ頼みの中で {n + 3} 回まで"
    for bad in (_before_first_table(GUARD, "```\n" + _decoy_table("prior_ask", cell) + "```\n"),
                _in_other_section(GUARD, _decoy_table("prior_ask", cell))):
        assert 止める回数(bad) == n
    row = _row_line(GUARD, "prior_ask")
    assert 止める回数(GUARD.replace(row, "```\n" + row + "\n```", 1)) is None
    moved = re.sub(r"(同じ頼みの中で )\d+", lambda m: f"{m.group(1)}{n + 1}", row, count=1)
    assert 止める回数(GUARD.replace(row, moved, 1)) == n + 1


def test_注入_Stop_の札は_watch_log_の頭の文だけから読む():
    codes = Stopの札(WATCH)
    assert codes and len(codes) >= 2
    line = next(l for l in WATCH.splitlines() if "は、Stop の hook" in l)
    decoy = "`made` は、Stop の hook（見本）"
    assert Stopの札(_in_other_section(WATCH, decoy)) == codes
    assert Stopの札(WATCH + f"\n<!-- {decoy} -->\n") == codes
    # 頭の文に 2 行あれば決められない・本物を囲いへ入れると読めない
    heading = next(l for l in WATCH.splitlines() if l.startswith("# "))
    assert Stopの札(WATCH.replace(heading, heading + "\n\n" + decoy, 1)) is None
    assert Stopの札(WATCH.replace(line, "```\n" + line + "\n```", 1)) is None
    # 読んだ札から 1 つ抜くと並びが変わる
    cut = WATCH.replace(f"・`{codes[-1]}` は、Stop", " は、Stop", 1)
    assert Stopの札(cut) == codes[:-1]


def test_注入_枝の名の決まりは_CONTRIBUTING_の枝の節だけから読む():
    rule = 枝の決まり(CONTRIB)
    assert rule
    prefix, digits, example = rule
    line = next(l for l in CONTRIB.splitlines() if BRANCH_RE.search(l))
    old = line.replace(f"`{prefix}/", "`old/", 1)
    # 先の節（頭）・別の節・注記に古い決まりを書いても読まない
    head = next(l for l in CONTRIB.splitlines() if l.startswith("# "))
    for bad in (CONTRIB.replace(head, head + "\n\n" + old, 1), _in_other_section(CONTRIB, old), CONTRIB + f"\n<!-- {old} -->\n"):
        assert 枝の決まり(bad) == rule
    # 節の中に 2 つ・本物を囲いへ入れると読めない
    assert 枝の決まり(CONTRIB.replace(line, line + "\n" + old, 1)) is None
    assert 枝の決まり(CONTRIB.replace(line, "```\n" + line + "\n```", 1)) is None
    # 読んだ日付の桁を変えると読む値も変わる
    date = BRANCH_RE.search(line).group(2)
    shorter = line.replace(f"`{date}`", f"`{date[2:]}`", 1)
    assert 枝の決まり(CONTRIB.replace(line, shorter, 1))[1] == digits - 2
