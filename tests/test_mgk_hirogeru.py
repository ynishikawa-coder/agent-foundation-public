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
from test_core_plugin import raw_text, used_texts

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


def test_赤の時の直しの文は意図とのずれから入る():
    # 生の文で読む: docstring（__doc__ や argparse の説明）も赤の時に出る直しの文
    tools = used_texts(under=("plugins", "scripts", "public-guard"), suffixes=(".py", ".sh", ".mjs", ".js"), read=raw_text)
    bad = {str(rel): b for rel, text in tools if (b := 原因から入る直し(text))}
    assert not bad, bad


def test_注入_原因から入る直しの文は拒む():
    assert 原因から入る直し('ROOT_CAUSE = "直し: 赤の行を潰さず、細目 §3「まず構造を疑う」で原因から直す"')
    assert 原因から入る直し('print("直し: 崩れた原因を、意図とずらさず細目 §3「まず構造を疑う」で探す")')
    assert not 原因から入る直し('X = "直し: 意図（守る物）とのずれから入り、原因を細目 §3「まず構造を疑う」で探す"')


def test_CONTRIBUTING_の赤と_red_は意図とのずれから入る():
    c = _read("CONTRIBUTING.md")
    assert "外れた意図とのずれから入って細目 §3「まず構造を疑う」で原因を探して直し" in c
    assert "その試験が守る意図とのずれから入って細目 §3「まず構造を疑う」で原因を探して直す。" in c


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
