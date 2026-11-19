"""--pattern-skip は file 全体でなく、印 `public-guard: 形の見本` を書いた行の個人の情報の形だけを外す（注入の試験）。

前の形: pattern-skip に名指した file（土台では guard.py と tests/test_public_guard.py）は、中身も歴史も秘密・個人の
情報の形の照らしから丸ごと外れ、本物の鍵が入っても緑だった。今の形: 印の無い行は全部照らし、印の行でも秘密の形は照らす。
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


def test_注入_印を書いた_file_の印の無い行は赤(tmp_path):
    """印を 1 行でも書いた file は新しい形。印の無い行の個人の情報は赤（%r は改行を字にするので、行は file に分けて書く）。"""
    repo = make_repo(tmp_path / "r")
    commit(repo, {"pat.py": "EXAMPLE = %r\n# %s\n" % ("電話 " + PHONE, MARK)})
    r = cli(repo, "--range", "ALL", "--pattern-skip", "pat.py", env_extra=ENV)
    assert r.returncode == 1 and "pat.py: 電話番号" in r.stdout and "commit" in r.stdout, r.stdout


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


def test_土台の_skip_の_file_の形の行には皆印が在る():
    """ci.yml の pattern-skip の file で、個人の情報の形に当たる行は印の行だけ（印の無い行が当たれば CI が赤になる）。"""
    import workflow_reader as W
    ci = (guard.Path(guard.__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml")
    (call,) = [c for c in W.counted(ci.read_text(encoding="utf-8"), "") if c.check == "public-guard"]
    for rel in str(call.inputs["pattern-skip"]).split():
        text = (ci.parent.parent.parent / rel).read_text(encoding="utf-8")
        assert not guard.skipped_pattern_hits(rel, text), rel
