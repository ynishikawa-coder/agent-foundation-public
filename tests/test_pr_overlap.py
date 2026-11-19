"""scripts/pr_overlap.py: 並ぶ PR が同じ file の同じ行の辺りを書き換えた時だけ名指しで知らせ、止めないか。"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "scripts" / "pr_overlap.py"
spec = importlib.util.spec_from_file_location("pr_overlap", TOOL)
po = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(po)

MINE = {"plugins/core/細目.md": "@@ -20,4 +20,5 @@ 節\n-古い\n+新しい\n", "README.md": "@@ -1,2 +1,2 @@\n"}


def test_同じ節を書き換える他の_PR_を名指す():
    others = {"#7": {"plugins/core/細目.md": "@@ -22,3 +22,3 @@\n"}, "#8": {"plugins/core/細目.md": "@@ -200,2 +200,3 @@\n"},
              "#9": {"docs/x.md": "@@ -20,4 +20,4 @@\n"}}
    hits = po.overlaps(MINE, others)
    assert [(h[0], h[1]) for h in hits] == [("#7", "plugins/core/細目.md")]


def test_離れた所と別の_file_は知らせない():
    assert po.overlaps(MINE, {"#8": {"plugins/core/細目.md": "@@ -40,2 +40,3 @@\n"}}) == []


def test_重なっても止めず_材料が無くても止めない(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(MINE), encoding="utf-8")
    b.write_text(json.dumps({"#7": {"plugins/core/細目.md": "@@ -21,1 +21,1 @@\n"}}), encoding="utf-8")
    res = subprocess.run([sys.executable, "-B", str(TOOL), "--self", str(a), "--others", str(b)], capture_output=True, text=True)
    assert res.returncode == 0 and "#7 も plugins/core/細目.md" in res.stdout
    res = subprocess.run([sys.executable, "-B", str(TOOL)], capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin"})
    assert res.returncode == 3 and "見ていない" in res.stdout  # 材料が無い時は緑の 0 でなく「見ていない」の 3
