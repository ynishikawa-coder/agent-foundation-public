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


def _is_splitlines(n):
    return isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "splitlines"


def _is_loads(n):
    f = n.func if isinstance(n, ast.Call) else None
    return (isinstance(f, ast.Attribute) and f.attr == "loads") or (isinstance(f, ast.Name) and f.id == "loads")


# 並びをそのまま渡す組み込み（割った行を包んでも割った行のまま）
PASS_THROUGH = {"list", "tuple", "reversed", "sorted", "iter", "next", "filter", "enumerate", "zip", "map", "set"}


def _names(target):
    return {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}


def _splitlines_feeding_json(path):
    """json.loads に splitlines() で割った字が届く所（json.loads の行の番号）。同じ式・for の中だけでなく、一度変数に置いた物、
    同じ file の別の関数へ引数で渡した物・別の関数が返した物も追う（遠回しの読み口も拒む）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    params = {name: [a.arg for a in f.args.posonlyargs + f.args.args] for name, f in funcs.items()}
    in_params = {name: set() for name in funcs}         # 割った字を受ける引数
    returns = set()                                      # 割った字を返す関数
    sinks = set()

    def scope_nodes(scope):
        """scope の中の節（中の関数の本体へは降りない＝別の scope で見る）。"""
        stack = list(ast.iter_child_nodes(scope))
        while stack:
            n = stack.pop()
            yield n
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                stack.extend(ast.iter_child_nodes(n))

    def tainted(e, names):
        """e が割った行（の並び・1 行・1 行に字の操作をした物）か。文の組み立て（% や join）・数え（len）は追わない。"""
        if _is_splitlines(e):
            return True
        if isinstance(e, ast.Name):
            return e.id in names
        if isinstance(e, (ast.Subscript, ast.Starred)):
            return tainted(e.value, names)
        if isinstance(e, ast.Call):
            f = e.func
            if isinstance(f, ast.Name):
                if f.id in returns:
                    return True
                return f.id in PASS_THROUGH and any(tainted(a, names) for a in e.args)
            return isinstance(f, ast.Attribute) and tainted(f.value, names)     # 1 行への字の操作（strip など）
        if isinstance(e, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
            return any(tainted(g.iter, names) for g in e.generators)
        if isinstance(e, ast.BoolOp):
            return any(tainted(v, names) for v in e.values)
        if isinstance(e, ast.IfExp):
            return tainted(e.body, names) or tainted(e.orelse, names)
        if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Add):
            return tainted(e.left, names) or tainted(e.right, names)
        if isinstance(e, (ast.Tuple, ast.List)):
            return any(tainted(v, names) for v in e.elts)
        return False

    def run(scope, names):
        changed = True
        while changed:
            changed = False
            for n in scope_nodes(scope):
                got = set()
                if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and n.value is not None \
                        and tainted(n.value, names):
                    for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                        got |= _names(t)
                elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)) and tainted(n.iter, names):
                    got |= _names(n.target)
                elif isinstance(n, (ast.With, ast.AsyncWith)):
                    for it in n.items:
                        if it.optional_vars is not None and tainted(it.context_expr, names):
                            got |= _names(it.optional_vars)
                if got - names:
                    names |= got
                    changed = True
        outer = False
        for n in scope_nodes(scope):
            if isinstance(n, ast.Call):
                if _is_loads(n) and any(tainted(a, names) for a in n.args):
                    sinks.add(n.lineno)
                name = n.func.id if isinstance(n.func, ast.Name) else (n.func.attr if isinstance(n.func, ast.Attribute) else "")
                if name in funcs:
                    hit = {params[name][i] for i, a in enumerate(n.args) if i < len(params[name]) and tainted(a, names)}
                    hit |= {k.arg for k in n.keywords if k.arg in params[name] and tainted(k.value, names)}
                    if hit - in_params[name]:
                        in_params[name] |= hit
                        outer = True
            if isinstance(n, ast.Return) and n.value is not None and tainted(n.value, names) and isinstance(scope, ast.FunctionDef) \
                    and scope.name not in returns:
                returns.add(scope.name)
                outer = True
        return outer

    again = True
    while again:
        again = run(tree, set())
        for name, f in funcs.items():
            again = run(f, set(in_params[name])) or again
    return sorted(sinks)


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
    assert _splitlines_feeding_json(bad) == [3, 6]
    good = tmp_path / "正しい.py"
    good.write_text("import json\ndef a(t):\n    return [json.loads(x) for x in t.split('\\n')]\n", encoding="utf-8")
    assert _splitlines_feeding_json(good) == []


INDIRECT = [
    ("変数に置いてから回す", "def r(t):\n    lines = t.splitlines()\n    out = []\n    for x in lines:\n        out.append(json.loads(x))\n"
                       "    return out\n", [5]),
    ("変数から 1 つ取り出す", "def r(t):\n    lines = t.splitlines()\n    first = lines[0]\n    return json.loads(first)\n", [4]),
    ("別の関数へ引数で渡す", "def parse(rows):\n    return [json.loads(x) for x in rows]\ndef r(t):\n    lines = t.splitlines()\n"
                      "    return parse(lines)\n", [2]),
    ("名前つきの引数で渡す", "def parse(rows=()):\n    for x in rows:\n        yield json.loads(x)\ndef r(t):\n"
                      "    return list(parse(rows=t.splitlines()))\n", [3]),
    ("別の関数が割って返す", "def split(t):\n    return t.splitlines()\ndef r(t):\n    return [json.loads(x) for x in split(t)]\n", [4]),
    ("2 段の関数を渡る", "def inner(rows):\n    return [json.loads(x) for x in rows]\ndef mid(rows):\n    return inner(rows)\n"
                   "def r(t):\n    return mid(t.splitlines())\n", [2]),
]


@pytest.mark.parametrize("name,src,want", INDIRECT, ids=[c[0] for c in INDIRECT])
def test_見張りの検査は遠回しの誤った読み口も拒む(tmp_path, name, src, want):
    bad = tmp_path / "作り物.py"
    bad.write_text("import json\n" + src, encoding="utf-8")
    assert _splitlines_feeding_json(bad) == [n + 1 for n in want]


def test_見張りの検査は正本の読み口と割った字を_JSON_に渡さない形を通す(tmp_path):
    ok = tmp_path / "正しい.py"
    ok.write_text("import json\nimport guard_common as G\n"
                  "def a(t):\n    return [json.loads(x) for x in G.json_lines(t)]\n"
                  "def b(p):\n    tail = (p.stderr or '').splitlines()[-1:]\n    return json.loads(p.stdout), tail\n"
                  "def c(t):\n    return len(t.splitlines())\n", encoding="utf-8")
    assert _splitlines_feeding_json(ok) == []


def test_土台の_1_行_1_件の_JSON_の割り方は正本_1_つ():
    """guard の中で 1 行 1 件の JSON を割る所は guard_common.json_lines だけ（会話ログの読み口と gh の出力の読み口がそれを呼ぶ）。"""
    import pr_text  # noqa: E402
    assert "G.json_lines(" in ast.get_source_segment(Path(pr_text.__file__).read_text(encoding="utf-8"),
                                                       next(n for n in ast.parse(Path(pr_text.__file__).read_text(encoding="utf-8")).body
                                                            if isinstance(n, ast.FunctionDef) and n.name == "pr_facts"))
    assert "json_lines(" in ast.get_source_segment(Path(G.__file__).read_text(encoding="utf-8"),
                                                     next(n for n in ast.parse(Path(G.__file__).read_text(encoding="utf-8")).body
                                                          if isinstance(n, ast.FunctionDef) and n.name == "iter_rows"))
    assert list(G.json_lines("{\"a\": \"x\u2028y\"}\n\n  \n{\"b\": 1}\n")) == ['{"a": "x\u2028y"}', '{"b": 1}']
