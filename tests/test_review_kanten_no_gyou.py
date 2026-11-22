"""review-pr の見る点は、写す元の一般の観点を、受け持つ表の行に持つ。

意図: 一般の観点（壊すと赤・迂回・既定で止まる など）が、見る点の表のどの行が受け持つかまで決まっている事を守る。
課題: 試験が SKILL の全文に字が在るかだけを見ていたので、観点を別の行へ移しても・注記に置いても緑だった。
原因: 試験が表の行を読む口を持たず、字で照らしていた（表の行は tests/md_yomi.py で読む）。
"""
from pathlib import Path

from md_yomi import 表の行

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "checker"


# 写す元の一般の観点と、それを受け持つ行（見る点の表の点の番号か、言語ごとの点の表の言語）。
観点の持ち主 = {
    1: ["オーナーの原文"],                        # 依頼文の範囲が原文より縮んでいないか
    6: ["本番の効き目"],                          # 直したを本番の効き目で確かめたか
    8: ["壊すと赤・戻すと緑", "注入の試験"],      # 歯の実証・誤りの類をわざと入れて拒む試験
    10: ["守備範囲", "迂回", "呼ぶ側と呼ばれる側"],  # 退役した仕組み・新しい関所の迂回・共通の仕組みの参照切れ
    12: ["既定で止まる", "黙って既定の値", "申告だけ"],  # 誤りが入れない形（核 §3）
    "Python": ["except: pass", "shell=True"],
    "JS・TS": ["await"],
    "Shell": ["set -euo pipefail", "未クォート"],
}


def 見る点の行(skill):
    """review-pr の見る点の表を {点の番号: 行の字}、言語ごとの点の表を {言語: 行の字} で返す。"""
    rows = {int(r[0].split(" ")[0]): " | ".join(r) for r in 表の行(skill, "点") if r[0].split(" ")[0].isdigit()}
    rows.update({r[0]: " | ".join(r) for r in 表の行(skill, "言語・対象")})
    return rows


def 観点の外れ(skill):
    rows = 見る点の行(skill)
    bad = [f"{who} の行に無い: {w}" for who, words in 観点の持ち主.items() for w in words if w not in rows.get(who, "")]
    nums = sorted(k for k in rows if isinstance(k, int))
    if nums != list(range(1, len(nums) + 1)):
        bad.append(f"点の番号が 1 から抜けなく並ばない: {nums}")
    return bad


def test_見る点が写す元の一般の観点を受け持つ行に持つ():
    skill = (PLUGIN / "skills" / "review-pr" / "SKILL.md").read_text(encoding="utf-8")
    assert 観点の外れ(skill) == []


def test_注入_観点を別の行へ移すと赤():
    skill = (PLUGIN / "skills" / "review-pr" / "SKILL.md").read_text(encoding="utf-8")
    # 点 6 の行から「本番の効き目」を抜き、点 9 の行へ置く（SKILL の中に字は残る）
    six = next(l for l in skill.splitlines() if l.startswith("| 6 "))
    moved = skill.replace(six, six.replace("本番の効き目", "効き目"), 1)
    nine = next(l for l in moved.splitlines() if l.startswith("| 9 "))
    moved = moved.replace(nine, nine.rstrip(" |") + "・本番の効き目 |", 1)
    assert "本番の効き目" in moved
    assert any("6 の行に無い: 本番の効き目" in x for x in 観点の外れ(moved))
    # 表の外（注記）に置いても数えない
    gone = skill.replace("except: pass", "except だけ").replace("`except` だけ", "x") + "\n<!-- | Python | except: pass | -->\n"
    assert any("Python の行に無い: except: pass" in x for x in 観点の外れ(gone))
