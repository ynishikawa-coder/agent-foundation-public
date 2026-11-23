"""決まりの置き場を照らす試験（tests/test_rule_holes.py が「消しても赤にならない文」と名指した物を守る）。照らしの正本は
tests/test_kimari_okiba.py（節の中の要の語と、kaku.py から読む名）。"""
from pathlib import Path

from test_kimari_okiba import RYOU, 量の上限の名, 量の上限の外れ

ROOT = Path(__file__).resolve().parent.parent


def test_量の上限は_1_か所で_使う側の_CLAUDE_md_は起動の_hook_が照らし数も道具も写さない():
    """細目の「量の上限」の節（PR #49 で書き換わった）を、節の中の要の語と動く物の名で照らす。"""
    assert 量の上限の外れ((ROOT / RYOU).read_text(encoding="utf-8"), 量の上限の名()) == []
