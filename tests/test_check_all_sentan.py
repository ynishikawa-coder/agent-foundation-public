"""check_all の最後の行は回した先端を添え、git に無い file や commit していない変更がある時は「+未 commit」を付ける。

git ls-files で道具を拾う試験は git に無い file を見ないので、commit 前に回した緑は先端の結果と言えない（#78 で起きた）。
"""
import pathlib
import subprocess

from entry_box import copy_entry

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _check_all_の最後の行(tmp_path, dirty):
    """check_all.sh を tmp の repo に写し、検査の中身は空にして最後の行だけを見る。"""
    copy_entry(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_ok.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    g = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    g("init", "-q")
    g("add", "-A")
    g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "t")
    if dirty:
        (tmp_path / "tests/test_new.py").write_text("def test_new():\n    pass\n", encoding="utf-8")
    out = subprocess.run(["bash", "scripts/check_all.sh"], cwd=tmp_path, capture_output=True, text=True)
    head = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    return out.stdout.strip().splitlines()[-1], head


def test_check_allの結果は回した先端を添える(tmp_path):
    last, head = _check_all_の最後の行(tmp_path, dirty=False)
    assert last.startswith("check_all: 緑") and last.endswith(f"@{head}")


def test_git_に無いfileがあると未commitの印が付く(tmp_path):
    last, head = _check_all_の最後の行(tmp_path, dirty=True)
    assert f"@{head}+未 commit" in last
