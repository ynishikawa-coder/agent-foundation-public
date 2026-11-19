#!/usr/bin/env python3
"""部品（plugin）どうしの呼び出しの流れを、コードと手順の文から機械で拾い、全体の絵に全部在るかを照らす。

なぜ在るか: 全体の絵を写す・描く時に、ある plugin の script・skill の手順が別の plugin の道具を呼ぶ流れを、
人の目で 2 回続けて拾い漏らした（合意した絵に無い流れが実物に在り、合流の前の照らしで red）。
流れは目で探さず、ここで拾った一覧を正にする。

  python3 scripts/call_flows.py list  [--repo DIR]            # 流れを 1 行ずつ「呼ぶ側 → 呼ばれる側  証拠」で出す
  python3 scripts/call_flows.py check <絵.json> [--repo DIR]  # 拾った流れが全部、絵の仕組みの構成（arch）の矢印に在るか

拾う物（道具＝plugins/<名>/ の下の .py .mjs .js .sh の file）:
  - 別の plugin の道具の file 名（その名の file が plugin の外にも在る時は path ごと書いた物だけ）
  - 別の plugin の道具の path（plugins/<名>/…/<道具の file 名>）
  - コード（道具の file）が持つ別の plugin の file の在り処は、拡張子を問わず拾う（雛形の .md・表の .json を読む流れも）。
    path を割って書いた呼び方（("checker", os.path.join("scripts", "verdict_form.py")) の類）は、Python は ast で、
    他のコードは 1 行の字の並び（引用の中）で、1 つの式の中の字を順に / でつないで、git の在る file に結べるかで見る
    （名の字の形でなく、実物の file に結べるか）。
  拾わない物: skill の名を文で挙げるだけの物・文書（.md 等）が文書の path を挙げるだけの物（道具を呼ぶ流れでない）。
  残る穴: 字を実行時に組む呼び方（f 文字列・変数で plugin の名を差す）は結べない。
絵との対応: 絵の箱のうち tab が arch で、題の頭（「（」の前）が plugin の名と同じ箱をその plugin の箱とみる。
  箱が無い plugin・2 つ在る plugin は照らせない＝赤（黙って通さない）。矢印の向きは 呼ぶ側 → 呼ばれる側。
exit: list は 0。check は 0=全部在る／1=絵に無い流れが在る／2=照らせない（絵が読めない・箱が無い・重なる）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL_SUFFIX = (".py", ".mjs", ".js", ".sh")
TEXT_SUFFIX = (".py", ".mjs", ".js", ".sh", ".md", ".json", ".html", ".txt")
ROOT_CAUSE = ("直し: 絵に無い流れを 1 本ずつ足して済ませず、流れが絵から漏れた原因を細目 §3「まず構造を疑う」で探して直す"
              "（絵は合意の版＝足すならオーナーに差を見せて決めてもらう）")


def tracked(repo: Path) -> list[str]:
    r = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files"], cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise OSError(f"git の一覧が取れない: {r.stderr.strip()}")
    return [ln for ln in r.stdout.splitlines() if ln]


CODE_SUFFIX = TOOL_SUFFIX
MAX_JOIN = 8          # 1 つの式の中でつなぐ字の数の上限
_QUOTED = re.compile(r"""(['"`])((?:(?!\1).){1,300})\1""")


def _py_groups(text: str):
    """Python の 1 つの式（呼び出し・並び）ごとの字の並び (行, [字])。読めない file は None。"""
    import ast
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Call, ast.Tuple, ast.List, ast.Set, ast.Dict, ast.BinOp)):
            consts = sorted((c.lineno, c.col_offset, c.value) for c in ast.walk(node)
                            if isinstance(c, ast.Constant) and isinstance(c.value, str) and len(c.value) < 300)
            if len(consts) >= 2:
                out.append((node.lineno, [v for _, _, v in consts]))
    return out


def _line_groups(lines):
    """他のコードは 1 行の引用の中の字の並び。"""
    return [(no, [m.group(2) for m in _QUOTED.finditer(ln)]) for no, ln in enumerate(lines, 1)]


def _resolve(pieces, x: str, files_of: dict[str, set[str]]):
    """字の並びを順に / でつなぎ、別の plugin の在る file（plugins/<y>/<rel> か <y> と <rel> の並び）に結べた (y, file 名)。"""
    got = set()
    pieces = [p.strip().strip("/") for p in pieces if p.strip().strip("/")]
    for i in range(len(pieces)):
        for j in range(i + 2, min(i + MAX_JOIN, len(pieces)) + 1):
            joined = re.sub(r"/+", "/", "/".join(pieces[i:j]))
            if joined.startswith("./"):
                joined = joined[2:]
            if joined.startswith("plugins/"):
                joined = joined[len("plugins/"):]
            y, _, rel = joined.partition("/")
            if y != x and rel in files_of.get(y, ()):
                got.add((y, rel.rsplit("/", 1)[-1]))
    return got


