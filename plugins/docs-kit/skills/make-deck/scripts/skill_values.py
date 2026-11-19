#!/usr/bin/env python3
"""skill_values.py — repo ごとの値の表（repo の根の config/skill-values.json）を読む小さな口.

規則（SKILL.md と同じ）:
  - 表は「今の作業 dir の repo の根」から引く（plugin は install 時に cache へ写されて動く＝
    このファイルの置き場からは引かない）。根は `git rev-parse --show-toplevel`。
  - 環境変数 SKILL_VALUES に path があればそれを読む（試験・repo の外で動かす時）。
  - 表が無い・読めない・鍵が無い・値が空（""・[]・{}・None）なら default を返す
    ＝他社（種）の空の型でも skill は中立の既定で動く。
  - 引く鍵は SKILL.md の「repo ごとの値」の表に載った物だけ。載っていない鍵を引くと止まる
    （土台の guard の values_keys の読み口を直に通す＝表とコードのずれが実行の時に出る）。

使い方:
  from skill_values import get
  accent = get("docs-kit", "make-deck", "accent", default="#334155")
  python3 skill_values.py docs-kit make-deck accent   # 値を 1 つ表示（無ければ空行）
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REL_PATH = os.path.join("config", "skill-values.json")


def _repo_root(cwd=None):
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd or os.getcwd(),
                             capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def table_path(cwd=None):
    env = os.environ.get("SKILL_VALUES")
    if env:
        return env
    root = _repo_root(cwd)
    return os.path.join(root, REL_PATH) if root else None


def load(cwd=None):
    """表をまるごと返す。無い・壊れている時は {}（skill を止めない＝既定で動く）。"""
    path = table_path(cwd)
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        sys.stderr.write("⚠ %s が読めないので既定で動く: %s\n" % (path, exc))
        return {}
    return data if isinstance(data, dict) else {}


def _empty(v):
    return v is None or (isinstance(v, (str, list, dict)) and len(v) == 0) or (
        isinstance(v, str) and not v.strip())


def values_reader():
    """値の表の読み口（土台の plugin guard の scripts/values_keys.py）を直に読む（写さない）。表に無い鍵を読むと止まる。
    在り処: repo の形 plugins/guard・入れた plugin の形 cache/<市場>/guard/<版>（同じ版を先に、無ければ新しい物）。
    見つからなければ止める（読み口を通さずに値の表を読まない）。"""
    if "af_values_keys" in sys.modules:
        return sys.modules["af_values_keys"]
    plugin = Path(__file__).resolve().parents[3]
    rel = Path("scripts") / "values_keys.py"
    cands = [plugin.parent / "guard" / rel, plugin.parent.parent / "guard" / plugin.name / rel]
    cands += sorted((plugin.parent.parent / "guard").glob("*/scripts/values_keys.py"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    for c in cands:
        if c.is_file():
            import importlib.util
            spec = importlib.util.spec_from_file_location("af_values_keys", c)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["af_values_keys"] = mod
            spec.loader.exec_module(mod)
            return mod
    raise RuntimeError("値の表の読み口（土台の plugin guard の scripts/values_keys.py）が見つからない。土台の plugin guard を入れる")


def get(*keys, default=None, table=None):
    """get("docs-kit", "make-deck", "accent", default=...)。common は get("common", "<鍵>")。
    鍵の path が SKILL.md の「repo ごとの値」の表に無ければ、表の中身に依らず止まる（values_keys の読み口）。"""
    values_reader().require(keys)
    node = load() if table is None else table
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            return default
        node = node[k]
    return default if _empty(node) else node


def main(argv):
    if not argv:
        sys.stderr.write("使い方: python3 skill_values.py <plugin|common> [<skill>] <鍵>\n")
        return 2
    v = get(*argv, default="")
    print(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
