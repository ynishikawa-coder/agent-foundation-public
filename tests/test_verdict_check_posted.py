"""注入の試験: 他の repo の関所が判定を数える時も、判定は始めた時の決まり（決まりの版）で照らす。

意図: 判定を数える関所（例: pixel-office の pr_review_gate）が main の先端の点で照らす写しを持つと、
レビューの途中で点が増えた PR の正しい判定を red と数える。関所は verdict_form.check_posted の 1 つの口を呼ぶ。
誤りの類をわざと入れて拒むかを見る: 初めの版と違う版／初めの判定を古い版で書く／決まりの git が読めない。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules_git  # noqa: E402
from test_checker import vf  # noqa: E402
from test_rules_version import V1, V2, verdict  # noqa: E402


def test_初めの版の判定は後から足された点なしで通り_違う版や古い版は拒む(tmp_path):
    clone, v1 = rules_git.make(tmp_path / "g", V1)
    v2 = rules_git.push_version(clone, V2)
    assert vf.check_posted(verdict(v1), v1[:12], head="0123456789ab", repo=clone) == []
    assert vf.check_posted(verdict(v1), "なし", head="0123456789ab", repo=clone)            # 初めの判定を古い版で
    assert vf.check_posted(verdict(v2, "\n- 13 作り物の新しい点: pass"), v1[:12], head="0123456789ab", repo=clone)  # 違う版
    no_line3 = verdict(v1).replace("決まりの版: %s\n" % v1[:12], "")
    assert vf.check_posted(no_line3, v1[:12], head="0123456789ab", repo=clone)              # 3 行目が無い


def test_決まりの_git_が読めなければ通さず_Unreadable(tmp_path):
    with pytest.raises(vf.Unreadable):
        vf.check_posted(verdict("0123456789ab"), "なし", repo=tmp_path / "無い")
