"""PreToolUse — 原因の台帳へ書く行の形を、Notion へ出る前に照らし、崩れていれば AI だけを止める。

なぜ在るか: 台帳の 1 行の形（行き先と、その行き先が要る欄）は細目 §3「原因の台帳」の文だけで、Notion へ書く道具には
  何も当たらず、行き先に要る欄の欠けた行（理由の無い「直さない」・URL の無い「直す窓」）が入りえた。
正本: 細目 §3「原因の台帳」— 行き先は `直す窓`（その窓の URL）／`直した`（直しの所在）／`直さない`（オーナーが決めた理由と
  決定の記録）。下の REQUIRES はその文の欄の名を指すだけ（行き先の語と欄の名は台帳の列の名と同じ）。
見分け: Notion へ書く道具（MCP の notion の作る・直す道具と、Bash の api.notion.com への curl の JSON）の入力の中で、
  「行き先」の鍵を持つ物＝台帳の行（台帳の id を値で持たない＝どの会社の台帳でも同じ列の名で当たる）。
止める: 行き先が上の 3 つと「未定」の外／その行き先が要る欄が同じ書き込みに無い・空。
  「未定」は書いてよい（行き先を付けるまでの間。終わりの報告は細目 §7 の根治の終わりが照らす）。
射程の外（正直に書く）: 書く中身を JSON の字で持たない形（Python の中で組み立てて送る等）は見えない。
"""
from __future__ import annotations

import json
import re

# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}

KEY = "行き先"
# 行き先ごとに同じ書き込みに要る欄（細目 §3「原因の台帳」の文の欄）
REQUIRES = {"直す窓": ("直す窓",), "直した": ("直し",), "直さない": ("直さない理由", "決定"), "未定": ()}
NOTION_TOOL = re.compile(r"notion.*(create|update).*(page|row)|notion-(create-pages|update-page)", re.I)


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


def faults(row):
    dest = plain(row.get(KEY))
    if dest not in REQUIRES:
        return ["行き先「%s」は台帳の行き先（直す窓・直した・直さない・未定）の外" % dest]
    return ["行き先「%s」には欄「%s」が要るのに、同じ書き込みに無いか空" % (dest, k)
            for k in REQUIRES[dest] if not plain(row.get(k))]


def check(data, vals):
    name = str(data.get("tool_name") or "")
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return ""
    if name == "Bash":
        cmd = ti.get("command")
        if not (isinstance(cmd, str) and "api.notion.com" in cmd and KEY in cmd):
            return ""
        src = cmd
    elif NOTION_TOOL.search(name):
        src = ti
    else:
        return ""
    bad = []
    for r in rows(src):
        bad += faults(r)
    if not bad:
        return ""
    return ("原因の台帳へ書く行の形が崩れているので、Notion へ出すのを止めました。\n"
            + "\n".join("  ✗ " + b for b in bad) + "\n"
            "直し方（skill guard:guard-rules の ledger_row・細目 §3「原因の台帳」）:\n"
            "  直す窓 → 欄「直す窓」にその窓の URL／直した → 欄「直し」に直しの所在（PR など）／"
            "直さない → 欄「直さない理由」にオーナーが決めた理由と、欄「決定」に決定の記録（AI は直さないを決めない）。\n"
            "  行き先を変える書き込みには、その行き先が要る欄を同じ書き込みに入れて出し直す。")
