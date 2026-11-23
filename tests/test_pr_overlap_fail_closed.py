"""scripts/pr_overlap.py: 取れない物（2 頁目からの PR・GitHub が返さない patch・上限に当たった file の一覧）を「無い」と読まないか。

意図: 開いている他の PR との重なりを、取れた分だけで「重なりは無い」と言わずに名指す。
課題: 開いた PR を 1 頁（100 本）だけ取り、101 本目からの重なりを見なかった。patch の無い file を空の差分と読み、
compare の file の上限 300 も照らさず、重なりを見落とした。
原因: 取れない・欠けた応答を既定で「重なりが無い」へ倒していた（既定で通す）。
作り物の API 応答をわざと入れ、重なりを名指すか exit 3（見ていない）で終える事を確かめる注入の試験。
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "pr_overlap.py"
spec = importlib.util.spec_from_file_location("af_pr_overlap_fail_closed", TOOL)
po = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(po)

TIP = "t" * 40
HUNK = "@@ -10,2 +10,3 @@\n a\n+b\n c\n"


def page_of(url):
    return int(url.rsplit("&page=", 1)[1]) if "&page=" in url else 1     # 1 頁目は頁の印なし


def fake_api(monkeypatch, opened, compares):
    """作り物の GitHub: opened は開いた PR の並び、compares は {head の sha: compare の files}。頁は page= で切る。"""
    def get(url, _token):
        if "/pulls?state=open" in url:
            page = page_of(url)
            return opened[(page - 1) * 100:page * 100]
        if url.endswith("/pulls/1"):
            return {"base": {"ref": "main"}, "head": {"sha": "me"}}
        if "/branches/main" in url:
            return {"commit": {"sha": TIP}}
        if "/compare/" in url:
            head = url.rsplit("...", 1)[1]
            return {"merge_base_commit": {"sha": TIP}, "files": compares[head]}
        raise AssertionError(url)
    monkeypatch.setattr(po, "_get", get)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def pr(n):
    return {"number": n, "head": {"sha": f"h{n}", "ref": f"b{n}"}, "base": {"ref": "main"}}


def test_101_本目の_PR_の重なりを名指す(monkeypatch, capsys):
    opened = [pr(n) for n in range(2, 103)]          # 101 本（2 頁目に #102）
    compares = {f"h{n}": [{"filename": "z.md", "patch": HUNK, "changes": 1}] for n in range(2, 102)}
    compares["h102"] = [{"filename": "a.md", "patch": HUNK, "changes": 1}]
    compares["me"] = [{"filename": "a.md", "patch": HUNK, "changes": 1}]
    fake_api(monkeypatch, opened, compares)
    assert po.main(["--repo", "o/r", "--pr", "1"]) == 0
    out = capsys.readouterr().out
    assert "#102 も a.md" in out and "重なる PR は無い" not in out, out


def test_patch_の無い_file_を空の差分と読まず重なりに数える(monkeypatch, capsys):
    compares = {"h2": [{"filename": "a.bin", "changes": 5}],          # GitHub が patch を返さない
                "me": [{"filename": "a.bin", "patch": "@@ -900,1 +900,1 @@\n-x\n+y\n", "changes": 2}]}
    fake_api(monkeypatch, [pr(2)], compares)
    assert po.main(["--repo", "o/r", "--pr", "1"]) == 0
    out = capsys.readouterr().out
    assert "#2 も a.bin" in out and "重なる PR は無い" not in out, out


def test_中身の変わらない名の付け替えは重なりに数えない():
    assert po._patch({"filename": "a.md", "changes": 0}) == ""
    assert po._patch({"filename": "a.md", "changes": 3}) is None


def test_compare_の_file_が上限_300_に当たれば見ていない(monkeypatch, capsys):
    many = [{"filename": f"f{i}.md", "patch": HUNK, "changes": 1} for i in range(300)]
    fake_api(monkeypatch, [pr(2)], {"h2": many, "me": [{"filename": "a.md", "patch": HUNK, "changes": 1}]})
    assert po.main(["--repo", "o/r", "--pr", "1"]) == 3
    out = capsys.readouterr().out
    assert "見ていない" in out and "300" in out and "重なる PR は無い" not in out, out


def test_PR_の_file_の一覧は頁を全部取り_上限に当たれば読めないと言う(monkeypatch):
    def get(url, _token):
        if "/pulls?state=open" in url:
            return [pr(2)] if page_of(url) == 1 else []
        page = page_of(url)
        return [{"filename": f"p{page}-{i}.md"} for i in range(100)]   # 満ちた頁が続く
    monkeypatch.setattr(po, "_get", get)
    try:
        po.open_files("o/r", "x")
    except OSError as e:
        assert "3000" in str(e)
    else:
        raise AssertionError("上限に当たった一覧を全部と読んだ")


def test_PR_の_file_の一覧の_2_頁目の_file_も宣言と照らす(monkeypatch, capsys):
    def get(url, _token):
        if "/pulls?state=open" in url:
            return [pr(2)] if page_of(url) == 1 else []
        if page_of(url) == 1:
            return [{"filename": f"x{i}.md"} for i in range(100)]
        return [{"filename": "a.md"}]
    monkeypatch.setattr(po, "_get", get)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    assert po.main(["--repo", "o/r", "--files", "a.md"]) == 1
    assert "a.md を書き換えている" in capsys.readouterr().out
