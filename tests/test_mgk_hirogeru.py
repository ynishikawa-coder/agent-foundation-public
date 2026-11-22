"""根治の 5 段（意図→課題→原因→解決→未来）を、振り返り・直しの他の型にも広げた形を照らす。

意図: 振り返り・レビュー・赤の時の直しの文・決定・台帳の型が、本来の意図を独立した段として持ち、起きた事（課題）と原因を分けて書かせる。
課題: 根治の型を 5 段にしても、verify の完了報告・review-pr の所見・赤の時の「直し:」・register-rule・codex の戻り・
  spec-doc の 00 宣言・全体の絵の meta と説明・細目の台帳と決定の記録が、意図の欄を持たず事象と原因を 1 欄に混ぜたままだった。
原因: 型ごとに欄を前例の真似で作り、根治の段の定義（細目 §3）から欄を引いて作る決まりが無かった。
"""
import importlib.util
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
P = ROOT / "plugins"


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


# ── 赤の時の「直し:」の文は意図とのずれから入る ─────────────────────────

ENTRY = re.compile(r"細目(?:\s*§\s*\d+)?「まず構造を疑う」")
直しの文 = re.compile(r"(?:直し|直しは)[:：、].*?(?:\"|$)", re.M)


def 原因から入る直し(text):
    """根治の入口を指す「直し」の文のうち、意図より先に原因を書く・意図が無い物を返す。"""
    bad = []
    text = re.sub(r'"\s*\n\s*"', "", text)   # 続け書きの文字列（"…"\n  "…"）は 1 つの文として見る
    for line in text.splitlines():
        if "直し" not in line or not ENTRY.search(line):
            continue
        i, c = line.find("意図"), line.find("原因")
        if i < 0 or (c >= 0 and c < i):
            bad.append(line.strip()[:120])
    return bad


def _tools():
    out = []
    for base in ("plugins", "scripts", "public-guard"):
        for f in (ROOT / base).rglob("*"):
            if f.suffix in {".py", ".sh", ".mjs", ".js"} and f.is_file() and "verdict_form.py" not in f.name:
                out.append(f)
    return out


def test_赤の時の直しの文は意図とのずれから入る():
    bad = {str(f.relative_to(ROOT)): b for f in _tools() if (b := 原因から入る直し(f.read_text(encoding="utf-8")))}
    assert not bad, bad


def test_注入_原因から入る直しの文は拒む():
    assert 原因から入る直し('ROOT_CAUSE = "直し: 赤の行を潰さず、細目 §3「まず構造を疑う」で原因から直す"')
    assert 原因から入る直し('print("直し: 崩れた原因を、意図とずらさず細目 §3「まず構造を疑う」で探す")')
    assert not 原因から入る直し('X = "直し: 意図（守る物）とのずれから入り、原因を細目 §3「まず構造を疑う」で探す"')


def test_CONTRIBUTING_の赤と_red_は意図とのずれから入る():
    c = _read("CONTRIBUTING.md")
    assert "外れた意図とのずれから入って細目 §3「まず構造を疑う」で原因を探して直し" in c
    assert "その試験が守る意図とのずれから入って細目 §3「まず構造を疑う」で原因を探して直す。" in c


# ── 型の欄 ────────────────────────────────────────────────────
# 型ごとの欄の定義は tests/data/型の欄.json 1 つ。根治の段の名と順は細目 §3 の「根治の 5 段」から引く。
# 照らすのは決まった字の有無でなく欄の形: 欄の始まりの印（行の頭・見出し・箇条・太字・`|`・`｜`・`／`・`/`・`—`・丸数字・`）の後に
# 名が在り、すぐ欄の終わりの印（`:`・`：`・`（`・太字の閉じ・`|`・`｜`・`／`・`/`・`・行の終わり）が続く所を欄と見る。

型の欄 = json.loads(_read("tests/data/型の欄.json"))["型"]
_始まりの印 = r"(?:^[ \t]*(?:#+[ \t]*|[-*][ \t]*|\d+\.[ \t]*)?(?:\*\*|`)?|[|｜／/—`①②③④⑤⑥⑦⑧⑨⑩][ \t]*|\*\*)"
_終わりの印 = r"(?=[:：（(／/`]|\*\*|[ \t]*[|｜]|[ \t]*$)"


