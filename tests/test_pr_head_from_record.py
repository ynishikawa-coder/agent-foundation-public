"""PR 本文の頭に記録の写し（書いた窓・検査・親窓）を置かない約束の注入の試験（2026-11-22 原因の台帳）。

前の形: 型の頭に `書いた窓:`・`検査:` を置き、窓が手で写した。直しの commit を足した窓が書き直さず、本文が commit の記録
（`Claude-Session:`）や CI の結果とずれた（使う側の PR で起きた）。今の形: 型の頭は `job:` だけ。書いた窓は
plugins/checker/scripts/pr_writer.py --writers が commit の記録から出し、別の目の照らし（guard の pr_text・合流の判定）は記録だけを読む。
"""
import re

from test_pr_writer import A, B, ROOT, body, repo_with, run


COPY_FIELD = re.compile(r"^\s*(?:書いた窓|検査|親窓)\s*[:：]", re.M)


def copy_fields_in_head(tpl_path):
    """型の file の頭の塊（最初の空行まで）に在る記録の写しの欄の行を返す。"""
    head = tpl_path.read_text(encoding="utf-8").split("\n\n", 1)[0]
    return [m.group(0).strip() for m in COPY_FIELD.finditer(head)]


def test_型の頭に記録の写しの欄が無い(tmp_path):
    real = ROOT / ".github" / "pull_request_template.md"
    assert copy_fields_in_head(real) == [], "型の頭に写しの欄が戻った"
    # 注入: 本物の型の file に前の頭を書き戻した作り物の型で、同じ照らしが赤になる
    fake = tmp_path / "pull_request_template.md"
    fake.write_text("書いた窓: <session id>\n" + real.read_text(encoding="utf-8").replace("\n\n", "\n検査: <緑>\n\n", 1),
                    encoding="utf-8")
    assert len(copy_fields_in_head(fake)) == 2


def test_写しの無い本文は_直しの往復で別の窓が_commit_しても緑(tmp_path):
    repo, head = repo_with(tmp_path, [A, B])
    code, out = run(repo, head, "job: 20261122-test\n\n## 何をどう変えたか\n")
    assert code == 0, out


def test_前の型の写しが残る本文は_形でないと赤(tmp_path):
    repo, head = repo_with(tmp_path, [A])
    assert run(repo, head, body("<session id>"))[0] == 1
