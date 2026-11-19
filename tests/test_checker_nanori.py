"""チェック役: 判定の名乗り（1 行目の窓）が、verdict_form.py を回した本物の窓と同じかを照らす（注入の試験）。

起きた事: 書いた窓が立てた助手が、自分の手元の id から作った `session_…` で名乗って green を残し、別の窓の判定に見えた。
助手は立てた窓の環境（CLAUDE_CODE_REMOTE_SESSION_ID）を受け継ぐので、回した窓の id と照らせば作った名乗りは通らない。
"""
import pytest

from test_checker_eye_and_cards import GREEN, run

ARGS = ("--writer", "session_WRITER01", "--head", "0123456789ab")


def test_本物のレビューの窓が自分の_id_で名乗れば通る(tmp_path):
    res = run(tmp_path, GREEN, *ARGS, me="cse_REVIEW01")
    assert res.returncode == 0, res.stdout + res.stderr


def test_書いた窓の助手が作った_id_で名乗ると誤り(tmp_path):
    made = GREEN.replace("session_REVIEW01", "session_207e09a5ffad599bb72b247d1941aef1", 1)
    res = run(tmp_path, made, *ARGS, me="cse_WRITER01")
    assert res.returncode == 1
    assert "この命令を回した窓 session_WRITER01 と違う" in res.stdout
    assert "書いた窓 session_WRITER01 と同じ" in res.stdout


def test_別の窓が他の窓の名を騙っても誤り(tmp_path):
    res = run(tmp_path, GREEN, *ARGS, me="cse_OTHER01")
    assert res.returncode == 1 and "回した窓 session_OTHER01 と違う" in res.stdout


@pytest.mark.parametrize("me", [None, "", "session_REVIEW01", "cse_", "cse_a-b"])
def test_回した窓が分からない時は形を通さない(tmp_path, me):
    res = run(tmp_path, GREEN, *ARGS, me=me)
    assert res.returncode == 2 and "CLAUDE_CODE_REMOTE_SESSION_ID" in res.stderr, me


def test_引き継ぎで書いた窓が_2_つの時_後の書き手の判定も誤り(tmp_path):
    """書いた窓を 1 つ目だけ照らすと、引き継いだ後の書き手が自分の PR に判定を付けられた（原因の台帳の行）。"""
    two = ("--writer", "session_WRITER01,session_REVIEW01", "--head", "0123456789ab")
    res = run(tmp_path, GREEN, *two, me="cse_REVIEW01")
    assert res.returncode == 1
    assert "書いた窓とレビューした窓が同じ" in res.stdout
    assert "書いた窓 session_REVIEW01 と同じ" in res.stdout


def test_書いた窓の組の外の窓の判定は通る(tmp_path):
    two = ("--writer", "session_WRITER01, session_WRITER02", "--head", "0123456789ab")
    res = run(tmp_path, GREEN, *two, me="cse_REVIEW01")
    assert res.returncode == 0, res.stdout + res.stderr


@pytest.mark.parametrize("writer", [",", " , ", ",,"])
def test_書いた窓の組が空なら形を通さない(tmp_path, writer):
    """`,` だけの --writer で組が空になり、別の目の照らしが全部飛んで通っていた戻り（レビューの所見）。"""
    res = run(tmp_path, GREEN, "--writer", writer, "--head", "0123456789ab", me="cse_REVIEW01")
    assert res.returncode == 2 and "--writer" in res.stderr, writer
