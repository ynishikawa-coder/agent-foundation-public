#!/usr/bin/env python3
"""skill_values.py — repo ごとの値の表（repo の根の config/skill-values.json）を読む小さな口.

規則（SKILL.md と同じ）:
  - 表は「今の作業 dir の repo の根」から引く（plugin は install 時に cache へ写されて動く＝
    このファイルの置き場からは引かない）。根は `git rev-parse --show-toplevel`。
  - 環境変数 SKILL_VALUES に path があればそれを読む（試験・repo の外で動かす時）。
  - 表が無い・読めない・鍵が無い・値が空（""・[]・{}・None）なら default を返す
    ＝他社（種）の空の型でも skill は中立の既定で動く。

使い方:
  from skill_values import get
  accent = get("docs-kit", "make-deck", "accent", default="#334155")
  python3 skill_values.py docs-kit make-deck accent   # 値を 1 つ表示（無ければ空行）
"""
import json
import os
import subprocess
import sys

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


def get(*keys, default=None, table=None):
    """get("docs-kit", "make-deck", "accent", default=...)。common は get("common", "<鍵>")。"""
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
