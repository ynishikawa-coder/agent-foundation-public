"""試験が「使う形」だけを読む口（説明の文・注釈・docstring で名を挙げるだけの所を外す）。

字が在るか無いかで照らす試験は、注釈に名を書くだけで緑（呼んでいないのに呼ぶ側）や赤（禁じる説明の文で写しの側）に
倒れる。照らす相手を、構文で読んだ使う所に絞ってから字を見る:
  py_code   … Python の源から注釈と docstring を除いた字（tokenize と ast で読む）
  py_calls  … Python の源で呼ぶ関数の名（ast の Call）
  py_marks  … Python の源の試験に付いた印（デコレータと pytestmark の pytest.mark.<名>）
  sh_code   … shell の源から注釈（語の頭の #）を除いた字
  yaml_runs … workflow・action の yml の steps の run の字（注釈・name は入らない）
  yaml_on   … workflow の yml の on: の出来事の名
"""
from __future__ import annotations

import ast
import io
import tokenize

import yaml


def _docstring_lines(tree) -> set[int]:
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                lines.update(range(body[0].lineno, body[0].end_lineno + 1))
    return lines


def py_code(src: str) -> str:
    """注釈と docstring を除いた Python の源の字（字の値・名・演算子は残る）。"""
    doc = _docstring_lines(ast.parse(src))
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and tok.start[0] in doc:
            continue
        out.append(tok.string)
    return " ".join(out)


def py_calls(src: str) -> set[str]:
    """呼ぶ関数の名（f(…) の f・a.f(…) の f）。"""
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            f = node.func
            names.add(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
    return names - {""}


def _mark_name(node) -> str | None:
    """pytest.mark.<名>（呼び出しの形も）の名。"""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) and node.value.attr == "mark" \
            and isinstance(node.value.value, ast.Name) and node.value.value.id == "pytest":
        return node.attr
    return None


def py_marks(src: str) -> set[str]:
    """試験の印の名（関数・class のデコレータと、module の pytestmark の代入）。"""
    marks = set()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            marks.update(m for m in map(_mark_name, node.decorator_list) if m)
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "pytestmark" for t in node.targets):
            vals = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
            marks.update(m for m in map(_mark_name, vals) if m)
    return marks


def sh_code(src: str) -> str:
    """shell の源から注釈（引用の外で語の頭に在る #）を除いた字。"""
    out, q, i, n = [], "", 0, len(src)
    while i < n:
        c = src[i]
        if q:
            out.append(c)
            if c == "\\" and q == '"' and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            q = "" if c == q else q
        elif c in "'\"":
            q = c
            out.append(c)
        elif c == "#" and (i == 0 or src[i - 1] in " \t\n;&|("):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _steps(doc) -> list[dict]:
    out = []
    if isinstance(doc, dict):
        for k, v in doc.items():
            if k == "steps" and isinstance(v, list):
                out += [s for s in v if isinstance(s, dict)]
            else:
                out += _steps(v)
    elif isinstance(doc, list):
        for v in doc:
            out += _steps(v)
    return out


def yaml_runs(text: str) -> list[str]:
    """yml の全部の steps の run の字（並びの順）。"""
    return [str(s.get("run") or "") for s in _steps(yaml.safe_load(text))]


def yaml_on(text: str) -> set[str]:
    """workflow の on: の出来事の名（YAML 1.1 で on が true に読まれる形も）。"""
    doc = yaml.safe_load(text) or {}
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return set(map(str, on))
    return set(on or {})
