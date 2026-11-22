"""試験が「使う形」だけを読む口（説明の文・注釈・docstring で名を挙げるだけの所を外す）。

字が在るか無いかで照らす試験は、注釈に名を書くだけで緑（呼んでいないのに呼ぶ側）や赤（禁じる説明の文で写しの側）に
倒れる。照らす相手を、構文で読んだ使う所に絞ってから字を見る:
  py_code   … Python の源から注釈と docstring を除いた字（正本 kaku.py_code）
  py_calls  … Python の源で呼ぶ関数の名（ast の Call）
  py_marks  … Python の源の試験に付いた印（デコレータと pytestmark の pytest.mark.<名>）
  sh_code   … shell の源から注釈（語の頭の #）を除いた字（正本 kaku.sh_code）
  kaku      … core の読み口の正本（md_own・md_code・code・own・note_code・js_code など）
  yaml_runs … workflow・action の yml の steps の run の字（注釈・name は入らない）
  yaml_on   … workflow の yml の on: の出来事の名
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import yaml

# 構造（囲み・引用・注釈）の読み方の正本は core の kaku.py の「使う形の読み口」。試験は写しを置かずここから読む。
_spec = importlib.util.spec_from_file_location(
    "kaku_reader", Path(__file__).resolve().parent.parent / "plugins" / "core" / "scripts" / "kaku.py")
kaku = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kaku)


def py_code(src: str) -> str:
    """注釈と docstring を空にした Python の源の字（字の値・名・演算子は元の字のまま）。読み方の正本は kaku.py_code。"""
    return kaku.py_code(src)


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
    """shell の源から注釈（引用の外で語の頭に在る #）を除いた字。読み方の正本は kaku.sh_code。"""
    return kaku.sh_code(src)


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
