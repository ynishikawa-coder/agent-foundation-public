"""guard_common.parse_shell（PR #70・#77・#82 で同じ名と同じ意味の shell の読み口）: 走る命令の argv と、読み切れなかった形の
名指しを返すか。読み切れない形は呼ぶ側が安全な側に倒す（注入の試験・入力は全部作り物）。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "guard" / "scripts"))
sys.dont_write_bytecode = True
import guard_common as G  # noqa: E402

KNOWN = [
    ("素の命令", "node /x/check.mjs p --run-prior", [["node", "/x/check.mjs", "p", "--run-prior"]]),
    ("前置きを外す", "A=1 sudo -u a env B=2 time nice -n 5 nohup python3 t.py", [["python3", "t.py"]]),
    ("timeout と stdbuf", "timeout -s KILL 5 stdbuf -oL python3 t.py", [["python3", "t.py"]]),
    ("向け替えを除く", "python3 t.py < q.json > out.json 2>&1", [["python3", "t.py"]]),
    ("管と ; と改行で分ける", "cat q | python3 t.py; ls\nnode a.mjs",
     [["cat", "q"], ["python3", "t.py"], ["ls"], ["node", "a.mjs"]]),
    ("bash -c の中へ降りる", "bash -lc 'cd /x; python3 t.py'", [["cd", "/x"], ["python3", "t.py"]]),
    ("eval の中へ降りる", "eval python3 t.py", [["python3", "t.py"]]),
    ("xargs を外す", "ls | xargs -n 1 python3 t.py", [["ls"], ["python3", "t.py"]]),
    ("ヒアドキュメントの本文は除く", "cat > n.md <<'EOF'\npython3 t.py\nEOF\nls", [["cat"], ["ls"]]),
    ("<<- の本文も除く", "cat <<-E\n\tpython3 t.py\n\tE", [["cat"]]),
    ("語の頭の # だけが注", "ls a#b # python3 t.py", [["ls", "a#b"]]),
    ("引用の中の $( は字", "echo 'a $(b)'", [["echo", "a $(b)"]]),
    ("行の継ぎ", "node a.mjs \\\n  --run-prior", [["node", "a.mjs", "--run-prior"]]),
    ("command -v は走らない", "command -v python3", []),
    ("台本の file を走らせる shell", "bash run.sh", [["bash", "run.sh"]]),
]


@pytest.mark.parametrize("name,cmd,runs", KNOWN, ids=[c[0] for c in KNOWN])
def test_読み切れる形は走る命令を返し名指しが無い(name, cmd, runs):
    assert G.parse_shell(cmd) == (runs, []), name


UNKNOWN = [
    ("$(…)", "x=$(python3 t.py)", "$(…)"),
    ("`…`", "x=`python3 t.py`", "$(…)"),
    ("二重引用の中の $(…)", 'echo "$(python3 t.py)"', "$(…)"),
    ("頭に変数", "$TOOL run", "頭に変数"),
    ("閉じていない引用", "echo 'a", "閉じていない引用"),
    ("関数の定義", "f() { python3 t.py; }", "括弧の組"),
    ("shell への管", "echo python3 t.py | bash", "標準入力"),
    ("ヒアドキュメントを shell へ", "bash <<EOF\npython3 t.py\nEOF", "標準入力"),
    ("find -exec", "find . -name x -exec python3 t.py {} +", "find -exec"),
    ("xargs で shell", "ls | xargs bash -c 'python3 t.py'", "xargs で shell"),
    ("表に無い前置き", "flock /tmp/l python3 t.py", "表に無い前置き"),
    ("-c の後の --", "bash -c -- 'python3 t.py'", "-c の後の --"),
    ("subshell の組", "(cd /x; python3 t.py)", "括弧の組"),
    ("&& の枝", "false && python3 t.py", "条件の枝"),
    ("|| の枝", "true || python3 t.py", "条件の枝"),
    ("制御の語", "if false; then python3 t.py; fi", "制御の語"),
    ("exit の後", "exit 0; python3 t.py", "exit"),
    ("exec の後", "exec ls; python3 t.py", "exit"),
    ("bash -c の中の枝", "bash -c 'false && python3 t.py'", "条件の枝"),
]


@pytest.mark.parametrize("name,cmd,named", UNKNOWN, ids=[c[0] for c in UNKNOWN])
def test_読み切れない形は名指す(name, cmd, named):
    _, unknowns = G.parse_shell(cmd)
    assert any(named in u for u in unknowns), (name, unknowns)


def test_読めない入力でも落ちない():
    for cmd in (None, "", "   ", ";;", "<<", "a <<", "\\"):
        runs, unknowns = G.parse_shell(cmd)
        assert isinstance(runs, list) and isinstance(unknowns, list)
