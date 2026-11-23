"""dev-flow の skill の決まりを、字の有無でなく置き場（節・番号の段・太字の欄・表の行・出力の形の囲い）で照らす。

意図: 決まりが決めた段・欄・表に在り、段の番号は雛形の見出し（動く物）と揃う事を守り、言い回しは縛らない。
課題: 試験が文を skill の全体から `in` で探し（整地の別の目・行き先・verify の記録・論点の窓）、Step 1 は字の切り出しで
  順も欄も見ず注記も数え、ほんまにできる表はどの表の 1 列目でも通ったので、別の段・注記・囲いへ移しても緑だった。
原因: 試験が構造を読む口（tests/md_yomi.py）を使わず、段の番号も雛形から読まずに写していた。
"""
from __future__ import annotations

import re
from pathlib import Path

from md_yomi import 地の行, 太字の欄, 欄, 節, 表の行, 見出し

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins" / "dev-flow" / "skills"
_STEP = re.compile(r"^(\d+)\.[ \t]+\*\*(.+?)\*\*(.*)$")
_HEAD = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")


def _read(rel: str) -> str:
    return (SKILLS / rel).read_text(encoding="utf-8")


def 番号の段(body: str | None) -> list[tuple[str, str]]:
    """`1. **名**…` の番号の段を (名と見出しの行の残り, 段の行と下の行) の順で返す（注記・囲いの中は数えない）。"""
    out: list[list[str]] = []
    for line in (body or "").splitlines():
        m = _STEP.match(line)
        if m:
            out.append([m.group(2) + m.group(3), line])
        elif out and (line.startswith((" ", "\t")) or not line.strip()):
            out[-1][1] += "\n" + line
        elif out and line.strip():
            out.append(["", ""])  # 段の外の行で切る（次の段まで本文に混ぜない）
    return [(a, b) for a, b in out if a]


def 囲いの中(text: str, head_prefix: str) -> list[str]:
    """名が head_prefix で始まる見出しの節（地の行で数える）の中の、コードの囲いの中の生の行。"""
    ground, raw = 地の行(text), text.splitlines()
    hits = [(n, len(m.group(1))) for n, l in enumerate(ground) if (m := _HEAD.match(l)) and m.group(2).startswith(head_prefix)]
    if len(hits) != 1:
        return []
    start, depth = hits[0]
    end = next((n for n in range(start + 1, len(ground))
                if (m := _HEAD.match(ground[n])) and len(m.group(1)) <= depth), len(ground))
    out, fence = [], False
    for line in raw[start + 1:end]:
        if line.lstrip().startswith("```"):
            fence = not fence
        elif fence:
            out.append(line)
    return out


# --- 整地（preimpl-cleanup）: 段の番号は雛形の見出しの番号から読む -----------------------------------------

def 雛形の番号(tpl: str, word: str) -> int | None:
    """雛形の `## N. …` の見出しのうち、名に word を含む物の N（無い・2 つ在る時は None）。"""
    hits = [int(m.group(1)) for h in 見出し(tpl, 2) if (m := re.match(r"(\d+)\.\s", h)) and word in h]
    return hits[0] if len(hits) == 1 else None


def 手順の段(skill: str, n: int | None) -> str | None:
    """skill の「手順」の節の、見出しの行に `（n 欄）` を持つ番号の段の本文（見出しの行も含む）。1 つでない時は None。"""
    if n is None:
        return None
    hits = [body for name, body in 番号の段(節(skill, "手順")) if f"（{n} 欄）" in name]
    return hits[0] if len(hits) == 1 else None


def 原因の段の外れ(skill: str, tpl: str) -> list[str]:
    """原因の段（雛形の「原因」の番号の欄）が、同じ原因の他の問題を読むだけの助手に、自分の読みを渡さずに探させるか。"""
    step = 手順の段(skill, 雛形の番号(tpl, "原因"))
    if step is None:
        return ["手順に原因の欄の段が 1 つでない"]
    return [f"原因の段に無い: {w}" for w in ["読むだけの助手", "自分の読みや直し方は渡さない"] if w not in step]


def 行き先の外れ(skill: str, tpl: str) -> list[str]:
    """解決の段が原因の全部に行き先を付けて原因の台帳と合わせ、雛形の解決の節に「行き先」の欄が在るか。"""
    n = 雛形の番号(tpl, "解決")
    head = next((h for h in 見出し(tpl, 2) if n is not None and h.startswith(f"{n}. ")), None)
    out = []
    if head is None or 欄(節(tpl, head) or "", "行き先") is None:
        out.append("雛形の解決の節に「行き先」の欄が 1 つでない")
    step = 手順の段(skill, n)
    if step is None:
        return out + ["手順に解決の欄の段が 1 つでない"]
    return out + [f"解決の段に無い: {w}" for w in ["全部に行き先", "原因の台帳"] if w not in step]


