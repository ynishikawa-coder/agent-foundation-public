"""出す前の文の口（guard.py --text）は、照らしていない物が在れば CI でも緑（✅）と言わない（注入の試験）。

前の形: 顧客の語が環境に無いと CI でもその照合を飛ばし、「✅ 置かない物 0」と言って exit 0。表に語が 0 でも同じ。
今の形: 照らしていない物を名指し、✅ と言わない。exit は 0 のまま（守りの hook pr_text は 0 以外を止めるので、
3・1 にすると顧客の語の無い窓の出す前の文が皆止まる＝新しく止める物になる。hook の受けを直すのは別の行）。
当たりは顧客の語が無くても出して赤（照らせた物の当たりを隠さない）。
"""
import pytest

from public_guard_box import CLEAN_CUSTOMER, PHONE, cli


def _text(tmp_path, env, body="作り物の確かめを足した\n", words="作り物ノ禁句\n"):
    f = tmp_path / "body.md"
    f.write_text(body, encoding="utf-8")
    args = ["--text", "PR の本文=%s" % f]
    if words is not None:
        w = tmp_path / "deny.txt"
        w.write_text(words, encoding="utf-8")
        args += ["--deny-words-file", str(w)]
    return cli(None, *args, env_extra=env, cwd=tmp_path)


@pytest.mark.parametrize("ci", [{"GITHUB_ACTIONS": "true"}, {}])
def test_注入_顧客の語が無ければ_CI_でも緑と言わない(tmp_path, ci):
    r = _text(tmp_path, ci)
    assert r.returncode == 0 and "✅" not in r.stdout, r.stdout
    assert "照らしていない" in r.stdout and "顧客の語" in r.stdout, r.stdout
    r = _text(tmp_path, {**ci, "AF_DENY_WORDS": CLEAN_CUSTOMER})
    assert r.returncode == 0 and "✅" in r.stdout and "照らしていない" not in r.stdout, r.stdout


def test_注入_表に語が0なら緑と言わない(tmp_path):
    r = _text(tmp_path, {"GITHUB_ACTIONS": "true", "AF_DENY_WORDS": CLEAN_CUSTOMER}, words="# 空\n")
    assert r.returncode == 0 and "✅" not in r.stdout and "語が 0" in r.stdout, r.stdout


def test_顧客の語が無くても照らせた物の当たりは赤(tmp_path):
    r = _text(tmp_path, {"GITHUB_ACTIONS": "true"}, body="電話 %s\n" % PHONE)
    assert r.returncode == 1 and "PR の本文: 電話番号" in r.stdout, r.stdout
