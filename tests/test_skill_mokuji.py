"""skill の説明文（起動の時に毎回入る）と SKILL.md の本文（開いた時に入る）を小さく保つ。

意図: 起動の時に入る説明文と、skill を開いた時に読む本文を小さくし、細かい事は要る時に読む同じ dir の file に置く。
課題: 説明文が 19 skill で 5639 字、本文が 1 万字を超える SKILL.md があり、使わない事まで毎回・開くたびに読んでいた。
原因: 説明文に起動の言葉と中身の要約を並べ、SKILL.md に手順の細目まで全部書いていた（目次と細目を分ける形が無かった）。
合格: 説明文・本文が上限を超える、起動の言葉が説明文から落ちる、目次が指す file が無い・目次から指されない file が在ると赤。
"""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
spec = importlib.util.spec_from_file_location("measure_load", ROOT / "scripts" / "measure_load.py")
measure_load = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure_load)

DESC_MAX = 150     # 説明文の上限（字）。1〜2 行
BODY_MAX = 3000    # SKILL.md の本文（頭の後）の上限（字）。目次＋いつも要る事だけ
# 道具が SKILL.md から直に読む節を持つ skill だけ、理由つきで上限を広げる（理由の無い広げは置かない）。
BODY_ALLOW = {
    # 「見る点」「判定の形」の節は verdict_form.py・kaku.py が SKILL.md から読む（動かさない約束）
    "checker:review-pr": (4400, "verdict_form.py と kaku.py が「見る点」「判定の形」をこの file から読む"),
    # 見張りの目次の表と値の表は、試験と guard の値の照らしが SKILL.md の行を読む
    "guard:guard-rules": (4400, "見張りの目次の表・値の表の行を試験と値の照らしが SKILL.md から読む"),
}

# 起動の言葉: 説明文に残す語（合言葉・「〜で起動」「〜と言われた時」の語）。前の説明文から写した。
TRIGGERS = {
    "guard:guard-rules": ["guard", "止められた", "知らされた", "値"],
    "checker:review-pr": ["PR をレビューして", "チェック役で見て", "実装をレビューして"],
    "session-watch:watch-log": ["会話ログを点検して", "この窓の返事を点検して"],
    "session-watch:title-mark": ["窓の題", "問いを出す前", "手の窓", "返事を締める"],
    "docs-kit:big-picture": ["全体の絵を描いて", "完成像を絵にして", "なんでこうなるの？", "絵どおりか照らして"],
    "dev-flow:design-mode": ["設計モードで", "まだ実装しないで", "提案して", "調査して", "整理して", "相談"],
    "dev-flow:public-repo": ["公開の repo を作って", "public にしたい", "公開で出し直して", "見回りで外れと出た",
                             "公開する", "public にして", "公開の検査を付けて"],
}

LINK = re.compile(r"`([^`\s]+\.md)`")   # 目次が同じ dir の file を指す形（`見張り.md` など）


def skill_dirs():
    return {f"{d.parent.parent.name}:{d.name}": d for d in sorted(PLUGINS.glob("*/skills/*")) if (d / "SKILL.md").is_file()}


def problems(name: str, text: str, siblings: set[str]) -> list[str]:
    """1 つの skill の崩れを並べる（空なら良い）。siblings は SKILL.md と同じ dir の .md（SKILL.md を除く）。"""
    desc, body = measure_load.split_front(text)
    out = []
    if not desc:
        out.append(f"{name}: 説明文が無い")
    if len(desc) > DESC_MAX:
        out.append(f"{name}: 説明文 {len(desc)} 字 > {DESC_MAX}")
    limit = BODY_ALLOW.get(name, (BODY_MAX, ""))[0]
    if len(body) > limit:
        out.append(f"{name}: SKILL.md の本文 {len(body)} 字 > {limit}（細目は同じ dir の file へ）")
    for w in TRIGGERS.get(name, []):
        if w not in desc:
            out.append(f"{name}: 起動の言葉「{w}」が説明文に無い")
    named = {m for m in LINK.findall(body) if "/" not in m}
    for m in sorted(named - siblings):
        out.append(f"{name}: 目次が指す `{m}` が同じ dir に無い")
    for m in sorted(siblings - named):
        out.append(f"{name}: `{m}` を目次が指していない（読まれない）")
    return out


def _check(name: str):
    d = skill_dirs()[name]
    siblings = {p.name for p in d.glob("*.md") if p.name != "SKILL.md"}
    return problems(name, (d / "SKILL.md").read_text(encoding="utf-8"), siblings)


@pytest.mark.parametrize("name", sorted(TRIGGERS))
def test_skill_is_small_and_keeps_triggers(name):
    assert _check(name) == []


def test_allowances_have_reason_and_name_real_skills():
    """広げた上限は理由を持ち、在る skill だけを名指す（広げを黙って足さない）。"""
    assert set(BODY_ALLOW) <= set(skill_dirs())
    assert all(n > BODY_MAX and why for n, why in BODY_ALLOW.values())


def test_allowance_is_still_a_limit():
    bad = GOOD + "う" * (BODY_ALLOW["checker:review-pr"][0] + 1)
    assert any("本文" in p for p in problems("checker:review-pr", bad, {"細目.md"}))


def test_triggers_name_real_skills():
    """起動の言葉の表が、無い skill を名指していない（名を変えた時に照らしが黙って外れない）。"""
    assert set(TRIGGERS) <= set(skill_dirs())


# --- わざと崩して赤になるのを確かめる（注入） ---

GOOD = "---\nname: x\ndescription: 設計モードで・まだ実装しないで・提案して・調査して・整理して・相談の時に使う。\n---\n\n# x\n\n細目は `細目.md`。\n"
NAME = "dev-flow:design-mode"


def test_good_passes():
    assert problems(NAME, GOOD, {"細目.md"}) == []


def test_long_description_is_red():
    bad = GOOD.replace("の時に使う。", "の時に使う。" + "あ" * DESC_MAX)
    assert any("説明文" in p and ">" in p for p in problems(NAME, bad, {"細目.md"}))


def test_long_body_is_red():
    bad = GOOD + "い" * (BODY_MAX + 1)
    assert any("本文" in p for p in problems(NAME, bad, {"細目.md"}))


def test_dropped_trigger_is_red():
    bad = GOOD.replace("まだ実装しないで・", "")
    assert problems(NAME, bad, {"細目.md"}) == [f"{NAME}: 起動の言葉「まだ実装しないで」が説明文に無い"]


def test_dead_link_is_red():
    assert any("同じ dir に無い" in p for p in problems(NAME, GOOD, set()))


def test_unlinked_file_is_red():
    assert any("指していない" in p for p in problems(NAME, GOOD, {"細目.md", "迷子.md"}))
