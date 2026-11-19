"""guard の道具の口は 1 つの正本に置く: Bash の命令を語に分ける口（parse_shell）と、道具の呼び出しが走ったかの口
（tool_use_ran）は guard_common.py だけに在り、guard の script のどれも同じ名の関数を 2 度定義しない（写しが 2 つの正本に
なるのを止める）。AST で読む＝字の当たりでなく定義を数える。
"""
import ast
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "guard" / "scripts"
ONE_SOURCE = {"parse_shell", "tool_use_ran"}          # guard_common.py だけが定義する口
OWNER = "guard_common.py"


def _top_functions(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _all_functions(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


SCRIPT_FILES = sorted(SCRIPTS.glob("*.py"))


def test_guard_の_script_が在る():
    assert any(p.name == OWNER for p in SCRIPT_FILES)


@pytest.mark.parametrize("path", SCRIPT_FILES, ids=lambda p: p.name)
def test_同じ名の関数を_2_度定義しない(path):
    names = _top_functions(path)
    dup = sorted({n for n in names if names.count(n) > 1})
    assert not dup, "%s が同じ名の関数を 2 度定義している: %s" % (path.name, dup)


@pytest.mark.parametrize("path", [p for p in SCRIPT_FILES if p.name != OWNER], ids=lambda p: p.name)
def test_parse_shell_と_tool_use_ran_は_guard_common_の外に定義しない(path):
    found = ONE_SOURCE & set(_all_functions(path))
    assert not found, "%s が %s を定義している（guard_common の口を呼ぶ）" % (path.name, sorted(found))


def test_正本は_guard_common_に_1_つずつ在る():
    names = _top_functions(SCRIPTS / OWNER)
    for n in ONE_SOURCE:
        assert names.count(n) == 1, n


def test_重なりの見張りは写しを見つける(tmp_path):
    """見張りの歯: 同じ名の 2 度の定義と、外の script の写しを実際に拾う（作り物の file で当てる）。"""
    dup = tmp_path / "dup.py"
    dup.write_text("def a():\n    pass\n\n\ndef a():\n    pass\n", encoding="utf-8")
    names = _top_functions(dup)
    assert names.count("a") == 2
    copy = tmp_path / "copy.py"
    copy.write_text("class X:\n    def parse_shell(self):\n        pass\n", encoding="utf-8")
    assert ONE_SOURCE & set(_all_functions(copy)) == {"parse_shell"}
