"""PR 本文の頭に記録の写し（書いた窓・検査・親窓）を置かない約束の注入の試験（2026-11-22 原因の台帳）。

前の形: 型の頭に `書いた窓:`・`検査:` を置き、窓が手で写した。直しの commit を足した窓が書き直さず、本文が commit の記録
（`Claude-Session:`）や CI の結果とずれた（使う側の PR で起きた）。今の形: 型の頭は `job:` だけ。書いた窓は
plugins/checker/scripts/pr_writer.py --writers が commit の記録から出し、別の目の照らし（guard の pr_text・合流の判定）は記録だけを読む。
"""
import re

from test_pr_writer import A, B, ROOT, body, repo_with, run


def test_型の頭に記録の写しの欄が無い():
    tpl = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    head = tpl.split("\n\n", 1)[0]
    assert not re.search(r"^\s*(?:書いた窓|検査|親窓)\s*[:：]", head, re.M), "型の頭に写しの欄が戻った: " + head
    # 注入: 前の型の頭を戻すと拾う
    old = "書いた窓: <id>\njob: x\n検査: 緑\n"
    assert re.search(r"^\s*(?:書いた窓|検査|親窓)\s*[:：]", old, re.M)


def test_写しの無い本文は_直しの往復で別の窓が_commit_しても緑(tmp_path):
    repo, head = repo_with(tmp_path, [A, B])
    code, out = run(repo, head, "job: 20261122-test\n\n## 何をどう変えたか\n")
    assert code == 0, out


def test_前の型の写しが残る本文は_形でないと赤(tmp_path):
    repo, head = repo_with(tmp_path, [A])
    assert run(repo, head, body("<session id>"))[0] == 1
