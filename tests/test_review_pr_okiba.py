"""チェック役の skill（review-pr）の決まりを、字の有無でなく置き場（見る点の表の行・手順の段・判定の形の見本の囲い）で照らす。

意図: 触った path を差分から取る事・判定の形の道具を呼ぶ事・red の根治の入口の行が、決まった表・段・見本に在る事を守り、
  言い回しは縛らない。
課題: 試験が「| 2 」で始まる行をどの表からでも拾い、`verdict_form.py` と根治の入口の行を SKILL の全体から `in` で探して
  いたので、別の表や注記・本文へ移しても緑だった。
原因: 試験が構造を読む口（tests/md_yomi.py）を使わず、名（点の名・道具の file の名・入口の行）も動く物から読まずに写していた。
"""
import re
from pathlib import Path

from md_yomi import 地の行, 見出し, 節, 表の行
from test_checker import PLUGIN, vf

SKILL = PLUGIN / "skills" / "review-pr" / "SKILL.md"
_HEAD = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_STEP = re.compile(r"^\d+\.\s+\*\*(.+?)\*\*")


def _skill():
    return SKILL.read_text(encoding="utf-8")


def 囲いの中(text: str, name: str) -> str | None:
    """名が name の見出しの節の中の、コードの囲い（```）の中の行（注記の中は除く）。見出しが 1 つでない時は None。
    md_yomi は囲いの中を構造に数えないので、見本（囲いの中の形）を読む口はここに置く。"""
    raw = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S).splitlines()
    ground = 地の行(text)
    heads = [n for n, l in enumerate(ground) if (m := _HEAD.match(l)) and m.group(2) == name]
    if len(heads) != 1:
        return None
    depth = len(_HEAD.match(ground[heads[0]]).group(1))
    out, fence = [], False
    for n in range(heads[0] + 1, len(raw)):
        m = _HEAD.match(ground[n])
        if m and len(m.group(1)) <= depth:
            break
        if raw[n].lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            out.append(raw[n])
    return "\n".join(out)


def 触った_path_の外れ(skill: str, points: dict) -> list[str]:
    """「見る点」の節の表（頭の升が「点」）の、触った path の点の行が `git diff --name-only` で取り、本文の手書きを読まないか。
    点の番号と名は道具が読む表（vf.load_points）から取る。"""
    no, name = next((n, x) for n, x in points.items() if "path" in x)
    body = 節(skill, "見る点")
    if body is None:
        return ["「見る点」の節が 1 つでない"]
    row = next((r for r in 表の行(body, "点") if r and r[0] == f"{no} {name}"), None)
    if row is None:
        return [f"見る点の表に「{no} {name}」の行が無い"]
    line = " | ".join(row)
    return ([] if "git diff --name-only" in line else ["触った path の行が差分から取らない"]) + \
        (["触った path の行が本文の手書きを読む"] if "触る path:" in line else [])


def 形の道具の外れ(skill: str, tool: str) -> list[str]:
    """「手順」の節の、判定を出す段（番号つきの段で太字の名に「判定」を持つ）が判定の形の道具を呼ぶか。"""
    body = 節(skill, "手順")
    if body is None:
        return ["「手順」の節が 1 つでない"]
    steps = [l for l in 地の行(body) if (m := _STEP.match(l)) and "判定" in m.group(1)]
    if not steps:
        return ["手順に判定を出す段が無い"]
    return [] if any(tool in l for l in steps) else [f"判定を出す段が {tool} を呼ばない"]


def 見本の入口の外れ(skill: str, root_cause: str) -> list[str]:
    """「判定の形」の節の見本（囲いの中）の verdict の節に、根治の入口の行（道具が照らす行の頭）が在るか。"""
    heads = [h for h in 見出し(skill, 2) if h.startswith("判定の形")]
    if len(heads) != 1:
        return ["「判定の形」の節が 1 つでない"]
    sample = 囲いの中(skill, heads[0])
    verdict = 節(sample or "", "verdict")
    if verdict is None:
        return ["判定の形の見本に verdict の節が 1 つでない"]
    return [] if any(l.startswith(root_cause) for l in verdict.splitlines()) else ["見本の verdict に根治の入口の行が無い"]