def flows(repo: Path) -> dict[tuple[str, str], list[str]]:
    """{(呼ぶ側, 呼ばれる側): [証拠 "path:行 字"]}。"""
    files = tracked(repo)
    plugins = sorted({f.split("/")[1] for f in files if f.startswith("plugins/") and f.count("/") >= 2
                      and (repo / "plugins" / f.split("/")[1] / ".claude-plugin" / "plugin.json").is_file()})
    owner: dict[str, set[str]] = defaultdict(set)      # 道具の file 名 → 持つ plugin
    outside: set[str] = set()                          # plugin の外にも同じ名の file が在る名
    files_of: dict[str, set[str]] = defaultdict(set)   # plugin → その下の file（plugin の根からの path・拡張子を問わない）
    for f in files:
        name = f.rsplit("/", 1)[-1]
        parts = f.split("/")
        if parts[0] == "plugins" and len(parts) >= 3 and parts[1] in plugins:
            files_of[parts[1]].add("/".join(parts[2:]))
            if f.endswith(TOOL_SUFFIX):
                owner[name].add(parts[1])
        elif not (parts[0] == "plugins"):
            outside.add(name)
    pats = []
    for name, ys in owner.items():
        for y in ys:
            path_pat = re.compile(r"plugins/%s/(?:[^\s'\"`)]*/)?%s(?![\w.])" % (re.escape(y), re.escape(name)))
            bare = None if (name in outside or len(ys) > 1) else re.compile(r"(?<![\w./-])%s(?![\w])" % re.escape(name))
            pats.append((y, name, path_pat, bare))
    any_path = re.compile(r"plugins/([\w.-]+)/([^\s'\"`)\]]+)")
    out: dict[tuple[str, str], list[str]] = defaultdict(list)
    for f in files:
        parts = f.split("/")
        if parts[0] != "plugins" or len(parts) < 3 or parts[1] not in plugins or not f.endswith(TEXT_SUFFIX):
            continue
        x = parts[1]
        try:
            text = (repo / f).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        code = f.endswith(CODE_SUFFIX)
        for no, ln in enumerate(lines, 1):
            for y, name, path_pat, bare in pats:
                if y == x:
                    continue
                if path_pat.search(ln) or (bare and bare.search(ln)):
                    out[(x, y)].append(f"{f}:{no} {name}")
            if code:   # コードが持つ別の plugin の file の在り処（拡張子を問わない）
                for m in any_path.finditer(ln):
                    y, rel = m.group(1), m.group(2).rstrip(".,;:")
                    if y != x and rel in files_of.get(y, ()):
                        out[(x, y)].append(f"{f}:{no} {rel.rsplit('/', 1)[-1]}")
        if code:
            groups = _py_groups(text) if f.endswith(".py") else None
            for no, pieces in groups if groups is not None else _line_groups(lines):
                for y, name in sorted(_resolve(pieces, x, files_of)):
                    ev = f"{f}:{no} {name}"
                    if ev not in out[(x, y)]:
                        out[(x, y)].append(ev)
    return {k: v for k, v in out.items() if v}


def plugin_boxes(pic: dict, names) -> tuple[dict[str, str], list[str]]:
    boxes = [b for b in pic.get("boxes") or [] if isinstance(b, dict) and b.get("tab") == "arch"]
    found: dict[str, list[str]] = defaultdict(list)
    for b in boxes:
        head = str(b.get("t") or "").split("（", 1)[0].strip()
        if head in names:
            found[head].append(str(b.get("id")))
    errs = [f"plugin {n} の箱が絵の仕組みの構成（arch）に無い" for n in names if not found.get(n)]
    errs += [f"plugin {n} の箱が 2 つ以上在る（{'・'.join(ids)}）" for n, ids in found.items() if len(ids) > 1]
    return {n: ids[0] for n, ids in found.items() if len(ids) == 1}, errs


def check(pic_path: Path, repo: Path) -> int:
    try:
        pic = json.loads(pic_path.read_text(encoding="utf-8"))
        if not isinstance(pic, dict):
            raise ValueError("絵が JSON の object でない")
        got = flows(repo)
    except (OSError, ValueError) as e:
        print(f"call_flows: 照らせない — {e}")
        return 2
    names = sorted({n for pair in got for n in pair})
    box, errs = plugin_boxes(pic, names)
    if errs:
        for e in errs:
            print(f"✗ {e}")
        print("call_flows: 照らせない（plugin の箱と流れを結べない）")
        return 2
    arrows = {(a.get("from"), a.get("to")) for a in pic.get("arrows") or [] if isinstance(a, dict)}
    missing = [(x, y, ev) for (x, y), ev in sorted(got.items()) if (box[x], box[y]) not in arrows]
    for x, y, ev in missing:
        print(f"✗ 絵に無い流れ: {x} → {y}（{box[x]} → {box[y]}）証拠: {ev[0]}" + (f" ほか {len(ev) - 1}" if len(ev) > 1 else ""))
    if missing:
        print(f"call_flows: 赤 絵に無い流れ {len(missing)} 本")
        print(ROOT_CAUSE)
        return 1
    print(f"call_flows: 緑 流れ {len(got)} 本が全部絵に在る")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--repo", type=Path, default=ROOT)
    ck = sub.add_parser("check")
    ck.add_argument("picture", type=Path)
    ck.add_argument("--repo", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for (x, y), ev in sorted(flows(a.repo).items()):
            print(f"{x} → {y}  {ev[0]}" + (f" ほか {len(ev) - 1}" if len(ev) > 1 else ""))
        return 0
    return check(a.picture, a.repo)


if __name__ == "__main__":
    sys.exit(main())