def 未来の段の外れ(skill: str, tpl: str) -> list[str]:
    """未来の段か雛形の未来の節が、試験の名を並べる欄でないと言うか。"""
    n = 雛形の番号(tpl, "未来")
    step = 手順の段(skill, n) or ""
    head = next((h for h in 見出し(tpl, 2) if n is not None and h.startswith(f"{n}. ")), None)
    sec = 節(tpl, head) if head else ""
    return [] if "試験の名を並べる欄ではない" in step + (sec or "") else ["未来の段に、試験の名を並べる欄でないと無い"]


# --- 規律を足す（register-rule）: Step 1 の欄の順と、出力の形の Step 1 の行 ----------------------------------

STEP1_欄 = ["意図", "誤りが入れない形のどれか", "注入の試験"]


def step1の外れ(skill: str) -> list[str]:
    heads = [h for h in 見出し(skill, 2) if h.startswith("Step 1")]
    if len(heads) != 1:
        return ["Step 1 の見出しが 1 つでない"]
    body = 節(skill, heads[0]) or ""
    out = []
    names = [n for n, _ in 太字の欄(body) if n in STEP1_欄]
    if names != STEP1_欄:
        out.append(f"Step 1 の欄が {STEP1_欄} の順で 1 つずつでない: {names}")
    if not any("核 §3・細目 §3" in l for l in body.splitlines()):
        out.append("Step 1 に中身の正本（核 §3・細目 §3）を指す行が無い")
    fence = 囲いの中(skill, "出力の形")
    first = next((i for i, l in enumerate(fence) if l.startswith("Step 1")), None)
    second = next((i for i, l in enumerate(fence) if l.startswith("Step 2")), None)
    if first is None or second is None or second < first:
        return out + ["出力の形の囲いに Step 1 と Step 2 の行が順に無い"]
    if "止める物か" not in fence[first]:
        out.append("出力の形の Step 1 の行に「止める物か」が無い")
    if not any("注入の試験" in l for l in fence[first:second]):
        out.append("出力の形の Step 1 と Step 2 の間に注入の試験が無い")
    return out


# --- verify: 終わる前の段と報告の雛形 ----------------------------------------------------------------------

VERIFY_節 = "2. 終わる前（Completion Report）"


def verify_の外れ(skill: str) -> list[str]:
    """終わる前の段に「申告でなく記録」で見る番号の段が 1 つ在り、報告の雛形の確かめの表に「記録の所在」の列が在るか。"""
    body = 節(skill, VERIFY_節)
    if body is None:
        return [f"verify に「{VERIFY_節}」の節が 1 つでない"]
    out = []
    if len([n for n, _ in 番号の段(body) if "申告でなく記録" in n]) != 1:
        out.append("終わる前の段に、申告でなく記録で見る段が 1 つでない")
    rows = [l for l in 囲いの中(skill, VERIFY_節[:6]) if l.startswith("## Verification Results")]
    if len(rows) != 1 or "記録の所在" not in rows[0]:
        out.append("報告の雛形の Verification Results に「記録の所在」の列が無い")
    return out


# --- 設計モード（design-mode）: ほんまにできる表と論点の窓 ------------------------------------------------

def ほんまにできる表の外れ(text: str) -> list[str]:
    """「出る」の節の、ほんまにできる表の段の下の表（頭が「項目」）の 1 列目に、届く先と写しの残りが在るか。"""
    body = 節(text, "出る")
    if body is None:
        return ["design-mode に「出る」の節が 1 つでない"]
    lines = body.splitlines()
    at = [i for i, l in enumerate(lines) if "**ほんまにできる表**" in l]
    if len(at) != 1:
        return ["「出る」にほんまにできる表の段が 1 つでない"]
    rows = {r[0] for r in 表の行("\n".join(lines[at[0]:]), "項目")}
    return [f"ほんまにできる表に行が無い: {w}" for w in ["届く先", "写しの残り"] if w not in rows]


def 論点の窓の外れ(text: str) -> list[str]:
    """「中でする事」の節の 1 つの行が、未決を 1 本の列にせず論点ごとに窓を並べると言うか。"""
    body = 節(text, "中でする事")
    if body is None:
        return ["design-mode に「中でする事」の節が 1 つでない"]
    ok = any("1 本の列にしない" in l and "論点ごとに窓を並べて同時に進める" in l for l in body.splitlines())
    return [] if ok else ["「中でする事」に、論点ごとに窓を並べ 1 本の列にしない行が無い"]


# --- 注入の試験 ---------------------------------------------------------------------------------------------

def _seichi():
    return _read("preimpl-cleanup/SKILL.md"), _read("preimpl-cleanup/整地受領証.template.md")