def test_注入_触った_path_を別の表の行へ移すと赤_言い回しは緑():
    s, pts = _skill(), vf.load_points()
    assert 触った_path_の外れ(s, pts) == []
    row = next(l for l in s.splitlines() if l.startswith("| 2 "))
    # 見る点の行から差分の取り方を消し、言語ごとの点の表に「| 2 」の行で置く（全体には字が残る）
    head = next(h for h in 見出し(s, 2) if h.startswith("言語ごとの点"))
    table = next(l for l in 節(s, head).splitlines() if l.startswith("|") and not set(l) <= set("|-: "))
    moved = s.replace(row, row.replace("git diff --name-only", "差分"), 1).replace(
        table, table + "\n| 2 触った path | `git diff --name-only` | x |", 1)
    assert moved.count("| 2 ") >= 2 and "git diff --name-only" in moved
    assert any("差分から取らない" in x for x in 触った_path_の外れ(moved, pts))
    # 本文の手書きを読む形へ戻す
    assert any("手書き" in x for x in 触った_path_の外れ(s.replace(row, row + " 触る path: を読む", 1), pts))
    # 点の名が道具の表と違えば行が無い（表の名を写していない）
    assert any("行が無い" in x for x in 触った_path_の外れ(s, {**pts, 2: "触る path"}))
    # 言い回しを変えても名と取り方が在れば緑
    assert 触った_path_の外れ(s.replace("本文の手書きは見ない", "本文の手書きは読まない", 1), pts) == []


def test_注入_形の道具を判定の段から外し注記_別の節へ移すと赤_言い回しは緑():
    s, tool = _skill(), Path(vf.__file__).name
    assert 形の道具の外れ(s, tool) == []
    step = next(l for l in 節(s, "手順").splitlines() if (m := _STEP.match(l)) and "判定" in m.group(1))
    bare = step.replace(tool, "形の道具")
    # 判定の段から消し、注記に残す（全体には字が残る・立ち位置の節にも在る）
    hidden = s.replace(step, bare + f" <!-- {tool} -->", 1)
    assert tool in hidden and any(tool in x for x in 形の道具の外れ(hidden, tool))
    # 別の段（返す）へ移す
    moved = s.replace(step, bare, 1).replace("5. **返す**:", f"5. **返す**: {tool} を回して", 1)
    assert any(tool in x for x in 形の道具の外れ(moved, tool))
    # 言い回しを変えても段の中に在れば緑
    assert 形の道具の外れ(s.replace(step, step.replace("出す前に", "出すより先に"), 1), tool) == []


def test_注入_根治の入口を見本から本文へ移すと赤_言い回しは緑():
    s, rc = _skill(), vf.ROOT_CAUSE
    assert 見本の入口の外れ(s, rc) == []
    head = next(h for h in 見出し(s, 2) if h.startswith("判定の形"))
    line = next(l for l in 囲いの中(s, head).splitlines() if l.startswith(rc))
    # 見本から消し、囲いの後の本文に 1 回だけ書く（全体には字が残る）
    moved = s.replace(line + "\n", "", 1).replace("## 確認した範囲 / 確認していない範囲\n- 見た diff・回した物差し / 見ていない所\n```\n",
                                               "## 確認した範囲 / 確認していない範囲\n- 見た diff・回した物差し / 見ていない所\n```\n\n" + line + "\n", 1)
    assert rc in moved and 見本の入口の外れ(moved, rc) == ["見本の verdict に根治の入口の行が無い"]
    # 見本の別の節（点）へ移す
    other = s.replace(line + "\n", "", 1).replace("## 点\n- 1 依頼の充足", "## 点\n" + line + "\n- 1 依頼の充足", 1)
    assert 見本の入口の外れ(other, rc) == ["見本の verdict に根治の入口の行が無い"]
    # 行の頭の後ろの言い回しを変えても緑
    assert 見本の入口の外れ(s.replace(line, rc + "で原因を探す", 1), rc) == []
