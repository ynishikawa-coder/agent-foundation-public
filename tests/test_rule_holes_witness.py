"""決まりの文の穴の照らし（tests/test_rule_holes.py）が、回っていない試験を「赤になった」に数えないか（注入の試験）。

前の形: 決まりの試験を直に呼び except BaseException で受けたので、skip・xfail・道具が無くて落ちる試験も
「文を消したら赤になった」に数え、その文は穴に出なかった。fixture を取る試験は黙って照らしから外れた（原因の台帳 束 F1）。
今の形: 赤に数えるのは普通の例外と pytest.fail だけ。元の文で通らない試験は照らしに使わず名を残す。文を消した回で
飛んだら止める。tmp_path・monkeypatch・capsys と parametrize の値は用意して回す。
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("af_rule_holes_for_witness", ROOT / "tests" / "test_rule_holes.py")
holes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(holes)
REL = "plugins/core/細目.md"
TEXT = "- 作り物の決まり。\n"


def _with(monkeypatch, f):
    monkeypatch.setattr(holes, "_決まりの試験", lambda: {REL: [(f, {})]})


def test_注入_文を消した回で飛ぶ試験は赤に数えず止める(monkeypatch):
    def reader():
        pytest.skip("作り物の飛ばし")
    _with(monkeypatch, reader)
    with pytest.raises(AssertionError, match="飛んだ"):
        holes.穴(REL, TEXT)


def test_注入_xfail_も赤に数えず止める(monkeypatch):
    def reader():
        pytest.xfail("作り物")
    _with(monkeypatch, reader)
    with pytest.raises(AssertionError, match="飛んだ"):
        holes.穴(REL, TEXT)


def test_文を照らす試験の赤は赤に数える(monkeypatch):
    def reader():
        assert "作り物の決まり" in (ROOT / REL).read_text(encoding="utf-8")
    _with(monkeypatch, reader)
    assert holes.穴(REL, TEXT) == []


def test_fixture_と_parametrize_を用意して回す():
    @pytest.mark.parametrize("a,b", [(1, 2), (3, 4)])
    def t(tmp_path, monkeypatch, capsys, a, b):
        pass
    assert holes._呼び方(t) == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]

    def u(request):
        pass
    assert holes._呼び方(u) is None
