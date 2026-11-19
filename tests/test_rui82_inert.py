"""注入: 「読むだけと名乗る命令が、option・設定・前の代入で別の命令を走らせる・file へ書く」形を、守りが止めるか。

PR #91 のレビュー（先端 967e51d）が red にした原因: 読むだけの証（cmd_read.inert）を命令の名の表で決めていたので、
名が読むだけでも option で他の命令を走らせる形（git -c diff.external=… diff・GIT_EXTERNAL_DIFF=… git diff・
git grep -O…・rg --pre・sort --compress-program）と file へ書く形（sort --output・git diff --output・tree -o）を
読むだけとして通した。今は名＋使った option が全部「読むだけと分かっている物の集合」に入る時だけ証す。
直す前の版では、下の STOP はどれも通った。入力は全部作り物。
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))

import cmd_read  # noqa: E402
import irreversible  # noqa: E402
import paid_upstream  # noqa: E402
import spec_gate  # noqa: E402

G = "skills/spec-doc/" + "check_spec" + "_doc.py"
L = "--" + "lock"
RUN = f"python3 {G} d {L}"
KEY = "OPENAI" + "_API_KEY"


def _forms(run):
    """読むだけの名の下で run を走らせる形（レビューが確かめた 7 形と、同じ類の形）。"""
    return [
        f"git -c diff.external='{run}' diff",
        f"GIT_EXTERNAL_DIFF='{run}' git diff",
        f"git -c core.fsmonitor='{run}' status",
        f"git grep -O'{run}' b",
        f"git fetch --upload-pack='{run}; git-upload-pack' .",
        f"rg --pre '{run}' b a",
        f"sort --compress-program='{run}' a",
        f"git --exec-path=/x -c alias.l='!{run}' log",
        f"PAGER='{run}' git log",
        f"env GIT_PAGER='{run}' git log",
        f"sudo -u x git -c diff.external='{run}' diff",
    ]


INERT_NO = _forms("x") + [
    "sort --output=f a", "sort -o f a", "git diff --output=f", "tree -o f", "rg -z x", "uniq a b",
    "git add .", "git commit -m x", "git fetch origin", "git --git-dir=/other log", "git --work-tree=/x status",
    "./cat x", "yq -i '.a=1' f", "less -o log f", "git cat-file --textconv HEAD:a", "git log --show-signature",
]
INERT_YES = [
    "git log --oneline -5", "git diff --stat origin/main...HEAD", "git status -sb", "git -C x log -p",
    "git grep -n x", "git show HEAD:a.py", "git branch -a", "rg -n x tests", "grep -rn --include=*.py x .",
    "cat a | grep -n foo | head -n 20", "sort -u f | uniq -c", "ls -la", "sed -n 1,5p f", "echo hi", "wc -l a b",
]


@pytest.mark.parametrize("cmd", INERT_NO)
def test_inert_は名が読むだけでも_option_設定_前の代入で走らせる形を証さない(cmd):
    assert not cmd_read.inert(cmd), cmd


@pytest.mark.parametrize("cmd", INERT_YES)
def test_inert_は読むだけの_option_だけの形を証す(cmd):
    assert cmd_read.inert(cmd), cmd


def test_inert_の正本は知らない_option_を証さない():
    """option の集合に無い物は、名が読むだけでも 1 つで証せない（表の外は止める側）。"""
    assert cmd_read.inert("git log --oneline")
    assert not cmd_read.inert("git log --oneline --作り物の知らない旗")
    assert not cmd_read.inert("cat -Z a")


@pytest.mark.parametrize("cmd", _forms(RUN))
def test_spec_gate_は読むだけの名の下で_gate_を_lock_で走らせる形を止める(cmd):
    assert spec_gate.hit(cmd), cmd


@pytest.fixture
def outside_scratch(monkeypatch, tmp_path):
    other = tmp_path / "別の一時の置き場"
    other.mkdir()
    monkeypatch.setattr(irreversible.tempfile, "gettempdir", lambda: str(other))
    return tmp_path


@pytest.mark.parametrize("cmd", _forms("dropdb prod"))
def test_irreversible_は読むだけの名の下で消す命令を走らせる形を止める(cmd, outside_scratch):
    assert irreversible.bash_verbs(cmd, str(outside_scratch)), cmd


def _git_repo(path):
    path.mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", *a], cwd=path, check=True, capture_output=True)
    run("init", "-q")
    (path / "src").mkdir()
    (path / "src" / "real.py").write_text("KEY = '%s'\n" % KEY, encoding="utf-8")
    return path


@pytest.mark.parametrize("cmd", [
    "sort --output=tests/test_llm.py src/real.py",
    "sort -o tests/test_llm.py src/real.py",
    "git diff --no-index --output=tests/test_llm.py /dev/null src/real.py",
])
def test_paid_upstream_は読むだけの名で試験の_file_へ書く形を止める(tmp_path, cmd):
    repo = _git_repo(tmp_path / "repo")
    data = {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": cmd}}
    assert "有料の上流" in paid_upstream.check(data, {}), cmd


def test_守りの命令の読み手は_cmd_read_の_1_本():
    """守り（plugins/guard/scripts）で命令を字句に割るのは cmd_read だけ（shlex.split で別に読む守りを足すと赤）。"""
    scripts = ROOT / "plugins" / "guard" / "scripts"
    others = [p.name for p in scripts.glob("*.py")
              if p.name != "cmd_read.py" and "shlex.split" in p.read_text(encoding="utf-8")]
    assert others == [], others
