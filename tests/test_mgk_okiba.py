"""根治の 5 段の照らしを、字の有無でなく置き場（細目 §3 の段の箇条・CONTRIBUTING の節・説明の行の欄）で照らす。

意図: 段の要・赤の時の直しの入口・説明の並びが、決まった段・節・欄に在る事を守り、言い回しは縛らない。
課題: 未来の段の要を照らさず（PR #149 のレビュー）、CONTRIBUTING の文を丸ごと写して全体から `in` で探し、
  説明の行の頭を写して startswith で照らしていたので、別の節・注記へ移しても緑、言い回しを直すと赤だった。
原因: 試験が構造を読む口（tests/md_yomi.py）を使わず、名も動く物（核の段・細目の子の名）から読まずに写していた。
"""
import json
import re

from md_yomi import 地の行, 箇条の子, 節
from test_mgk_5_dan import 核の段, 段の外れ, _3節
from test_mgk_hirogeru import DODAI, ENTRY, bp, 原因から入る直し

赤の入口の節 = ("2. レビュー", "5. 試験の置き方")


def 赤の入口の外れ(contributing: str) -> list[str]:
    """CONTRIBUTING の「レビュー」と「試験の置き方」の節の地の行に、細目「まず構造を疑う」を指す直しの文が在り、
    その文が意図とのずれから入る（意図が原因より先・ずれの語が在る）か。注記や囲いの中は数えない。"""
    bad = []
    for name in 赤の入口の節:
        body = 節(contributing, name)
        if body is None:
            bad.append(f"CONTRIBUTING に「{name}」の節が 1 つでない")
            continue
        lines = [l for l in 地の行(body) if ENTRY.search(l)]
        if not lines:
            bad.append(f"「{name}」の節に細目「まず構造を疑う」を指す直しの文が無い")
            continue
        for l in lines:
            if "ずれ" not in l or 原因から入る直し("直し: " + l):
                bad.append(f"「{name}」の直しの文が意図とのずれから入らない: {l.strip()[:60]}")
    return bad


_説明の行 = re.compile(r"^- ([^:：]+)[:：] ?(.*)$")


def 説明の順の外れ(text: str, dan: list[str], intent: str) -> list[str]:
    """全体の絵の説明の行の欄（`- 名（注）: 値`）が、核の段の頭 3 つ（意図・課題・原因）をこの順で持ち、
    意図の欄の値が起きた所の箱の意図か。欄の名の括弧の中（注）は照らさない。"""
    rows = [(m.group(1).split("（")[0].strip(), m.group(2)) for l in text.splitlines() if (m := _説明の行.match(l))]
    pos, bad = [], []
    for step in dan[:3]:
        n = next((k for k, (lab, _) in enumerate(rows) if lab.startswith(step)), None)
        if n is None:
            bad.append(f"説明に {step} の欄が無い")
        pos.append(n)
    if None not in pos and pos != sorted(pos):
        bad.append(f"説明の欄の順が核の段と違う: {[rows[n][0] for n in pos]}")
    if pos and pos[0] is not None and intent not in rows[pos[0]][1]:
        bad.append("意図の欄が起きた所の箱の意図を出さない")
    return bad


def _未来(s3):
    return dict(箇条の子(s3, "根治の 5 段"))["未来"].split("\n")[0]


def test_注入_未来の段の要を別の段へ移す_同じ原因の他の問題を指さないと赤_言い回しは緑():
    s3, k3 = _3節()
    assert 段の外れ(s3, k3) == []
    mirai = _未来(s3)
    kaiketsu = dict(箇条の子(s3, "根治の 5 段"))["解決"].split("\n")[0]
    # 「オーナーの手」を未来の段から解決の段へ移す（細目の全文には字が残る）
    moved = s3.replace(mirai, mirai.replace("オーナーの手", "人の手"), 1).replace(kaiketsu, kaiketsu + "オーナーの手。", 1)
    assert "オーナーの手" in moved and any("未来 の段に要が無い: オーナーの手" in x for x in 段の外れ(moved, k3))
    # 未来が同じ原因の他の問題の起きない姿を書かない
    gone = s3.replace(mirai, mirai.replace("と同じ原因の他の問題", ""), 1)
    assert any("同じ原因の他の問題" in x for x in 段の外れ(gone, k3))
    # 言い回しを変えても要と受け渡しが在れば緑
    reworded = s3.replace(mirai, mirai.replace("直した後の姿。", "直し終えた時の姿。").replace("書く。", "書き出す。"), 1)
    assert reworded != s3 and 段の外れ(reworded, k3) == []


def _c():
    from test_mgk_hirogeru import _read
    return _read("CONTRIBUTING.md")


def test_注入_赤の入口を別の節_注記へ移す_原因から入ると赤_言い回しは緑():
    c = _c()
    assert 赤の入口の外れ(c) == []
    line = next(l for l in 節(c, "5. 試験の置き方").splitlines() if ENTRY.search(l))
    # 「試験の置き方」の文を「置かない物」の節へ移す（全文には字が残る）
    moved = c.replace(line + "\n", "", 1).replace("## 4. 置かない物\n", "## 4. 置かない物\n\n" + line + "\n", 1)
    assert ENTRY.search(moved) and any("5. 試験の置き方" in x for x in 赤の入口の外れ(moved))
    # 注記の中へ
    hidden = c.replace(line, "<!-- " + line + " -->", 1)
    assert any("5. 試験の置き方" in x for x in 赤の入口の外れ(hidden))
    # 意図を落とし原因から入る
    cause = c.replace(line, "- 赤は細目 §3「まず構造を疑う」で原因から直す。", 1)
    assert any("意図とのずれから入らない" in x for x in 赤の入口の外れ(cause))
    # 言い回しを変えても形が在れば緑
    assert 赤の入口の外れ(c.replace("その試験が守る意図とのずれから入って", "その試験が守る意図とのずれを起点に", 1)) == []


def test_注入_説明の欄の順を入れ替えると赤_欄の注を変えても緑():
    pic = json.loads(DODAI.read_text(encoding="utf-8"))
    p = pic["problems"][0]
    text = bp.explain(pic, p["id"])
    dan = 核の段(_3節()[1])
    intent = {b["id"]: b for b in pic["boxes"]}[p["at"][0]].get("intent") or "まだ聞いていない"
    assert 説明の順の外れ(text, dan, intent) == []
    lines = text.splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith("- 意図"))
    k = next(n for n, l in enumerate(lines) if l.startswith("- 課題"))
    swapped = lines[:]
    swapped[i], swapped[k] = lines[k], lines[i]
    assert any("順" in x for x in 説明の順の外れ("\n".join(swapped), dan, intent))
    # 意図の欄から箱の意図を落とす
    assert any("意図の欄" in x for x in 説明の順の外れ(text.replace(intent, "別の文", 1), dan, intent))
    # 欄の名の注（括弧の中）を変えても緑
    renamed = text.replace("意図（起きた所の箱が何のために在るか）", "意図（箱の在る訳）", 1)
    assert renamed != text and 説明の順の外れ(renamed, dan, intent) == []
