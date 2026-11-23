"""scripts/pr_overlap.py: 長く動いていない開いた PR を、今いっしょに進む相手と同じに照らさないか。

意図: 重なりの知らせは、今いっしょに進む PR だけと照らし、本当にぶつかる相手を見えるようにする。
課題: 閉じ忘れの古い PR も開いている限り照らし、知らせがその重なりで埋まり、今の相手が見えなかった。
原因: 「開いている」を「今いっしょに進む」と同じに数えていた（動いているかを見る段が無かった）。
古い updated_at の PR をわざと入れ、重なりに数えず番号だけを名指す事を確かめる注入の試験。
"""
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "pr_overlap.py"
spec = importlib.util.spec_from_file_location("af_pr_overlap_stale", TOOL)
po = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(po)

TIP = "t" * 40
HUNK = "@@ -10,2 +10,3 @@\n a\n+b\n c\n"
NOW = datetime.now(timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def pr(n, days_ago=None):
    p = {"number": n, "head": {"sha": f"h{n}", "ref": f"b{n}"}, "base": {"ref": "main"}}
    if days_ago is not None:
        p["updated_at"] = iso(days_ago)
    return p


def fake_api(monkeypatch, opened, compares, files=None):
    def get(url, _token):
        if "/pulls?state=open" in url:
            return opened if "&page=" not in url else []
        if url.endswith("/pulls/1"):
            return {"base": {"ref": "main"}, "head": {"sha": "me"}}
        if "/branches/main" in url:
            return {"commit": {"sha": TIP}}
        if "/compare/" in url:
            return {"merge_base_commit": {"sha": TIP}, "files": compares[url.rsplit("...", 1)[1]]}
        if "/files" in url:
            n = url.split("/pulls/")[1].split("/")[0]
            return files[n] if "&page=" not in url else []
        raise AssertionError(url)
    monkeypatch.setattr(po, "_get", get)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def test_古い_PR_は進む相手に数えず_新しい物と無い物は数える():
    live, stale = po.moving([pr(2, 30), pr(3, 1), pr(4)], now=NOW)
    assert [p["number"] for p in live] == [3, 4]
    assert [p["number"] for p in stale] == [2]


def test_長く動いていない_PR_の重なりは知らせず_番号だけ名指す(monkeypatch, capsys):
    same = [{"filename": "a.md", "patch": HUNK, "changes": 1}]
    fake_api(monkeypatch, [pr(2, 60), pr(3, 0)], {"h2": same, "h3": same, "me": same})
    assert po.main(["--repo", "o/r", "--pr", "1"]) == 0
    out = capsys.readouterr().out
    assert "#3 も a.md" in out, out
    assert "#2 も a.md" not in out, out
    assert "動いていない開いた PR 1 本" in out and "#2" in out, out


def test_宣言の照らしも長く動いていない_PR_では列にしない(monkeypatch, capsys):
    fake_api(monkeypatch, [pr(2, 60)], {}, files={"2": [{"filename": "a.md"}]})
    assert po.main(["--repo", "o/r", "--files", "a.md"]) == 0
    out = capsys.readouterr().out
    assert "a.md を書き換えている" not in out and "#2" in out, out
