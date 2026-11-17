"""チェック役（plugins/checker）の判定の形の道具が、作り物の判定で合う／合わないを見る。"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "checker"

spec = importlib.util.spec_from_file_location("verdict_form", PLUGIN / "scripts" / "verdict_form.py")
vf = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True   # 写しの置き場（plugins/）に __pycache__ を作らない＝写しの照らしを汚さない
spec.loader.exec_module(vf)

GREEN = """レビューした窓: session_REVIEW01 判定: green
見た先端: 0123456789ab
job: 作り物

## verdict
green

## 点
- 1 依頼の充足: pass
- 2 宣言した path: pass
- 3 別の目: 書いた窓 session_WRITER01 ≠ この窓
- 4 回帰: pass（check_all: 緑）
- 5 秘密・顧客の物: pass
- 6 当て物・本番の効き目: pass
- 7 なくす物: pass
- 8 歯と口・注入の試験: N/A
- 9 文書の事実: pass
- 10 退役・迂回・呼ぶ側: N/A
- 11 言語ごとの点: N/A
- 12 既定で止まる: N/A

## 所見
- [後の便｜整地] 作り物の気づき
"""

RED = """レビューした窓: session_REVIEW01 判定: red
見た先端: 0123456789ab

## verdict
red

## 点
- 1 依頼の充足: fail（作り物の欠け）
- 2 宣言した path: pass
- 3 別の目: 書いた窓 session_WRITER01 ≠ この窓
- 4 回帰: pass（check_all: 緑）
- 5 秘密・顧客の物: pass
- 6 当て物・本番の効き目: pass
- 7 なくす物: pass
- 8 歯と口・注入の試験: N/A
- 9 文書の事実: pass
- 10 退役・迂回・呼ぶ側: N/A
- 11 言語ごとの点: N/A
- 12 既定で止まる: N/A

## 所見
- [止める｜実装] plugins/x.py — 作り物の欠け
- [後の便｜設計] 作り物の気づき
"""


def test_型どおりの判定は通る():
    assert vf.check(GREEN, writer="session_WRITER01", head="0123456789abcdef") == []
    assert vf.check(RED, writer="session_WRITER01") == []


def test_書いた窓とレビューした窓が同じなら誤り():
    errs = vf.check(GREEN, writer="session_REVIEW01")
    assert any("別の目" in e for e in errs)


def test_止めるが在るのに_green_は誤り():
    errs = vf.check(GREEN.replace("[後の便｜整地]", "[止める｜実装]"))
    assert any("判定は red" in e for e in errs)


def test_見た先端が今の先端と違えば誤り():
    errs = vf.check(GREEN, head="fedcba9876543210")
    assert any("見た先端" in e for e in errs)


def test_blocked_の_red_は止めるが無くてよい():
    text = RED.replace("## verdict\nred", "## verdict\nred（blocked: 物差しが回らない）").replace(
        "- [止める｜実装] plugins/x.py — 作り物の欠け\n", "")
    assert vf.check(text) == []


def test_札と形の崩れを拾う():
    errs = vf.check("レビューした窓: 自分 判定: ok\n\n## verdict\nたぶん良い\n\n## 所見\n- 良さそう\n")
    assert len(errs) >= 4


def test_skill_が判定の形の道具を指す():
    skill = (PLUGIN / "skills" / "review-pr" / "SKILL.md").read_text(encoding="utf-8")
    assert "verdict_form.py" in skill
    assert json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"] == "checker"


def test_見る点が写す元の一般の観点を全部持つ():
    skill = (PLUGIN / "skills" / "review-pr" / "SKILL.md").read_text(encoding="utf-8")
    for word in [
        "オーナーの原文",                       # 依頼文の範囲が原文より縮んでいないか
        "本番の効き目",                         # 直したを本番の効き目で確かめたか
        "壊すと赤・戻すと緑",                   # 歯の実証
        "守備範囲", "迂回",                      # 退役した仕組み・新しい関所の迂回
        "呼ぶ側と呼ばれる側",                   # 共通の仕組みの参照切れ
        "except: pass", "shell=True", "set -euo pipefail", "未クォート", "await",  # 言語ごとの点
        "注入の試験",                           # 根治と言う直しに、誤りの類をわざと入れて拒む試験が在るか
        "既定で止まる", "黙って既定の値", "申告だけ",  # 誤りが入れない形（核 §3）
    ]:
        assert word in skill, f"見る点に無い: {word}"
    points = [l.split("|")[1].strip().split(" ")[0] for l in skill.splitlines() if l.startswith("| ") and l.split("|")[1].strip()[:2].strip().isdigit()]
    assert points == [str(i) for i in range(1, 13)], points


# 注入の試験: 判定の `## 点` の欄に誤りをわざと入れ、形の道具が赤にする事を見る。
# 点の正本は review-pr の SKILL.md の表（道具はそこを直に読む）。


def test_点の正本は_skill_の表で_1_から_12():
    assert sorted(vf.load_points()) == list(range(1, 13))


def test_点を_1_つ抜くと赤():
    for no, name in vf.load_points().items():
        lines = [l for l in GREEN.splitlines() if not l.startswith("- %d %s:" % (no, name))]
        errs = vf.check("\n".join(lines) + "\n", writer="session_WRITER01")
        assert any("点 %d " % no in e and "無い" in e for e in errs), (no, errs)


def test_点の値が選べる値の外なら赤():
    for bad in ["ok", "たぶん pass", "passed", "済", ""]:
        text = GREEN.replace("- 5 秘密・顧客の物: pass", "- 5 秘密・顧客の物: " + bad)
        errs = vf.check(text, writer="session_WRITER01")
        assert any("点 5" in e for e in errs), (bad, errs)


def test_点の節が無いと赤():
    text = GREEN[:GREEN.index("## 点")] + GREEN[GREEN.index("## 所見"):]
    assert any("`## 点` の節が無い" in e for e in vf.check(text))


def test_表に無い点と重なりと名の違いは赤():
    assert any("点 13" in e for e in vf.check(GREEN.replace("- 12 既定で止まる: N/A", "- 12 既定で止まる: N/A\n- 13 作り物: pass")))
    assert any("2 度" in e for e in vf.check(GREEN.replace("- 2 宣言した path: pass", "- 2 宣言した path: pass\n- 2 宣言した path: pass")))
    assert any("点 4 の名" in e for e in vf.check(GREEN.replace("- 4 回帰:", "- 4 回り:")))


def test_点に_fail_が在るのに_green_は赤():
    errs = vf.check(GREEN.replace("- 7 なくす物: pass", "- 7 なくす物: fail（残る）"))
    assert any("判定は red" in e for e in errs)


def test_点_3_の書いた窓が自分か名乗りと違えば赤():
    assert any("点 3" in e for e in vf.check(GREEN.replace("書いた窓 session_WRITER01", "書いた窓 session_REVIEW01")))
    assert any("点 3" in e for e in vf.check(GREEN, writer="session_OTHER01"))


def test_見る点の表が読めない時は止まる(tmp_path):
    empty = tmp_path / "SKILL.md"
    empty.write_text("# 表の無い作り物\n", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        vf.load_points(empty)