def 根治の段():
    """細目 §3「根治の 5 段」の段の名を順に返す（型の欄の名と順の正本）。"""
    s = _read("plugins/core/細目.md")
    head = s.index("- **根治の 5 段**")
    names = []
    for line in s[head:].splitlines()[1:]:
        m = re.match(r"^  - \*\*(.+?)\*\* — ", line)
        if not m:
            break
        names.append(m.group(1))
    return names


def 型の所(text, kata):
    """file の中の型の所（始まりの行から、幅の終わりまで）を返す。無ければ None。"""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if re.search(kata["始まり"], line):
            out = [line]
            if kata["幅"] != "行":
                for nxt in lines[n + 1:]:
                    if nxt.startswith("```") or (kata["幅"] == "塊" and not nxt.strip()) or \
                       (kata["幅"] == "節" and re.match(r"^#+\s", nxt)):
                        break
                    out.append(nxt)
            return "\n".join(out)
    return None


def 欄の位置(unit, name):
    """name が欄として在る最初の位置（字だけ在って欄でない物は数えない）。無ければ -1。"""
    m = re.search(_始まりの印 + "(" + re.escape(name) + ")" + _終わりの印, unit, re.M)
    return m.start(1) if m else -1


def 欄の外れ(unit, names):
    """欄が別々に・この順で在るかを照らし、外れを返す（空なら合う）。"""
    if unit is None:
        return ["型の所が見つからない"]
    pos = {n: 欄の位置(unit, n) for n in names}
    bad = [f"欄が無い: {n}" for n, p in pos.items() if p < 0]
    seen = [pos[n] for n in names if pos[n] >= 0]
    if not bad and seen != sorted(seen):
        bad.append("欄の順が違う: " + " → ".join(sorted(names, key=pos.get)))
    return bad


def _ids(k):
    return k["名"]


def test_型の欄の段の名と順は細目の根治の段に沿う():
    dan = 根治の段()
    assert dan[:3] == ["意図", "課題", "原因"], dan
    for k in 型の欄:
        steps = [n for n in k["欄"] if n in dan]
        assert steps, k["名"]
        assert steps == sorted(steps, key=dan.index), k["名"]


@pytest.mark.parametrize("kata", 型の欄, ids=_ids)
def test_型は意図などの欄を別々にこの順で持つ(kata):
    assert 欄の外れ(型の所(_read(kata["file"]), kata), kata["欄"]) == []


def _字だけ残す(unit, name):
    """name の欄を壊し、字は残す（「意図:」→「意図も込みの文:」）。"""
    return re.sub(_始まりの印 + "(" + re.escape(name) + ")" + _終わりの印,
                  lambda m: m.group(0) + "も込みの文", unit, flags=re.M)


def _言い回しを変える(unit, names):
    """欄の名を除く言葉を全部言い換える（欄の名と区切りの印は残す）。"""
    keep = []

    def _守る(m):
        keep.append(m.group(0))
        return f"\0{len(keep) - 1}\0"

    pat = _始まりの印 + "(?:" + "|".join(map(re.escape, names)) + ")" + _終わりの印
    out = re.sub(r"[ぁ-んァ-ヶ一-龠ー]+", "言い換え", re.sub(pat, _守る, unit, flags=re.M))
    return re.sub(r"\0(\d+)\0", lambda m: keep[int(m.group(1))], out)


@pytest.mark.parametrize("kata", 型の欄, ids=_ids)
def test_注入_欄を消して字だけ残すと赤_言い回しを変えても欄が残れば緑(kata):
    unit = 型の所(_read(kata["file"]), kata)
    for name in kata["欄"]:
        broken = _字だけ残す(unit, name)
        assert name in broken
        assert f"欄が無い: {name}" in 欄の外れ(broken, kata["欄"]), (kata["名"], name)
    reworded = _言い回しを変える(unit, kata["欄"])
    assert reworded != unit, kata["名"]
    assert 欄の外れ(reworded, kata["欄"]) == [], kata["名"]


