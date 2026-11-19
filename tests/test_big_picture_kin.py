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
    assert "作り物のこの製品だけの箱）: 兄弟に同じ理由の答えが無い＝聞く" in res.stdout
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


def _carry(me, sib, i, intent=None, why=None):
    sb = sib["boxes"][i]
    b = me["boxes"][i]
    b["intent"] = intent or "［%sと同じ答え］%s" % (sib["meta"]["title"], sb["intent"])
    b["intent_from"] = {"title": sib["meta"]["title"], "version": sib["meta"]["version"], "box": sb["id"]}
    if why:
        b["why"] = why
    return me


def test_引いた意図が兄弟の絵と合えば通る(tmp_path):
    sib = _sibling()
    me = _carry(_mine(sib, "x"), sib, 1)
    res = run("kin", write(tmp_path, "me.json", me), write(tmp_path, "sib.json", sib))
    assert res.returncode == 0, res.stdout


def test_作った意図に兄弟の札を付けても止まる(tmp_path):
    sib = _sibling()
    me = _carry(_mine(sib, "x"), sib, 1, intent="［作り物の兄弟の製品と同じ答え］兄弟が言っていない意図")
    res = run("kin", write(tmp_path, "me.json", me), write(tmp_path, "sib.json", sib))
    assert res.returncode == 1 and "引いた意図が兄弟" in res.stdout


def test_理由の違う箱へ兄弟の答えを当てると止まる(tmp_path):
    sib = _sibling()
    me = _carry(_mine(sib, "x"), sib, 1, why="この製品だけの別の理由")
    res = run("kin", write(tmp_path, "me.json", me), write(tmp_path, "sib.json", sib))
    assert res.returncode == 1 and "理由（why）が違う" in res.stdout


def test_引いた札に元が無い絵は形の誤り(tmp_path):
    sib = _sibling()
    me = _carry(_mine(sib, "x"), sib, 1)
    del me["boxes"][1]["intent_from"]
    res = run("check", write(tmp_path, "me.json", me))
    assert res.returncode == 1 and "intent_from" in res.stdout


def test_名だけ同じで理由の違う箱は答え済みに数えない(tmp_path):
    sib = _sibling()
    me = _mine(sib, "x")
    me["boxes"][1]["why"] = "名は同じだが理由が違う"
    res = run("kin", write(tmp_path, "me.json", me), write(tmp_path, "sib.json", sib))
    assert res.returncode == 0 and "聞く赤い点 2" in res.stdout and "理由が違うので当てない" in res.stdout


def test_兄弟の意図が空の箱は答え済みにしない(tmp_path):
    sib = _sibling()
    sib["boxes"][1]["intent"] = None
    sib["meta"]["kind"] = "合意"
    me = _mine(sib, "x")
    res = run("kin", write(tmp_path, "me.json", me), write(tmp_path, "sib.json", sib))
    assert "聞く赤い点 2" in res.stdout