def test_注入_整地の段を別の段_注記へ移すと赤_段の番号は雛形から読む():
    skill, tpl = _seichi()
    assert 原因の段の外れ(skill, tpl) == [] and 行き先の外れ(skill, tpl) == [] and 未来の段の外れ(skill, tpl) == []
    # 読むだけの助手を原因の段から抜き、大原則の節へ移す（全文に字は残る）
    moved = skill.replace("読むだけの助手", "助手", 1).replace("## 大原則（なぜ要るか）\n", "## 大原則（なぜ要るか）\n\n読むだけの助手\n", 1)
    assert "読むだけの助手" in moved and any("読むだけの助手" in x for x in 原因の段の外れ(moved, tpl))
    # 原因の台帳を解決の段から注記へ
    step4 = 手順の段(skill, 雛形の番号(tpl, "解決"))
    hidden = skill.replace(step4, step4.replace("原因の台帳", "台帳") + "\n<!-- 原因の台帳 -->", 1)
    assert any("原因の台帳" in x for x in 行き先の外れ(hidden, tpl))
    # 雛形の「行き先」の欄を囲いへ入れると欄が無い
    fenced = tpl.replace("**行き先**", "```\n**行き先**", 1).replace("\n## 5.", "\n```\n## 5.", 1)
    assert "**行き先**" in fenced and "雛形の解決の節に「行き先」の欄が 1 つでない" in 行き先の外れ(skill, fenced)
    # 雛形の欄の番号が動いたら（原因が 4 番）skill の段が古いので赤
    renum = tpl.replace("## 3. 原因", "## 4. 原因", 1).replace("## 4. 解決", "## 3. 解決", 1)
    assert 原因の段の外れ(skill, renum) != []
    # 言い回しを変えても段に要の語が在れば緑
    assert 原因の段の外れ(skill.replace("その 1 文だけを", "1 文だけを", 1), tpl) == []


def test_注入_Step_1_の欄の順を崩す_注記へ移す_出力の形の行を動かすと赤():
    skill = _read("register-rule/SKILL.md")
    assert step1の外れ(skill) == []
    a, b = "- **意図** —", "- **注入の試験** —"
    swapped = skill.replace(a, "@@A@@", 1).replace(b, a, 1).replace("@@A@@", b, 1)
    assert any("順" in x for x in step1の外れ(swapped))
    line = next(l for l in skill.splitlines() if l.startswith("- **誤りが入れない形のどれか**"))
    assert any("順" in x for x in step1の外れ(skill.replace(line, f"<!--\n{line}\n-->", 1)))
    # 出力の形で注入の試験を Step 2 の後へ動かす
    out = skill.replace("／ 注入の試験: <何をわざと入れ・どこで赤／止まる・回す口>", "", 1).replace(
        "Step 2 重複: N 件（<path:line>）→ 新規 / 改訂 / 集約", "Step 2 重複: N 件（<path:line>）→ 新規 / 改訂 / 集約\n       注入の試験: <…>", 1)
    assert "出力の形の Step 1 と Step 2 の間に注入の試験が無い" in step1の外れ(out)
    # 言い回しを変えても欄と順が在れば緑
    assert step1の外れ(skill.replace("起きた事・原因と混ぜずに 1 文", "起きた事と混ぜずに 1 文", 1)) == []


def test_注入_verify_の記録の段と列を囲い_別の節へ移すと赤():
    skill = _read("verify/SKILL.md")
    assert verify_の外れ(skill) == []
    # 報告の雛形の列から記録の所在を抜き、節の地の文へ移す（全文に字は残る）
    moved = skill.replace("｜記録の所在）", "）", 1).replace("## 2. 終わる前（Completion Report）\n", "## 2. 終わる前（Completion Report）\n\n記録の所在\n", 1)
    assert "記録の所在" in moved and any("記録の所在" in x for x in verify_の外れ(moved))
    # 申告でなく記録の段を注記へ
    line = next(l for l in skill.splitlines() if l.startswith("4. **確かめは申告でなく記録で見る**"))
    assert any("申告でなく記録" in x for x in verify_の外れ(skill.replace(line, f"<!-- {line} -->", 1)))
    assert verify_の外れ(skill.replace("記録の無い行", "記録が無い行", 1)) == []


def test_注入_ほんまにできる表の行を別の表へ_論点の窓を注記へ移すと赤():
    text = _read("design-mode/SKILL.md")
    assert ほんまにできる表の外れ(text) == [] and 論点の窓の外れ(text) == []
    row = next(l for l in text.splitlines() if l.strip().startswith("| 届く先 |"))
    # 届く先の行を論点の表へ移す（どの表の 1 列目でも通っていた形）
    moved = text.replace(row + "\n", "", 1).replace("|---|---|---|---|---|\n", "|---|---|---|---|---|\n" + row.strip() + " | | | |\n", 1)
    assert "| 届く先 |" in moved and ほんまにできる表の外れ(moved) == ["ほんまにできる表に行が無い: 届く先"]
    line = next(l for l in text.splitlines() if "論点ごとに窓を並べて同時に進める" in l)
    assert 論点の窓の外れ(text.replace(line, f"<!--\n{line}\n-->", 1)) != []
    # 2 つの言い回しを別の行へ割ると赤
    split = text.replace(line, line.replace("1 本の列にしない。", "1 本の列にしない。\n-", 1), 1)
    assert 論点の窓の外れ(split) != []
    assert 論点の窓の外れ(text.replace("前提待ちの論点は", "前提を待つ論点は", 1)) == []
