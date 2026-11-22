"""1 行 1 件の JSON（会話ログ・gh の --jq の出力）を改行だけで割って読むか（注入の試験）。

意図: 見張りが会話ログの道具の呼び出しを 1 件も落とさずに読み、引き継いだ窓・答えた問いを正しく数える。
課題: 見張りの読み口が、JSON の文字列の中に U+2028 などを含む行を壊れ行として黙って捨てていた（原因の台帳の行）。
原因: 1 行 1 件の JSON を str.splitlines() で割っていた。splitlines() は改行のほか U+2028・U+2029・U+0085 などでも割り、
JSON の文字列の中にそのまま書かれたそれらの字を含む行を壊れ行として捨てていた。
"""
import ast
import json
import subprocess
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
    assert list(G.iter_rows(path)) == rows
    assert list(G.iter_rows(path, tail_bytes=10_000)) == rows


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


# 走査から外す dir（repo の根からの名）。外す時はここに名と理由を書く。今は無い＝git が持つ *.py を全部照らす。
EXCLUDE_DIRS = ()


def _tracked_py(root):
    """git が持つ *.py を全部（外す dir だけを除く）。新しい dir に置いた読み口も走査に入る。"""
    out = subprocess.run(["git", "ls-files", "-z", "--", "*.py"], cwd=root, capture_output=True, text=True, check=True)
    paths = [p for p in out.stdout.split("\0") if p]
    assert paths, "git ls-files が *.py を 1 つも返さない（走査が空のまま緑にならないように止める）"
    return [root / p for p in paths if not any(p == d or p.startswith(d + "/") for d in EXCLUDE_DIRS)]


def _bad_readers(root):
    return ["%s:%d" % (path.relative_to(root), n) for path in _tracked_py(root) for n in _splitlines_feeding_json(path)]


def test_土台の道具は1行1件のJSONをsplitlinesで割らない():
    bad = _bad_readers(ROOT)
    assert not bad, "1 行 1 件の JSON は split('\\n') で割る（splitlines() は U+2028 などでも割る）: " + "、".join(bad)


@pytest.mark.parametrize("where", ["public-guard/zz_inj.py", "新しい場所/zz_inj.py", "tests/zz_inj.py"])
def test_走査はgitが持つどのdirの誤った読み口も拒む(tmp_path, where):
    """plugins/・scripts/ の外（repo の根の public-guard/・まだ無い dir・試験）に置いた誤った読み口も赤にする。"""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    inj = tmp_path / where
    inj.parent.mkdir(parents=True, exist_ok=True)
    inj.write_text("import json\ndef r(t):\n    return [json.loads(x) for x in t.splitlines()]\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("import json\ndef r(t):\n    return [json.loads(x) for x in t.split('\\n')]\n",
                                    encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    assert _bad_readers(tmp_path) == [where + ":3"]


def test_見張りの検査は作り物の誤った読み方を拒む(tmp_path):
    bad = tmp_path / "作り物.py"
    bad.write_text("import json\n"
                   "def a(t):\n    return [json.loads(x) for x in t.splitlines()]\n"
                   "def b(t):\n    for x in t.splitlines():\n        json.loads(x)\n", encoding="utf-8")
    assert _splitlines_feeding_json(bad) == [3, 5]
    good = tmp_path / "正しい.py"
    good.write_text("import json\ndef a(t):\n    return [json.loads(x) for x in t.split('\\n')]\n", encoding="utf-8")
    assert _splitlines_feeding_json(good) == []
