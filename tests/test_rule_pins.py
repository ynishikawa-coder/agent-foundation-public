"""決まりの文を文のまま照らす試験（tests/test_rule_holes.py が「消しても赤にならない文」と名指した物を守る）。"""
from pathlib import Path
from saimoku import 全文 as 細目の全文

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "core"


def test_量の上限は_1_か所で_使う側の_CLAUDE_md_は起動の_hook_が照らし数も道具も写さない():
    """細目の量の上限の文（PR #49 で書き換わった）を文のまま照らす（照らさない文を足すと test_rule_holes が赤）。"""
    saimoku = 細目の全文()
    assert "使う側の `CLAUDE.md` は起動の hook が照らして知らせる・使う側は数も道具も写さない）。" in saimoku
