"""big-picture の kin: 意図を問う前に、ほかの製品の合意した絵（兄弟）で答え済みの意図を引くか（同じ問いを 2 度させない）。

合格の線: 兄弟で同じ理由の箱に意図がある赤い点は「答え済み」に、どの絵にも無い赤い点だけが「聞く」に数わる。
合意していない兄弟・兄弟を渡さない時は照らさない（exit 2）。絵は土台の絵から作る作り物。
"""
import copy
import json

from test_big_picture import agreed, run, write


def _sibling():
    sib = copy.deepcopy(agreed())
    sib["meta"]["title"] = "作り物の兄弟の製品"
    for i, b in enumerate(sib["boxes"]):
        b["intent"] = "兄弟で答えた意図 %d" % i
    return sib


def _mine(sib, ask_only):
    me = copy.deepcopy(agreed())
    me["meta"]["title"] = "作り物の今の製品"
    for b in me["boxes"]:
        b["intent"] = None
    extra = dict(copy.deepcopy(me["boxes"][0]), id="zz_only_here", t=ask_only, why="この製品だけの理由")
    me["boxes"].append(extra)
    return me


def test_兄弟で答え済みの意図は候補に出て_どの絵にも無い意図だけ聞く(tmp_path):
    sib = _sibling()
    me = _mine(sib, "作り物のこの製品だけの箱")
    res = run("kin", write(tmp_path, "me.json", me), write(tmp_path, "sib.json", sib))
    assert res.returncode == 0, res.stdout
    assert "作り物のこの製品だけの箱）: 兄弟にも無い＝聞く" in res.stdout
    assert "聞く赤い点 1" in res.stdout
    assert "兄弟で答えた意図" in res.stdout and "「作り物の兄弟の製品」" in res.stdout


def test_合意していない兄弟の意図は引かない(tmp_path):
    sib = _sibling()
    sib["meta"]["kind"] = "実物"
    sib["meta"].pop("agreed", None)
    sib["meta"]["drawn_from"] = "x@0123456789ab"
    sib["meta"]["drawn_by"] = "session_REVIEW01"
    res = run("kin", write(tmp_path, "me.json", _mine(sib, "x")), write(tmp_path, "sib.json", sib))
    assert res.returncode == 2 and "合意の絵でない" in res.stdout


def test_兄弟を渡さずに聞く数を出さない(tmp_path):
    res = run("kin", write(tmp_path, "me.json", agreed()))
    assert res.returncode == 2 and "兄弟の合意した絵が 1 つも渡されていない" in res.stdout


def test_skill_は意図を問う前に兄弟を引けと書く():
    from test_big_picture import SKILL
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "kin" in text and "兄弟を引かずに意図を問わない" in text
