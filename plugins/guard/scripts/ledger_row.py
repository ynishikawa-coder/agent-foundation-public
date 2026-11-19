"""PreToolUse — 原因の台帳へ書く行の形を、Notion へ出る前に照らし、崩れていれば AI だけを止める。

なぜ在るか: 台帳の 1 行の形（行き先と、その行き先が要る欄）は細目 §3「原因の台帳」の文だけで、Notion へ書く道具には
  何も当たらず、行き先に要る欄の欠けた行（理由の無い「直さない」・URL の無い「直す窓」）が入りえた。
正本（写さない）: 細目 §3「原因の台帳」の文を直に読む — `<行き先>`（欄「<名>」…）の並びが行き先ごとに要る欄、
  「`<行き先>` の行を残して」が欄の要らない行き先（未定）。見張りの側は行き先の語も欄の名も持たない。
  細目が読めない・並びが取れない時は、台帳の行を見つけたら止める（照らせない行を出さない）。
見分け: 台帳の行＝「行き先」の鍵を持つ入力（台帳の id を値で持たない＝どの会社の台帳でも同じ列の名で当たる）。
  - MCP の Notion の書く道具（名に notion と create・update）の入力の全部。
  - Bash の命令の字の中の JSON と、命令が option の値で渡す在る file（repo の書き込みの道具へ --payload x.json・curl の -d @x.json）の中の JSON。
    行き先を JSON で書けば、送り先（api.notion.com か repo の道具か）を問わず当たる。
  - 値の表の `ledger_targets`（台帳の database・data source の id）を親にして作る行に「行き先」が無ければ止める
    （行き先の鍵を書かずに台帳へ行を作る道）。
止める: 行き先が細目の並びの外／その行き先が要る欄が同じ書き込みに無い・空／台帳に作る行に行き先が無い。
  「未定」は書いてよい（行き先を付けるまでの間。終わりの報告は細目 §7 の根治の終わりが照らす）。
射程の外（正直に書く）: 書く中身を JSON の字で持たない形（Python の中で組み立てて送る等）は見えない。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shlex

import guard_common as G

# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}

KEY = "行き先"
NOTION_TOOL = re.compile(r"notion.*(create|update)", re.I)
LEDGER_LINE = re.compile(r"^- \*\*原因の台帳\*\*.*$", re.M)
DEST = re.compile(r"`([^`]+)`（([^（）]*)）")
COL = re.compile(r"欄「([^」]+)」")
OPEN_DEST = re.compile(r"`([^`]+)` の行を残して")
FILE_MAX = 1_000_000


def saimoku_path(guard_root=None):
    return os.environ.get("AF_SAIMOKU") or G.sibling_plugin_file("core", "細目.md", guard_root)


def requires(guard_root=None):
    """細目 §3「原因の台帳」から {行き先: (要る欄…)}。読めない・並びが取れなければ None。"""
    try:
        m = LEDGER_LINE.search(pathlib.Path(saimoku_path(guard_root)).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None
    if not m:
        return None
    out = {}
    for d, inner in DEST.findall(m.group(0)):
        cols = tuple(COL.findall(inner))
        if cols:
            out[d] = cols
    if not out:
        return None
    for d in OPEN_DEST.findall(m.group(0)):
        out.setdefault(d, ())
    return out


def plain(v):
    """Notion の値の形（select・url・rich_text・title・文字）から字を取る。"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "".join(plain(x) for x in v).strip()
    if isinstance(v, dict):
        for k in ("select", "status", "url", "rich_text", "title", "name", "content", "plain_text", "text"):
            if k in v:
                return plain(v[k])
    return ""


