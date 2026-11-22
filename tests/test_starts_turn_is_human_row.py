"""番（ターン）を切る名 starts_turn（plugin session-watch がこの名で直に読む）は、人の行の見分けの正本 guard_common.is_human_row と同じ答えを返すという約束。
starts_turn に別の見分け（is_owner_row など）を写して戻すと、知らせ・要約・中断の行で答えがずれて赤。"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "plugins/guard/scripts"))
import guard_common as G  # noqa: E402


@pytest.mark.parametrize("row", [
    {"type": "user", "message": {"content": "頼み"}},
    {"type": "user", "promptSource": "system", "message": {"content": "知らせ"}},
    {"type": "user", "isCompactSummary": True, "message": {"content": "要約"}},
    {"type": "user", "message": {"content": "[Request interrupted by user]"}},
])
def test_starts_turn_は人の行の正本と同じ(row):
    assert G.starts_turn(row) == G.is_human_row(row)
