"""土台の plugin どうしの借りの流れは、書いた窓が土台の絵の版を上げて足してよい（オーナーの決定 2026-11-19）。

意図: 借りの流れが 1 本増えるたびにオーナーに聞いて PR が止まらないようにし、書いた窓とレビューの窓が同じ許しを読むようにする。
課題: 借りの流れが 1 本増えるたびに合意した絵との差になり、毎回オーナーに聞いて PR が止まっていた。
原因: 許しの置き場が決まっていなかった。許しは細目 §7「③の照らし方」に 1 か所だけ置き、review-pr 点 13 手順 5 はそれを
在り処として指す。片方だけ消えると、書いた窓は足してよいのにレビューの窓は fail にする（またはその逆）ので、両方を照らす。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
RULE = "土台の plugin どうしの借りの流れは、書いた窓が土台の絵の版を上げて足す。"


def _節7():
    text = (ROOT / "plugins/core/細目.md").read_text(encoding="utf-8")
    m = re.search(r"^## 7\..*?(?=^## )", text, re.S | re.M)
    assert m, "細目に §7 が無い"
    return m.group(0)


def test_細目7の照らし方に借りの流れの許しが在る():
    sec = _節7()
    line = next((ln for ln in sec.splitlines() if "**③の照らし方**" in ln), "")
    assert RULE in line, f"細目 §7「③の照らし方」に「{RULE}」が無い"


def test_review_pr_手順5が細目7の許しを在り処として指す():
    text = (ROOT / "plugins/checker/skills/review-pr/SKILL.md").read_text(encoding="utf-8")
    step5 = next((ln for ln in text.splitlines() if ln.startswith("5. **合意した絵そのものを変える PR**")), "")
    assert "土台の plugin どうしの借りの矢印だけを足す版上げ" in step5
    assert "細目 §7「③の照らし方」が在り処" in step5
