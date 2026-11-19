"""注入: PR #81 のレビューが挙げた「読み手が知らない形」で gate を --lock で直に呼ぶ形を、spec_gate が止めるか。
直す前（読み手が段の頭を形の表で決めた版）はどれも通った。網を既定にして、読み手は読むだけの命令を通す側にだけ使う。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugins", "guard", "scripts"))
import spec_gate  # noqa: E402

G = "skills/spec-doc/" + "check_spec" + "_doc.py"
L = "--" + "lock"
STOP = [
    f"if true; then python3 {G} d {L}; fi",
    f"for i in 1; do python3 {G} d {L}; done",
    f"until true; do python3 {G} d {L}; done",
    f"! python3 {G} d {L}",
    f"coproc python3 {G} d {L}",
    f"timeout -s KILL 5 python3 {G} d {L}",
    f"timeout -k 1 5 python3 {G} d {L}",
    f"nice -n 5 python3 {G} d {L}",
    f"env -u X python3 {G} d {L}",
    f"env -S \"python3 {G} d {L}\"",
    f"python3 -W ignore {G} d {L}",
    f"python3 -X utf8 {G} d {L}",
    f"uv run --with x python {G} d {L}",
    f"echo \"python3 {G} d {L}\" | bash",
    f"bash <<<\"python3 {G} d {L}\"",
    f". /dev/stdin <<< 'python3 {G} d {L}'",
    f"fish -c 'python3 {G} d {L}'",
    f"busybox sh -c 'python3 {G} d {L}'",
    f"su -c 'python3 {G} d {L}'",
    f"script -c 'python3 {G} d {L}'",
    f"watch python3 {G} d {L}",
    f"ssh host python3 {G} d {L}",
    f"find . -name x.py -exec python3 {G} d {L} \\;",
    f"alias g='python3 {G}'; g d {L}",
    f"cat {G} | python3 - d {L}",
    f"python3 <(cat {G}) d {L}",
    f"perl -e 'system(\"python3 {G} d {L}\")'",
    f"node -e 'require(\"child_process\").execSync(\"python3 {G} d {L}\")'",
    f"cp {G} g.py; python3 g.py d {L}",
    "python3 \"check_spec\"'_doc.py' d --loc",
    "A=check_spec; B=_doc.py; python3 $A$B d --lo",
    f"python3 $(printf %s Y2hlY2s=) d {L}",
]
PASS = [
    f"python3 {G} d",
    f"python3 {G} d --verify-receipt r.json",
    f"python3 {G} d --stamp",
    f"grep -n -- {L} {G} | head",
    f"git log -p -- {G}",
    "python3 skills/spec-doc/seal.py d",
]


@pytest.mark.parametrize("cmd", STOP)
def test_知らない形でも止める(cmd):
    assert spec_gate.hit(cmd), cmd


@pytest.mark.parametrize("cmd", PASS)
def test_読むだけと_lock_無しは通す(cmd):
    assert spec_gate.hit(cmd) == "", cmd
