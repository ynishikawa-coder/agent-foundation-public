"""--pattern-skip の 1 段目（注入の試験）。

前の形: 名指した file は秘密も個人の情報の形も file ごと外れた。1 段目: 個人の情報の形は file ごと外したまま
（使う側の見本の行を赤にしない）、秘密の形は file 全体で照らす。印の行だけに絞るのは 2 段目。
"""
import pytest

from public_guard_box import CLEAN_CUSTOMER, CUSTOMER, PHONE, TOKEN, cli, commit, guard, make_repo

MARK = guard.SKIP_MARK
ENV = {"AF_DENY_WORDS": CLEAN_CUSTOMER}


def _run(tmp_path, line, env=ENV):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"pat.py": "EXAMPLE = %r\n" % line})
    return cli(repo, "--range", "ALL", "--pattern-skip", "pat.py", env_extra=env)


def test_印の行の個人の情報の形だけ外れる(tmp_path):
    r = _run(tmp_path, "電話 %s  # %s" % (PHONE, MARK))
    assert r.returncode == 0, r.stdout


def test_1段目_印の無い_file_は前の形で形を_file_ごと外す(tmp_path):
    """印が 1 行も無い pattern-skip の file は、前の形のまま形を外す（使う側の CI を赤にしない）。"""
    r = _run(tmp_path, "電話 %s" % PHONE)
    assert r.returncode == 0, r.stdout


def test_1段目_印を書いた_file_でも個人の情報の形は_file_ごと外す(tmp_path):
    """1 段目は個人の情報の形を file ごと外す。印の無い行を赤にするのは 2 段目。"""
    repo = make_repo(tmp_path / "r")
    commit(repo, {"pat.py": "EXAMPLE = %r\n# %s\n" % ("電話 " + PHONE, MARK)})
    r = cli(repo, "--range", "ALL", "--pattern-skip", "pat.py", env_extra=ENV)
    assert r.returncode == 0 and "電話番号" not in r.stdout, r.stdout


@pytest.mark.parametrize("line, label", [
    ("鍵 %s  # %s" % (TOKEN, MARK), "GitHub のトークン"),   # 注入: 印の行でも秘密の形は外さない
])
def test_注入_印の行でも秘密の形は赤(tmp_path, line, label):
    r = _run(tmp_path, line)
    assert r.returncode == 1, r.stdout
    assert "pat.py: %s" % label in r.stdout and "commit" in r.stdout, r.stdout


def test_印の行でも顧客の語は外さない(tmp_path):
    r = _run(tmp_path, "%s  # %s" % (CUSTOMER, MARK), env={"AF_DENY_WORDS": CUSTOMER})
    assert r.returncode == 1 and "顧客の語" in r.stdout, r.stdout


def test_土台の_skip_の_file_に秘密の形は無い():
    """ci.yml の pattern-skip の file に秘密の形が無い（1 段目は秘密の形を file 全体で照らす）。"""
    import workflow_reader as W
    ci = (guard.Path(guard.__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml")
    (call,) = [c for c in W.counted(ci.read_text(encoding="utf-8"), "") if c.check == "public-guard"]
    for rel in str(call.inputs["pattern-skip"]).split():
        text = (ci.parent.parent.parent / rel).read_text(encoding="utf-8")
        assert not guard.skipped_pattern_hits(rel, text), rel
