"""オーナーの決定が決まりの文へ戻る道は 1 本（細目 §8「決めた事」→ skill register-rule）で、決まりの文には決定の日付の札を置かないか（注入の試験）。

課題: オーナーの決定が決定の記録にだけ残り、決まりの文（核・細目・skill）へ戻る道が無かった。決まりの文に「（オーナー決定 日付）」の札が
散り、どれが今の結論でどれが記録かが混ざった。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIROKU = ROOT / "plugins" / "core" / "細目" / "08-記録.md"
REGISTER = ROOT / "plugins" / "dev-flow" / "skills" / "register-rule" / "SKILL.md"

# 決まりの文＝窓が動く時に読む物（核・振る舞い・細目・skill の本文・直す人の手順）
RULE_FILES = [ROOT / "plugins" / "core" / "核.md", ROOT / "plugins" / "core" / "振る舞い.md", ROOT / "CONTRIBUTING.md",
              *sorted((ROOT / "plugins" / "core" / "細目").glob("*.md")), *sorted(ROOT.glob("plugins/*/skills/*/SKILL.md"))]

_DATE = r"\d{4}-\d{2}-\d{2}"
_STAMP = re.compile(rf"(?:オーナー|決定|同意)[^。\n]{{0,8}}{_DATE}|{_DATE}[^。\n]{{0,4}}(?:決定|同意)")


def stamps(text):
    """決まりの文に残る決定の日付の札（決定の記録へ置く物）を返す。"""
    return [m.group(0) for m in _STAMP.finditer(text)]


def route_ok(kiroku, register):
    """細目 §8 の「決めた事」に `決まりへ` の欄と register-rule への道が在り、register-rule の Step 5 がその欄を書くか。"""
    line = next((l for l in kiroku.splitlines() if "**決めた事**" in l), "")
    return ("`意図｜決めた中身｜原文｜時刻｜決まりへ`" in line and "register-rule" in line and "この 1 本" in line and "決まりの文には日付・原文・経緯を書かない。" in line
            and re.search(r"決定の記録のその行の `決まりへ` に", register) is not None)


def test_決定が決まりへ戻る道が在る():
    assert route_ok(KIROKU.read_text(encoding="utf-8"), REGISTER.read_text(encoding="utf-8"))


def test_注入_道を消すと赤():
    kiroku, register = KIROKU.read_text(encoding="utf-8"), REGISTER.read_text(encoding="utf-8")
    assert not route_ok(kiroku.replace("｜決まりへ", ""), register)
    assert not route_ok(kiroku.replace("register-rule", "記録"), register)
    assert not route_ok(kiroku.replace("決まりの文には日付・原文・経緯を書かない。", ""), register)
    assert not route_ok(kiroku, register.replace("その行の `決まりへ` に", "その行に"))


def test_決まりの文に決定の日付の札が無い():
    hit = [f"{p.relative_to(ROOT)}: {s}" for p in RULE_FILES for s in stamps(p.read_text(encoding="utf-8"))]
    assert not hit, "決定の日付・出所は決定の記録へ（細目 §8「決めた事」）:\n" + "\n".join(hit)


def test_注入_日付の札を入れると拾う():
    assert stamps("相談で出た事は全部やる（オーナー決定 2026-11-19）。")
    assert stamps("写しを試験が照らす（オーナーの決定 2026-11-22）。")
    assert stamps("版を上げる（2026-11-21 の決定）。")
    assert stamps("止めてよい（オーナー同意 2026-11-19）。")
    # 決定でない日付（版の例・実測の日）は拾わない
    assert not stamps("版（例 `2026-11-13.1`）を入れる。")
    assert not stamps("何時間も空く・2026-11-20 実測 7 時間")