def rows(obj, depth=0):
    """入力の中の「行き先」を持つ dict を全部。"""
    if depth > 12:
        return
    if isinstance(obj, dict):
        if KEY in obj:
            yield obj
        for v in obj.values():
            yield from rows(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from rows(v, depth + 1)
    elif isinstance(obj, str) and KEY in obj and "{" in obj:
        for o in json_objects(obj):
            yield from rows(o, depth + 1)


def json_objects(text):
    dec = json.JSONDecoder()
    i = text.find("{")
    while i >= 0:
        try:
            o, end = dec.raw_decode(text, i)
        except ValueError:
            i = text.find("{", i + 1)
            continue
        yield o
        i = text.find("{", end)


def faults(row, req):
    dest = plain(row.get(KEY))
    if dest not in req:
        return ["行き先「%s」は台帳の行き先（%s）の外" % (dest, "・".join(req))]
    return ["行き先「%s」には欄「%s」が要るのに、同じ書き込みに無いか空" % (dest, k)
            for k in req[dest] if not plain(row.get(k))]


def _ids(v):
    """値の中の Notion の id（32 桁の 16 進・- を除いて小文字）を全部。"""
    t = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return {x.lower() for x in re.findall(r"[0-9a-fA-F]{32}", t.replace("-", ""))}


def missing_dest(obj, targets, depth=0):
    """台帳（targets）を親にして作る行で「行き先」の無い物の数。"""
    if depth > 12 or not targets:
        return 0
    n = 0
    if isinstance(obj, dict):
        if "parent" in obj and _ids(obj["parent"]) & targets:
            pages = obj.get("pages") if isinstance(obj.get("pages"), list) else [obj]
            for p in pages:
                props = p.get("properties") if isinstance(p, dict) else None
                if not (isinstance(props, dict) and KEY in props):
                    n += 1
        for v in obj.values():
            n += missing_dest(v, targets, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            n += missing_dest(v, targets, depth + 1)
    return n


def bash_sources(cmd, cwd):
    """Bash の命令の字の中の JSON と、命令が option の値で渡す在る file（--payload x.json・-d @x.json）の中の JSON。"""
    out = list(json_objects(cmd)) if "{" in cmd else []
    try:
        toks = shlex.split(cmd, posix=True)
    except ValueError:
        toks = cmd.split()
    prev = ""
    for t in toks:
        flag_val = prev.startswith("-") or t.startswith("@") or (t.startswith("-") and "=" in t)
        prev = t
        if not flag_val:
            continue                                    # 渡す値の file だけ（cat x.json のような読みは見ない）
        t = t.split("=", 1)[1] if t.startswith("-") and "=" in t else t
        t = t[1:] if t.startswith("@") else t           # curl の -d @file
        p = os.path.expanduser(t)
        if cwd and not os.path.isabs(p):
            p = os.path.join(cwd, p)
        try:
            if not (t and os.path.isfile(p) and os.path.getsize(p) <= FILE_MAX):
                continue
            with open(p, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if "{" in text:
            out += list(json_objects(text))
    return out


def check(data, vals):
    name = str(data.get("tool_name") or "")
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return ""
    if name == "Bash":
        cmd = ti.get("command")
        if not isinstance(cmd, str):
            return ""
        src = bash_sources(cmd, data.get("cwd") or G.project_dir(data) or "")
    elif NOTION_TOOL.search(name):
        src = ti
    else:
        return ""
    found = list(rows(src))
    targets = {x for t in (vals.get("ledger_targets") or []) for x in _ids(str(t))}
    lost = missing_dest(src, targets)
    if not found and not lost:
        return ""
    req = requires()
    if req is None:
        return ("原因の台帳へ書く行を、細目 §3「原因の台帳」の行き先と欄の並びが読めず照らせないので、止めました（%s）。\n"
                "直し方: plugin core を入れ直す（`AF_SAIMOKU` で細目の path を渡せる）。細目の文の `<行き先>`（欄「<名>」…）の形を崩さない。"
                % (saimoku_path() or "細目が見つからない"))
    bad = []
    for r in found:
        bad += faults(r, req)
    if lost:
        bad.append("台帳（値の表 ledger_targets）に作る行 %d 件に「行き先」が無い" % lost)
    if not bad:
        return ""
    how = "／".join("%s → %s" % (d, "・".join("欄「%s」" % c for c in cols) if cols else "欄は要らない")
                   for d, cols in req.items())
    return ("原因の台帳へ書く行の形が崩れているので、Notion へ出すのを止めました。\n"
            + "\n".join("  ✗ " + b for b in bad) + "\n"
            "直し方（skill guard:guard-rules の ledger_row・細目 §3「原因の台帳」）:\n"
            "  行き先ごとに要る欄（細目から読んだ並び）: " + how + "。直さないにするかは AI が決めない（オーナーが決めた理由と決定の記録を書く）。\n"
            "  行き先を変える書き込み・台帳に作る行には、行き先とその行き先が要る欄を同じ書き込みに入れて出し直す。")
