"""レビューの関所・1 つの先端に判定 1 つ・後から足した話は別の PR へ・並べる前に触る file を宣言する、の決まりの文と口。

意図: 決まりの文（CONTRIBUTING §2・review-pr・振る舞いの既定「並走」）と、それを打つ道具（review_gate.py・pr_overlap.py --files）が
揃って在り、文を消すと赤になるようにする。
課題: レビュー中に別の話を同じ PR へ足し、同じ file を取る窓を並べて衝突を作った。
原因: 足してよい時と並べてよい時の決まりと、PR を出す前に重なりを引ける口が無かった。
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "pr_overlap.py"
spec = importlib.util.spec_from_file_location("pr_overlap_files", TOOL)
po = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(po)


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_並走に触る_file_の宣言と列の文が在る():
    assert ("並べる前に触る file を宣言し、同じ file を取る窓は列にする（`pr_overlap.py --files`）。"
            in _read("plugins/core/振る舞い.md"))


def test_宣言した_file_を開いている_PR_が書き換えていれば名指す():
    others = {"#7 claude/a": ["CONTRIBUTING.md", "x.py"], "#8 claude/b": ["docs/y.md"]}
    assert po.claimed(["./CONTRIBUTING.md", "z.py"], others) == [("#7 claude/a", "CONTRIBUTING.md")]
    assert po.claimed(["z.py"], others) == []


def test_files_は_repo_無しでは重ならないと言わない():
    res = subprocess.run([sys.executable, "-B", str(TOOL), "--files", "a.md"], capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin"})
    assert res.returncode == 3 and "見ていない" in res.stdout


def test_CONTRIBUTING_の_2_にレビューの関所と別の_PR_への文が在る():
    t = _read("CONTRIBUTING.md")
    assert "**レビューを頼むのは関所を通ってから。**" in t
    assert "通らない間に頼まれたレビューの窓は、判定に入らず「まだ」とだけ返す。" in t
    assert "**レビューが始まった後に、依頼に無い話を同じ PR へ足さない。**" in t
    assert "足されていたら、レビューの窓は判定せず「別の PR へ」と返す。" in t
    assert "1 つの先端に判定は 1 つ（1 回の見直しで全部の点を見る）。" in t


def test_review_pr_は関所を回してから見て_判定は先端に_1_つ():
    t = _read("plugins/checker/skills/review-pr/SKILL.md")
    assert '"${CLAUDE_PLUGIN_ROOT}/scripts/review_gate.py" --repo <owner/name> --pr <番号>' in t
    assert "exit 1・2 の時は見ず・判定を書かず・PR にコメントを残さず" in t
    assert "**1 つの先端に判定は 1 つ**" in t
    assert "**前回から足された話は見ない**" in t and "`別の PR へ <PR> <枝>@<SHA12> 話=" in t
    assert (ROOT / "plugins" / "checker" / "scripts" / "review_gate.py").is_file()
