"""scripts/pr_shape.py: 構文で読めない試験の file を「試験が無い」と読まず赤にするか（注入の試験）。

原因の台帳: 読めない試験の file を空（試験が無い）と読み、移した試験を見落とした。PR では pytest が走らないので、
PR の形の照らしで赤にする。前の形（読めなければ飛ばす）に戻すと、下の試験はどれも赤になる。
"""
import pytest

from test_pr_shape_moves import _write, repo, run  # noqa: F401 — repo は fixture（作り物の repo と枝）


@pytest.mark.parametrize("tail", ["", "\n\ndef test_extra():\n    assert 1\n"])
def test_構文の誤りの在る新しい試験の_file_は赤(repo, tail):  # noqa: F811
    (repo / "tests" / "test_old.py").unlink()
    # git の似ている度合いの外（D+A）で、元の試験 test_a を持つ＝移した物。構文の誤りで読めないと前は見落とした
    _write(repo, "tests/test_moved.py", "def test_a():\n    assert 1\n\n\n" + "".join(
        f"def test_new{i}():\n    assert {i} == {i}  # 足した\n\n\n" for i in range(12)) + tail + "\n\ndef test_broken(:\n    pass\n")
    res = run(repo)
    assert res.returncode == 1 and "tests/test_moved.py: 試験の file を構文で読めない" in res.stdout, res.stdout


def test_構文の誤りの在る新しい試験の_file_は試験を移さなくても赤(repo):  # noqa: F811
    _write(repo, "tests/test_new_broken.py", "def test_x(:\n    pass\n")
    res = run(repo)
    assert res.returncode == 1 and "tests/test_new_broken.py: 試験の file を構文で読めない" in res.stdout, res.stdout
