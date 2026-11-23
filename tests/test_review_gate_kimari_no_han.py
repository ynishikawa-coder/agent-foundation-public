"""レビューの関所（review_gate.py）が「入ってよい」の時に、判定が従う決まりの版（始めた時の決まり）を出す試験。

初めの判定が在ればその版・無ければ main の先端の版で見る。どちらも分からなければ入ってよいと言わず exit 2。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_gate import GREEN, REQ, pr, rg  # noqa: E402


def test_入ってよい時は判定が従う決まりの版と_first_を出す(capsys, monkeypatch):
    """初めの判定が無ければ main の先端の版と `なし`、在ればその初めの判定の版（後の版の判定や古い形の判定は数えない）。"""
    tip = "fedcba9876543210" * 2 + "fedcba98"
    monkeypatch.setattr(rg, "TIP", tip)
    assert rg.main(["--repo", "o/r", "--pr", "1"], read=lambda *a: (pr(), REQ, GREEN, [])) == 0
    out = capsys.readouterr().out
    assert "決まりの版: %s" % tip[:12] in out and "--first なし" in out
    old_form = {"body": "レビューした窓: session_R0 判定: red\n見た先端: ffffffffffff\n"}
    first = {"body": "レビューした窓: session_R1 判定: red\n見た先端: eeeeeeeeeeee\n決まりの版: 111111111111\n"}
    later = {"body": "レビューした窓: session_R2 判定: red\n見た先端: dddddddddddd\n決まりの版: 222222222222\n"}
    read = lambda *a: (pr(), REQ, GREEN, [old_form, first, later])          # noqa: E731
    assert rg.main(["--repo", "o/r", "--pr", "1"], read=read) == 0
    out = capsys.readouterr().out
    assert "決まりの版: 111111111111" in out and "--first 111111111111" in out


def test_main_の先端の版が分からず初めの判定も無ければ_exit_2(capsys, monkeypatch):
    monkeypatch.setattr(rg, "TIP", "")
    monkeypatch.delenv(rg.TIP_ENV, raising=False)
    assert rg.main(["--repo", "o/r", "--pr", "1"], read=lambda *a: (pr(), REQ, GREEN, [])) == 2
    assert "決まりの版を決められない" in capsys.readouterr().out
