"""レビューの窓が PR 本文の「残り」の台帳の行を開き、行き先・直しを本文の同じ原因の一覧と照らす（止めない）。

意図: 同じ原因の他の問題が、台帳の行として行き先つきで持たれているかを別の目が見る。
課題: レビューは本文の「残り」の言い分だけを読み、台帳の行の行き先・直しが本文の一覧とずれていても通っていた。
原因: skill review-pr の手順に、残りが指す台帳の行を開く段が無かった（本文の申告で照らした事にできた）。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "plugins" / "checker" / "skills" / "review-pr" / "SKILL.md"


def _step(text):
    lines = [l for l in text.split("\n") if "残りの台帳の行を開いて照らす" in l]
    assert len(lines) == 1, "手順に「残りの台帳の行を開いて照らす」が 1 つだけ在る"
    return lines[0]


def test_手順に残りの台帳の行を開いて照らす段が在り止めない():
    text = SKILL.read_text(encoding="utf-8")
    step = _step(text)
    assert text.index(step) < text.index("3. **物差しを自分で回す**")        # 判定を書く前の手順の中
    for word in ("行き先", "直し", "同じ原因の他の問題", "[台帳へ｜整地]", "`[止める｜…]` にしない", "確認していない範囲"):
        assert word in step, word


def test_注入_段を消すと赤():
    text = SKILL.read_text(encoding="utf-8")
    step = _step(text)
    gone = text.replace(step + "\n", "")
    try:
        _step(gone)
    except AssertionError:
        pass
    else:
        raise AssertionError("段を消しても見つかった")
