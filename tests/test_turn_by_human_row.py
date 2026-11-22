"""番（ターン）は人が打った行だけで切る（正本 guard_common.is_human_row・session-watch が読む名は starts_turn）という約束を、guard の離席の守りで照らす。
別の窓の知らせ・仕組みの知らせ・要約の行を「オーナーが戻った」と見る形（is_owner_row を直に使う形）に戻すと赤。"""
import pytest

from test_guard import DROP, append, away_log, bash, denied, env, human  # noqa: F401  env は fixture


@pytest.mark.parametrize("row", [
    {"origin": {"kind": "session"}},             # 別の窓の send_message で届いた行
    {"promptSource": "system"},                  # 仕組みの知らせ
    {"isCompactSummary": True},                  # 文脈を詰めた後の要約の行
])
def test_離席の後に知らせや要約の行が来ても戻ったと見ない(env, tmp_path, row):
    tpath = away_log(env, tmp_path)
    append(tpath, dict(human("子の窓の返事", ts="2999-01-01T00:00:00Z"), **row))
    assert denied(env, bash(DROP, tpath=tpath))


def test_離席の後に人が打てば戻ったと見る(env, tmp_path):
    tpath = away_log(env, tmp_path)
    append(tpath, dict(human("戻りました", ts="2999-01-01T00:00:00Z"), origin={"kind": "human"}))
    assert not denied(env, bash(DROP, tpath=tpath))


def test_starts_turn_は人の行の正本と同じ():
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "plugins/guard/scripts"))
    import guard_common as G
    for row in ({"type": "user", "message": {"content": "頼み"}},
                {"type": "user", "promptSource": "system", "message": {"content": "知らせ"}},
                {"type": "user", "isCompactSummary": True, "message": {"content": "要約"}},
                {"type": "user", "message": {"content": "[Request interrupted by user]"}}):
        assert G.starts_turn(row) == G.is_human_row(row)
