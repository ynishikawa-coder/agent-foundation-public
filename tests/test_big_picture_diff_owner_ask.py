"""全体の絵と実物の差を照らした時の直し方が、作り方のずれをオーナーへ聞かない事の注入の試験。

意図: 作り方のずれは AI が合意した絵どおりに直し、設計そのものを変える時だけオーナーと合意し直す（核 §4・skill big-picture）。
課題: 照らし（compare）の差ありの文が「絵と実物のどちらに合わせるかをオーナーに決めてもらう」と、作り方のずれまで
オーナーへ選ばせる形のまま残っていた。
原因: 照らしを合流の条件から外した時に、skill の使い方の文だけを直し、道具の出す文を直さなかった（正本が 2 つあった）。
ここでは、わざと絵と違う実物を作り、差ありの文が作り方のずれを AI が直すと言い、合意し直す時は前提の 2 行を先に見せると言う事を見る。
入力は全部作り物。
"""
from test_big_picture import DODAI, _drop_box, actual_from, agreed, run, write


def test_差ありの文は作り方のずれをオーナーに選ばせない(tmp_path):
    """意図: 作り方のずれで人を止めない。課題: 差ありの文がどちらに合わせるかをオーナーに決めてもらうと言っていた。"""
    x = actual_from(agreed())
    _drop_box(x)
    r = run("compare", DODAI, write(tmp_path, "x.json", x))
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "どちらに合わせるか" not in out and "オーナーに決めてもらう" not in out
    assert "AI が" in out and "絵どおりに直す" in out
    assert "「具体例:」「判断の物差し:」" in out
