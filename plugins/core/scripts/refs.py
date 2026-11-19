#!/usr/bin/env python3
"""土台の文書の節・名のついた箇条・守りの見張りの出来事を、機械で読める約束として出し、使う側の指しを照らす。

なぜ在るか: 土台は文書の節（`## 3. 直すは根治`）・名のついた箇条（`- **まず構造を疑う** —`）・見張りの出来事
（guard の各 module の頭の `HOOKS = {...}`）を約束として出していなかった。使う側は「細目 §3」と番号で指すか、
見出しや太字の字形を自分で読むしかなく、土台が節を足す・並べ替える・書き方を変えると、指す先が黙って別の節になる
（番号）か、読めずに止まった（字形）。字形を読むのはこの 1 か所だけにし、使う側は名で引く。

約束（出す物）:
  list  … JSON。{"root": 読んだ土台の dir, "docs": {相対 path: {"sections": [{"no", "title", "level", "line"}],
           "names": [{"name", "section", "line"}]}}, "hooks": {相対 path: {出来事: 関数}}}。
           no は見出しの番号（`## 量の上限` のように番号の無い節は null）。section は名のついた箇条が入る節の title。
  find <文書> <名> … 節の title か箇条の名を引き、今の番号と節を 1 行で出す。
  check <file>...  … 使う側の文の土台への指しを照らす。照らす形は 2 つ:
           `<文書> §<番号>`（後に「名」が続いてもよい）と `<文書>「名」`。<文書> は ALIASES の名か土台の相対 path。
           番号の無い「…」は節の title・箇条の名のほか、文の引きでもよい（その文書に今も在る字なら合う）。
           赤: 名（引いた文）が土台に無い／番号と名が今の節と合わない／番号だけで指す（--numbers で番号だけを許す＝土台の中の指し）
           ／在らない番号。
文書の名（ALIASES）: 核・細目・振る舞い・CONTRIBUTING・PR の型。skill は `skill:<plugin>:<名>`。
土台の dir: repo の形（.claude-plugin/ が在る dir）なら repo の文書全部、入れた形なら入った版の plugin の dir だけ
（copies.plugin_dirs と同じ選び方）。--root で渡せる。

exit（土台の道具の 0/1/2 の約束・kaku.py olds・copies.py・values_keys.py と同じ）:
  0=合う／1=合わない指し・引けない名が在る（1 行ずつ名指す）／2=土台の文書が読めない・照らす file が読めない。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
ALIASES = {
    "核": "plugins/core/核.md",
    "細目": "plugins/core/細目.md",
    "振る舞い": "plugins/core/振る舞い.md",
    "CONTRIBUTING": "CONTRIBUTING.md",
    "PR の型": ".github/pull_request_template.md",
}
_HEAD = re.compile(r"^(#{2,4})\s+(?:(\d+)\.\s+)?(.+?)\s*$")
_NAME = re.compile(r"^\s*[-*]\s+\*\*([^*]+?)\*\*")
_DOC = "|".join(map(re.escape, sorted(ALIASES, key=len, reverse=True))) + r"|skill:[\w-]+:[\w-]+|[\w./-]+\.md"
_REF = re.compile(r"(?P<doc>" + _DOC + r")\s*(?:§\s*(?P<no>\d+)\s*)?(?:「(?P<name>[^」\n]+)」)?")


def _root(root: Path | None) -> tuple[Path, list[Path]]:
    """(土台の dir, 読む文書の並び)。"""
    if root is None and (PLUGIN.parent.parent / ".claude-plugin").is_dir():
        root = PLUGIN.parent.parent
    if root is not None:
        docs = [root / p for p in ALIASES.values()] + sorted(root.glob("plugins/*/skills/*/SKILL.md"))
        return root, [d for d in docs if d.is_file()]
    sys.path.insert(0, str(HERE))
    import copies
    dirs = copies.plugin_dirs()
    docs = [PLUGIN / n for n in ("核.md", "細目.md", "振る舞い.md")] + sorted(
        p for d in dirs for p in d.glob("skills/*/SKILL.md"))
    return PLUGIN.parent, [d for d in docs if d.is_file()]


def _rel(root: Path, p: Path) -> str:
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return p.as_posix()


def parse(text: str) -> dict:
    """1 つの文書の節と名のついた箇条（字形を読むのはここだけ）。"""
    sections, names, cur, fence = [], [], None, False
    for no, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = _HEAD.match(line)
        if m:
            cur = m.group(3)
            sections.append({"no": int(m.group(2)) if m.group(2) else None, "title": cur,
                             "level": len(m.group(1)), "line": no})
            continue
        m = _NAME.match(line)
        if m:
            names.append({"name": m.group(1).strip(), "section": cur, "line": no})
    return {"sections": sections, "names": names}


def hooks(root: Path) -> dict:
    """guard の各見張りの頭の HOOKS（出来事: 関数）。代入の字を ast で読む（module を実行しない）。"""
    out = {}
    for p in sorted(root.glob("plugins/guard/scripts/*.py")) or sorted(PLUGIN.parent.glob("guard/scripts/*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "HOOKS"):
                out[_rel(root, p)] = ast.literal_eval(node.value)
    return out


def contract(root: Path | None = None) -> dict:
    base, docs = _root(root)
    if not docs:
        raise OSError(f"土台の文書が 1 つも読めない（{base}）。--root で土台の dir を渡す")
    texts = {_rel(base, d): d.read_text(encoding="utf-8") for d in docs}
    return {"root": str(base), "docs": {k: parse(v) for k, v in texts.items()}, "hooks": hooks(base), "_texts": texts}


def _doc_key(c: dict, doc: str) -> str | None:
    if doc in ALIASES:
        doc = ALIASES[doc]
    elif doc.startswith("skill:"):
        _, plugin, name = doc.split(":")
        doc = f"plugins/{plugin}/skills/{name}/SKILL.md"
    if doc in c["docs"]:
        return doc
    hits = [k for k in c["docs"] if k.endswith("/" + doc)]
    return hits[0] if len(hits) == 1 else None


def find(c: dict, doc: str, name: str) -> dict | None:
    """名（節の title か箇条の名）を引く。{"no": 節の番号, "section": 節の title, "kind": "section"|"name"}。"""
    key = _doc_key(c, doc)
    if key is None:
        return None
    d = c["docs"][key]
    for s in d["sections"]:
        if s["title"] == name:
            return {"doc": key, "no": s["no"], "section": s["title"], "kind": "section"}
    by_title = {s["title"]: s for s in d["sections"]}
    for n in d["names"]:
        if n["name"] == name:
            sec = by_title.get(n["section"]) or {}
            return {"doc": key, "no": sec.get("no"), "section": n["section"], "kind": "name"}
    return None


def _section_text(c: dict, key: str, no: str | None) -> str:
    """文書の字（番号が在れば、その番号の節の字だけ・節が無ければ空）。"""
    text = c["_texts"][key]
    if no is None:
        return text
    lines, secs = text.splitlines(), c["docs"][key]["sections"]
    for i, s in enumerate(secs):
        if s["no"] == int(no):
            end = next((x["line"] for x in secs[i + 1:] if x["level"] <= s["level"]), len(lines) + 1)
            return "\n".join(lines[s["line"] - 1:end - 1])
    return ""


def _flat(s: str) -> str:
    return re.sub(r"[\s`*]+", "", s)


def check_text(c: dict, text: str, numbers_ok: bool = False) -> list[tuple[int, str]]:
    """文の土台への指しの外れ (行番号, 名指し) の並び。"""
    bad = []
    for lno, line in enumerate(text.splitlines(), 1):
        for m in _REF.finditer(line):
            doc, no, name = m.group("doc"), m.group("no"), m.group("name")
            if no is None and name is None:
                continue                                   # 文書の名だけ（節を指していない）
            key = _doc_key(c, doc)
            if key is None:
                if doc in ALIASES or doc.startswith("skill:"):
                    bad.append((lno, f"{doc} が土台に無い（読んだ土台: {c['root']}）"))
                continue                                   # 土台の外の .md は照らさない
            nums = {s["no"] for s in c["docs"][key]["sections"] if s["no"] is not None}
            if name is not None:
                hit = find(c, doc, name)
                if hit is None and _flat(name) in _flat(_section_text(c, key, no)):
                    continue                               # 名でなく文の引き: 土台の文（番号が在ればその節）に今も在れば合う
                if hit is None:
                    bad.append((lno, f"{doc}「{name}」が土台の {key} に無い（節・名・文のどれにも無い＝変わったか消えた）"))
                elif no is not None and hit["no"] != int(no):
                    bad.append((lno, f"{doc} §{no}「{name}」の番号がずれた（今は §{hit['no']}「{hit['section']}」）。"
                                      f"番号を消して {doc}「{name}」と名で指す"))
            elif int(no) not in nums:
                bad.append((lno, f"{doc} §{no} は土台の {key} に無い番号"))
            elif not numbers_ok:
                title = next(s["title"] for s in c["docs"][key]["sections"] if s["no"] == int(no))
                bad.append((lno, f"{doc} §{no} を番号だけで指している（土台が節を足すと黙って別の節になる）。"
                                  f"名で指す: {doc}「{title}」"))
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    f = sub.add_parser("find")
    f.add_argument("doc")
    f.add_argument("name")
    k = sub.add_parser("check")
    k.add_argument("files", nargs="+", type=Path)
    k.add_argument("--numbers", action="store_true", help="番号だけの指しを許す（土台の中の指し）。番号が在るかは照らす")
    a = ap.parse_args(argv)
    try:
        c = contract(a.root)
    except (OSError, UnicodeDecodeError, ValueError, SyntaxError) as e:
        print(f"refs: 照らせない — {e}")
        return 2
    if a.cmd == "list":
        print(json.dumps({k: v for k, v in c.items() if not k.startswith("_")}, ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "find":
        hit = find(c, a.doc, a.name)
        if hit is None:
            print(f"refs: {a.doc}「{a.name}」は土台に無い")
            return 1
        where = f"§{hit['no']}「{hit['section']}」" if hit["no"] is not None else f"「{hit['section']}」"
        print(f"{hit['doc']} {where}" + (f" の「{a.name}」" if hit["kind"] == "name" else ""))
        return 0
    total = 0
    for p in a.files:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"refs: 照らせない — {p}: {e}")
            return 2
        for lno, msg in check_text(c, text, a.numbers):
            print(f"✗ {p}:{lno} {msg}")
            total += 1
    if total:
        print(f"refs: 赤 外れた指し {total} 件")
        print("直し: 指しを今の名に替える（番号は付けない）。名が消えた・変わった訳は土台の変更の記録（CHANGELOG.d の「壊れる」）を引き、"
              "指す形が要る訳は細目「まず構造を疑う」で探す")
        return 1
    print(f"refs: 緑（{len(a.files)} file の指しを土台の {len(c['docs'])} 文書と照らした）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
