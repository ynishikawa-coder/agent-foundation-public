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
from saimoku import 全文 as 細目の全文

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


def test_完了報告は意図の欄を持ち_未達は課題と原因を分ける():
    v = _read("plugins/dev-flow/skills/verify/SKILL.md")
    assert "## 意図（このゴールが何のために在るか・頼みの原文から）" in v
    assert "（未達は 課題＝意図とのずれ／原因 を別の行に）" in v
    assert "学びを根治の 5 段（意図・課題・原因・解決・未来＝細目 §3）で" in v


def test_レビューの所見は外れた意図と課題を書き_整地の意図を照らす():
    r = _read("plugins/checker/skills/review-pr/SKILL.md")
    assert "- [止める｜実装] path:関数 — 意図: その所が何のために在るか／課題: 意図とのずれ" in r
    assert "PR 本文の整地の `1. 意図`・`2. 課題`" in r
    assert "整地の意図がオーナーの原文の意図と違う・課題に原因（なぜ）が混ざる" in r
    assert "直し: 細目 §3「まず構造を疑う」で、所見の意図とのずれから原因を探す" in r


def test_規律を足す時は意図を独り立ちで書く():
    rr = _read("plugins/dev-flow/skills/register-rule/SKILL.md")
    assert "- **意図** — その規律が何のために在るか（誰の何を守るか）を、起きた事・原因と混ぜずに 1 文。" in rr
    assert "意図: <何のために在るか 1 文> ／ 形:" in rr
    assert "守りたかった意図とのずれ（課題）から原因の段へ戻る" in rr


def test_codex_の戻りは_pack_の目的とのずれで書く():
    c = _read("plugins/dev-flow/skills/codex/SKILL.md")
    assert "pack.md の目的・起点ゴール（意図）のどれとどうずれるか（課題）を書き" in c
    assert "— ずれ：<pack の目的・起点ゴールのどれと> / 該当：" in c


def test_論点の表は意図の列を持つ():
    d = _read("plugins/dev-flow/skills/design-mode/SKILL.md")
    assert "| 論点 | 意図（何のために決めるか） | 状態（決まった／未決／前提待ち） |" in d


def test_プロダクト宣言は意図から書く():
    s = _read("plugins/dev-flow/skills/spec-doc/SKILL.md")
    assert "② 意図（本来どうありたいか） ③ 課題（意図と今のずれ・なぜは書かない）" in s
    assert "困りごとを出発点にせず意図から書く。" in s


def test_細目の台帳と決定と入口は意図を分ける():
    s = 細目の全文()
    assert "原因と同じ原因の他の問題を 1 つ 1 行にし（意図・課題・原因は別の欄）、行き先を付ける:" in s
    assert "オーナーが決めた事は各社の決定の記録に、意図と決めた中身を分け、原文と時刻つきで書く。" in s
    assert "検査の赤も、検査が守る意図とのずれから入る。" in s


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
