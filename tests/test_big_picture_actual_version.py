"""実物の絵は版（meta.version）を持たなくても照らせるか。合意の絵は版が要るまま（注入の試験）。

意図: レビューの窓が意味の無い版を手で書かずに実物の絵を照らせるようにする（実物がどの先端から描かれたかは drawn_from が持つ）。
課題: レビューの窓が意味の無い版を手で書かないと照らせなかった（原因の台帳の行）。
原因: check が実物の絵にも版を求めていた。
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_bp_base_ver", Path(__file__).resolve().parent / "test_big_picture.py")
_b = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_b)


def test_版の無い実物とも照らせる(tmp_path):
    x = _b.actual_from(_b.agreed())
    x["meta"].pop("version", None)
    res = _b.run("compare", _b.write(tmp_path, "合意.json", _b.agreed()), _b.write(tmp_path, "実物.json", x))
    assert res.returncode == 0, res.stdout + res.stderr


def test_版の無い合意の絵は形の誤り(tmp_path):
    a = _b.agreed()
    a["meta"].pop("version")
    res = _b.run("check", _b.write(tmp_path, "合意.json", a))
    assert res.returncode == 1 and "meta.version" in res.stdout + res.stderr, res.stdout + res.stderr
