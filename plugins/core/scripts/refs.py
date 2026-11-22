#!/usr/bin/env python3
"""土台の文書の節・名のついた箇条・守りの見張りの出来事を、機械で読める約束として出し、使う側の指しを照らす。

意図: 使う側が土台の節・箇条・見張りの出来事を名で引けるようにし、字形を読むのはこの 1 か所だけにする。
課題: 土台が節を足す・並べ替える・書き方を変えると、使う側の指す先が黙って別の節になる（番号）か、読めずに止まった（字形）。
原因: 土台は文書の節（`## 3. 直すは根治`）・名のついた箇条（`- **まず構造を疑う** —`）・見張りの出来事
（guard の各 module の頭の `HOOKS = {...}`）を約束として出しておらず、使う側は「細目 §3」と番号で指すか、
見出しや太字の字形を自分で読むしかなかった。

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
<文書> は `細目.md`・`` `plugins/core/細目.md` `` のような file の名・path でもよい（略の名は長い語の中に当てない）。
土台の dir: repo の形（.claude-plugin/ が在る dir）なら repo の文書全部。入れた形（plugin の cache）なら入った版の
plugin の dir と、repo の根の文書（CONTRIBUTING・PR の型）は目録の clone の入った版の commit から読む。どちらの形でも
鍵は repo の相対 path（plugins/core/細目.md）にそろえる。読めなかった文書は "unread" に名指し、それを指す文は
外れに数えず「照らせない」にする（--root で repo の取り出しを渡せば全部照らせる）。

exit（土台の道具の 0/1/2 の約束・kaku.py olds・copies.py・values_keys.py と同じ）:
  0=合う／1=合わない指し・引けない名が在る（1 行ずつ名指す）／2=土台の文書が読めない・照らす file が読めない・
  外れは 0 だが照らせない指しが在る。
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
# 文書の書き方: file の名・path（`…` で囲んでも）を先に、略の名は長い語の中（「結核」の「核」）に当てない。
_DOC = (r"`?(?P<path>[\w./-]*[\w-]\.md)`?"
        r"|(?<![\u4e00-\u9fff々])(?P<alias>" + "|".join(map(re.escape, sorted(ALIASES, key=len, reverse=True))) + r")"
        r"|(?P<skill>skill:[\w-]+:[\w-]+)")
_REF = re.compile(r"(?:" + _DOC + r")\s*(?:§\s*(?P<no>\d+)\s*)?(?:「(?P<name>[^」\n]+)」)?")
MIN_QUOTE = 4   # 名でない引きは、これより短いと文書のどこかに当たるだけで合ってしまう（「の」）


def _kaku():
    """構造の読み方（コードの囲みの見分け）の正本 kaku.md_blocks を持つ core の kaku（写さない）。"""
    sys.path.insert(0, str(HERE))
    import kaku
    return kaku


def parse(text: str) -> dict:
    """1 つの文書の節と名のついた箇条（字形を読むのはここだけ）。"""
    sections, names, cur = [], [], None
    for no, (kind, line, _) in enumerate(_kaku().md_blocks(text), 1):
        if kind in ("mark", "fence"):
            continue                                       # 閉じの在るコードの囲みの中は見本（囲みの見分けの正本は kaku）
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


def _canon(root: Path) -> dict[str, Path]:
    """repo の形: {repo の相対 path: file}（文書と guard の見張りの .py）。"""
    files = [root / p for p in ALIASES.values()] + sorted(root.glob("plugins/*/skills/*/SKILL.md")) \
        + sorted(root.glob("plugins/guard/scripts/*.py"))
    return {f.relative_to(root).as_posix(): f for f in files if f.is_file()}


def _installed() -> tuple[str, dict[str, str], list[str]]:
    """入れた形（cache/<目録>/<plugin>/<版>/）: (読んだ所, {repo と同じ相対 path: 中身}, 読めなかった文書)。
    鍵は repo の形と同じ path（plugins/<plugin>/…）にそろえる（入れた形の path を約束に出さない＝使う側の指しは
    どちらの形でも同じ名で合う）。plugin の dir は入った台帳の今読まれる行（kaku.current_row）、無ければこの core と同じ版。
    repo の根の文書（CONTRIBUTING・PR の型）は plugin に入らないので、目録の clone から入った版の commit の物を読む。"""
    sys.path.insert(0, str(HERE))
    import kaku
    rows = kaku._foundation_rows()
    dirs = {n: Path(str(r["installPath"])) for n, r in rows.items() if r.get("installPath")}
    if not dirs:
        dirs = {d.name: d / PLUGIN.name for d in PLUGIN.parent.parent.iterdir() if (d / PLUGIN.name).is_dir()}
    texts = {}
    for name, d in dirs.items():
        for f in [d / n for n in ("核.md", "細目.md", "振る舞い.md")] + sorted(d.glob("skills/*/SKILL.md")) \
                + (sorted(d.glob("scripts/*.py")) if name == "guard" else []):
            if f.is_file():
                texts[f"plugins/{name}/{f.relative_to(d).as_posix()}"] = f.read_text(encoding="utf-8")
    m, _ = kaku.catalog_source()
    loc, sha = m.get("installLocation"), (rows.get("core") or {}).get("gitCommitSha")
    missing = []
    for rel in (r for r in ALIASES.values() if not r.startswith("plugins/")):
        got = kaku._git(str(loc), "show", f"{sha}:{rel}", timeout=10) if loc and sha else None
        if got is None:
            missing.append(rel)
        else:
            texts[rel] = got
    return str(PLUGIN.parent), texts, missing


def hooks(texts: dict[str, str]) -> tuple[dict, list[str]]:
    """guard の各見張りの頭の HOOKS（出来事: 関数）と、読めなかった module の名指し。代入の字を ast で読む（実行しない）。"""
    out, bad = {}, []
    for rel, text in sorted(texts.items()):
        if not (rel.startswith("plugins/guard/scripts/") and rel.endswith(".py")):
            continue
        try:
            tree = ast.parse(text)
            for node in tree.body:
                if (isinstance(node, ast.Assign) and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "HOOKS"):
                    out[rel] = ast.literal_eval(node.value)
        except (SyntaxError, ValueError) as e:
            bad.append(f"{rel} の HOOKS が字の宣言として読めない: {e}")
    return out, bad


def contract(root: Path | None = None) -> dict:
    if root is None and (PLUGIN.parent.parent / ".claude-plugin").is_dir():
        root = PLUGIN.parent.parent
    if root is not None:
        base, missing = str(root), [r for r in ALIASES.values() if not (root / r).is_file()]
        texts = {k: f.read_text(encoding="utf-8") for k, f in _canon(root).items()}
    else:
        base, texts, missing = _installed()
    docs = {k: v for k, v in texts.items() if k.endswith(".md")}
    if not docs:
        raise OSError(f"土台の文書が 1 つも読めない（{base}）。--root で土台の dir を渡す")
    hk, hk_bad = hooks(texts)
    return {"root": base, "docs": {k: parse(v) for k, v in docs.items()}, "hooks": hk, "unread": missing + hk_bad,
            "_texts": docs}


def _want(doc: str) -> str:
    """指しの文書の名を repo の相対 path に（略の名・skill の名・`細目.md` のような名だけの file）。"""
    if doc in ALIASES:
        return ALIASES[doc]
    if doc.startswith("skill:"):
        _, plugin, name = doc.split(":")
        return f"plugins/{plugin}/skills/{name}/SKILL.md"
    doc = doc.lstrip("./")
    by_name = [p for p in ALIASES.values() if p.rsplit("/", 1)[-1] == doc]
    return by_name[0] if len(by_name) == 1 else doc


def _doc_key(c: dict, doc: str) -> str | None:
    want = _want(doc)
    if want in c["docs"]:
        return want
    hits = [k for k in c["docs"] if k.endswith("/" + want)]
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
    return check_all(c, text, numbers_ok)[0]


def check_all(c: dict, text: str, numbers_ok: bool = False) -> tuple[list, list]:
    """(外れ, 照らせない指し)。照らせない指し＝土台の文書がこの形で読めない（入れた形で目録の clone が無い等）。"""
    bad, unread = [], []
    for lno, (kind, line, _) in enumerate(_kaku().md_blocks(text), 1):
        if kind in ("mark", "fence"):
            continue                                       # 閉じの在るコードの囲みの中は例・見本（指しでない）
        for m in _REF.finditer(line):
            doc = m.group("path") or m.group("alias") or m.group("skill")
            no, name = m.group("no"), m.group("name")
            if no is None and name is None:
                continue                                   # 文書の名だけ（節を指していない）
            key = _doc_key(c, doc)
            if key is None:
                want = _want(doc)
                if want in c.get("unread", []):
                    unread.append((lno, f"{doc} の指しを照らせない（{want} がこの形の土台で読めない＝照らした数に入れない）"))
                elif doc in ALIASES or doc.startswith("skill:") or want in ALIASES.values() or want.startswith("plugins/"):
                    bad.append((lno, f"{doc} が土台に無い（読んだ土台: {c['root']}）"))
                continue                                   # 土台の外の .md は照らさない
            nums = {s["no"] for s in c["docs"][key]["sections"] if s["no"] is not None}
            if name is not None:
                hit = find(c, doc, name)
                if hit is None and len(_flat(name)) >= MIN_QUOTE and _flat(name) in _flat(_section_text(c, key, no)):
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
    return bad, unread


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
    total = skipped = 0
    for p in a.files:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"refs: 照らせない — {p}: {e}")
            return 2
        bad, unread = check_all(c, text, a.numbers)
        for lno, msg in bad:
            print(f"✗ {p}:{lno} {msg}")
            total += 1
        for lno, msg in unread:
            print(f"? {p}:{lno} {msg}")
            skipped += 1
    if total:
        print(f"refs: 赤 外れた指し {total} 件")
        print("直し: 指しを今の名に替える（番号は付けない）。名が消えた・変わった訳は土台の変更の記録（CHANGELOG.d の「壊れる」）を引き、"
              "指す形が要る訳は、意図（指しが土台の今の名に合う）とのずれから入り、細目「まず構造を疑う」で探す")
        return 1
    if skipped:
        print(f"refs: 照らせない 指し {skipped} 件（外れ 0）。土台の repo の取り出しを --root で渡すと全部照らせる")
        return 2
    print(f"refs: 緑（{len(a.files)} file の指しを土台の {len(c['docs'])} 文書と照らした）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
