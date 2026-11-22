"""番（ターン）は人が打った行だけで切る（正本 guard_common.starts_turn）という約束を、guard の離席の守りで照らす。
別の窓の知らせ・仕組みの知らせ・要約の行を「オーナーが戻った」と見る形（is_owner_row を直に使う形）に戻すと赤。"""
import pytest

from test_guard import DROP, ask_result, bash, denied, env, hook, write_log  # noqa: F401  env は fixture


@pytest.mark.parametrize("row", [
    {"origin": {"kind": "session"}},             # 別の窓の send_message で届いた行
    {"promptSource": "system"},                  # 仕組みの知らせ
    {"isCompactSummary": True},                  # 文脈を詰めた後の要約の行
])
def test_離席の後に知らせや要約の行が来ても戻ったと見ない(env, tmp_path, row):
    hook(env, "post", ask_result())
    tpath = write_log(tmp_path / "t.jsonl", [dict({"type": "user", "timestamp": "2999-01-01T00:00:00Z",
                                                   "message": {"content": "子の窓の返事"}}, **row)])
    assert denied(env, bash(DROP, tpath=tpath))


def test_離席の後に人が打てば戻ったと見る(env, tmp_path):
    hook(env, "post", ask_result())
    tpath = write_log(tmp_path / "t.jsonl", [{"type": "user", "origin": {"kind": "human"},
                                              "timestamp": "2999-01-01T00:00:00Z", "message": {"content": "戻りました"}}])
    assert not denied(env, bash(DROP, tpath=tpath))
