"""1 行 1 件の JSON（会話ログ・gh の --jq の出力）を改行だけで割って読むか（注入の試験）。

意図: 見張りが会話ログの道具の呼び出しを 1 件も落とさずに読み、引き継いだ窓・答えた問いを正しく数える。
課題: 見張りの読み口が、JSON の文字列の中に U+2028 などを含む行を壊れ行として黙って捨てていた（原因の台帳の行）。
原因: 1 行 1 件の JSON を str.splitlines() で割っていた。splitlines() は改行のほか U+2028・U+2029・U+0085 などでも割り、
JSON の文字列の中にそのまま書かれたそれらの字を含む行を壊れ行として捨てていた。
"""
import ast
import json
import sys
from pathlib import Path

import pytest

from test_guard import write_log

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))

import guard_common as G  # noqa: E402

# JSON の文字列の中にそのまま書けて、splitlines() が行の区切りと読む字
SEPARATORS = ["\u2028", "\u2029", "\u0085"]


@pytest.mark.parametrize("ch", SEPARATORS, ids=[hex(ord(c)) for c in SEPARATORS])
def test_会話ログの読み口は改行以外の区切り字を含む行を捨てない(tmp_path, ch):
    rows = [{"type": "user", "message": {"content": "作り物" + ch + "の頼み"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "作り物の返事"}]}}]
    path = write_log(tmp_path / "l.jsonl", rows)
    assert ch in Path(path).read_text(encoding="utf-8")       # 字はエスケープされずにそのまま書かれている
    log = G.read_log(path)
    assert log.rows == rows and log.broken == []


def _splitlines_feeding_json(path):
    """json.loads に splitlines() で割った行を渡す所（同じ式の中か、splitlines() を回す for の中）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []

    def splits(node):
        return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "splitlines"
                   for n in ast.walk(node))

    def loads(node):
        return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "loads"
                   for n in ast.walk(node))

    for node in ast.walk(tree):
        if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
            if any(splits(g.iter) for g in node.generators) and loads(node.elt):
                out.append(node.lineno)
        elif isinstance(node, ast.For) and splits(node.iter) and any(loads(b) for b in node.body):
            out.append(node.lineno)
    return sorted(out)


def test_土台の道具は1行1件のJSONをsplitlinesで割らない():
    bad = []
    for path in sorted((ROOT / "plugins").rglob("*.py")) + sorted((ROOT / "scripts").rglob("*.py")):
        bad += ["%s:%d" % (path.relative_to(ROOT), n) for n in _splitlines_feeding_json(path)]
    assert not bad, "1 行 1 件の JSON は split('\\n') で割る（splitlines() は U+2028 などでも割る）: " + "、".join(bad)


def test_見張りの検査は作り物の誤った読み方を拒む(tmp_path):
    bad = tmp_path / "作り物.py"
    bad.write_text("import json\n"
                   "def a(t):\n    return [json.loads(x) for x in t.splitlines()]\n"
                   "def b(t):\n    for x in t.splitlines():\n        json.loads(x)\n", encoding="utf-8")
    assert _splitlines_feeding_json(bad) == [3, 5]
    good = tmp_path / "正しい.py"
    good.write_text("import json\ndef a(t):\n    return [json.loads(x) for x in t.split('\\n')]\n", encoding="utf-8")
    assert _splitlines_feeding_json(good) == []
