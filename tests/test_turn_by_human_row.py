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