@pytest.mark.parametrize("kata", 型の欄, ids=_ids)
def test_注入_欄の順を入れ替えると赤(kata):
    unit = 型の所(_read(kata["file"]), kata)
    a, b = kata["欄"][0], kata["欄"][-1]
    pa, pb = 欄の位置(unit, a), 欄の位置(unit, b)
    swapped = unit[:pa] + b + unit[pa + len(a):pb] + a + unit[pb + len(b):]
    assert any(x.startswith("欄の順が違う") for x in 欄の外れ(swapped, kata["欄"])), kata["名"]


def test_注入_型の所が無いと赤():
    assert 欄の外れ(None, ["意図"]) == ["型の所が見つからない"]
    assert 欄の外れ("意図と課題と原因を 1 つの欄に書く:", ["意図", "課題", "原因"])


def test_手順の文は根治の段で読ませる():
    """型の欄の外で、手順の文が根治の段で読ませる所（文の照らし）。"""
    assert "学びを根治の 5 段（意図・課題・原因・解決・未来＝細目 §3）で" in _read("plugins/dev-flow/skills/verify/SKILL.md")
    r = _read("plugins/checker/skills/review-pr/SKILL.md")
    assert "PR 本文の整地の `1. 意図`・`2. 課題`" in r
    assert "整地の意図がオーナーの原文の意図と違う・課題に原因（なぜ）が混ざる" in r
    assert "直し: 細目 §3「まず構造を疑う」で、所見の意図とのずれから原因を探す" in r
    assert "守りたかった意図とのずれ（課題）から原因の段へ戻る" in _read("plugins/dev-flow/skills/register-rule/SKILL.md")
    assert "pack.md の目的・起点ゴール（意図）のどれとどうずれるか（課題）を書き" in _read("plugins/dev-flow/skills/codex/SKILL.md")
    assert "困りごとを出発点にせず意図から書く。" in _read("plugins/dev-flow/skills/spec-doc/SKILL.md")
    assert "検査の赤も、検査が守る意図とのずれから入る。" in _read("plugins/core/細目.md")


# ── 全体の絵 ───────────────────────────────────────────────────

_spec = importlib.util.spec_from_file_location("bp_hirogeru", P / "docs-kit" / "skills" / "big-picture" / "scripts" / "big_picture.py")
bp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bp)
DODAI = ROOT / "docs" / "全体の絵.json"


def test_注入_合意の絵に意図が無いと赤い点で名指す():
    pic = json.loads(DODAI.read_text(encoding="utf-8"))
    pic["meta"].pop("intent", None)
    _, reds = bp.check(pic)
    assert any("meta.intent" in r for r in reds)
    pic["meta"]["intent"] = "どの窓も同じ振る舞いで動く"
    _, reds = bp.check(pic)
    assert not any("meta.intent" in r for r in reds)


def test_説明は起きた所の箱の意図を課題より先に出す():
    pic = json.loads(DODAI.read_text(encoding="utf-8"))
    p = pic["problems"][0]
    text = bp.explain(pic, p["id"])
    lines = text.splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith("- 意図（起きた所の箱が何のために在るか）: "))
    k = next(n for n, l in enumerate(lines) if l.startswith("- 課題（意図とのずれ＝起きた事）: "))
    c = next(n for n, l in enumerate(lines) if l.startswith("- 原因の箱: "))
    assert i < k < c
    at = {b["id"]: b for b in pic["boxes"]}[p["at"][0]]
    assert (at.get("intent") or "まだ聞いていない") in lines[i]


def test_絵の型は意図と課題を分けて出す():
    t = _read("plugins/docs-kit/skills/big-picture/references/template.html")
    assert '<div class="lab">意図（何のために在るか）</div><p id="intent"></p>' in t
    assert '<div class="lab">課題（意図と今のずれ）</div><p id="problem"></p>' in t
    assert "課題（この意図とのずれ＝起きた事）" in t
