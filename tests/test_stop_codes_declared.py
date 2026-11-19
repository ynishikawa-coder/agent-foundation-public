"""照らしを足しても黙って止める物が増えない: 札は差し戻す（STOP）か知らせる（NOTE）のどちらか 1 つに宣言し、
止める物の宣言を変えた PR は変更の記録の断片に `止める物:` を書かないと赤（pr_shape・注入の試験）。"""
import re
import subprocess
import sys
from pathlib import Path

from test_pr_shape import BR, commit, git, run  # noqa: F401  作り物の repo と命令を共にする
from test_pr_shape import repo  # noqa: F401  fixture

ROOT = Path(__file__).resolve().parent.parent
SW = ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py"
EMIT = re.compile(r'found(?:\.append\(\(| \+= \[\()"([a-z_]+)"')


def declared(text):
    ns = {}
    for name in ("STOP_CODES", "NOTE_CODES"):
        m = re.search(r"^%s = (\(.*?\))$" % name, text, re.M)
        ns[name] = set(eval(m.group(1))) if m else set()   # noqa: S307  自分の repo の定数の字
    return ns["STOP_CODES"], ns["NOTE_CODES"]


def undeclared(text):
    stop, note = declared(text)
    return sorted((set(EMIT.findall(text)) - stop - note) | (stop & note))


def test_見張りが出す札は全部どちらか_1_つに宣言してある():
    assert undeclared(SW.read_text(encoding="utf-8")) == []


def test_宣言の無い札を足すと赤():
    text = SW.read_text(encoding="utf-8").replace('found.append(("idk"', 'found.append(("atarashii"', 1)
    assert undeclared(text) == ["atarashii"]


def test_止める物の宣言を変えた_PR_は断片に_止める物_が要る(repo):  # noqa: F811
    sw = repo / "plugins" / "session-watch" / "scripts"
    sw.mkdir(parents=True)
    (sw / "session_watch.py").write_text('STOP_CODES = ("a",)\n', encoding="utf-8")
    git(repo, "checkout", "-q", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "元の宣言")
    git(repo, "checkout", "-q", BR)
    git(repo, "merge", "-q", "main")
    (sw / "session_watch.py").write_text('STOP_CODES = ("a", "b")\n', encoding="utf-8")
    frag = repo / "CHANGELOG.d" / "20261119-sakumono.txt"
    frag.write_text("- 足した: 作り物\n", encoding="utf-8")
    commit(repo)
    res = run(repo)
    assert res.returncode == 1 and "止める物" in res.stdout
    frag.write_text("- 足した（止める物: AI の締めだけ）: 作り物\n", encoding="utf-8")
    commit(repo)
    res = run(repo)
    assert res.returncode == 0, res.stdout
