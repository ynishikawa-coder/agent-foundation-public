#!/usr/bin/env python3
"""値の表（使う側の repo の config/skill-values.json）に、土台が読まない鍵が残っていないかを照らす。

なぜ在るか: 土台が鍵を畳む・名を変えると、使う側の値の表に古い鍵が残り、読まれずに黙って効かない
（行き先を変えたつもりで変わらない）。土台は鍵を「無ければ既定で動く」で読むので、どこも赤にならなかった。

知っている鍵の正本（写さない・ここで並べない）:
  - dev-flow・docs-kit … 各 skill の SKILL.md の `## repo ごとの値` の表の 1 列目（`鍵` は <plugin>.<skill>.鍵、
                         `common.…`・`<plugin>.…` で始まる鍵はそのまま）。`.*` で終わる鍵はその下を全部許す。
  - guard              … guard_common.DEFAULTS
  - 他の土台の plugin   … 鍵を持たない（在れば知らない鍵）
照らす所: 頭の鍵が土台の plugin の名か `common` の所だけ。それ以外の頭（repo が自分で持つ所）は見ない。
`_` で始まる鍵（_readme などの注）はどこでも通す。

  values_keys.py [<skill-values.json>]  … 知らない鍵を並べ、在れば exit 1（使う側の CI・手元で回す口）
hook（guard.py から）:
  check(data, vals)     … PreToolUse: Write・Edit・MultiEdit で値の表を書いた後に知らない鍵が残り、
                          書く前より減っていなければ止める（AI の書き込みだけを止める・人の手は止めない）
  resurface(data, vals) … SessionStart: 値の表に知らない鍵が在れば知らせる
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import guard_common as G  # noqa: E402

FOUNDATION = ("core", "checker", "dev-flow", "docs-kit", "guard", "session-watch")
SECTION = re.compile(r"^## repo ごとの値[^\n]*\n(.*?)(?=^## |\Z)", re.M | re.S)
TICK = re.compile(r"`([^`]+)`")
WRITE_TOOLS = ("Write", "Edit", "MultiEdit")


def _plugins_root(guard_root=None):
    """{plugin の名: その plugin の dir}。repo の形（plugins/<名>）と入れた plugin の形（cache/<市場>/<名>/<版>）。"""
    here = guard_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = {}
    parent = os.path.dirname(here)
    if os.path.basename(here) == "guard" and os.path.isdir(os.path.join(parent, "dev-flow")):
        for name in FOUNDATION:
            d = os.path.join(parent, name)
            if os.path.isdir(d):
                out[name] = d
        return out
    ver = os.path.basename(here)
    market = os.path.dirname(os.path.dirname(here))
    for name in FOUNDATION:
        same = os.path.join(market, name, ver)
        if os.path.isdir(same):
            out[name] = same
            continue
        found = sorted(glob.glob(os.path.join(market, name, "*", "")), key=os.path.getmtime, reverse=True)
        if found:
            out[name] = found[0].rstrip(os.sep)
    return out


def _keys_of_skill(plugin, skill, text):
    """SKILL.md の `## repo ごとの値` の表の 1 列目から、知っている鍵の path（tuple）を返す。"""
    m = SECTION.search(text)
    if not m:
        return set()
    keys = set()
    for line in m.group(1).splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = line.strip().strip("|").split("|")
        for tok in TICK.findall(cells[0]):
            tok = tok.strip()
            if not tok or "<" in tok or tok == "鍵":
                continue
            parts = tok.split(".")
            if parts[0] == "common" or (parts[0] == plugin and len(parts) > 1 and parts[1] == skill):
                keys.add(tuple(parts))
            else:
                keys.add((plugin, skill, *parts))
    return keys


def known_keys(guard_root=None):
    """(知っている鍵の path の集まり, 照らす頭の集まり, 照らせなかった plugin の並び)。"""
    roots = _plugins_root(guard_root)
    keys, frames = set(), set()
    for name, d in roots.items():
        for md in sorted(glob.glob(os.path.join(d, "skills", "*", "SKILL.md"))):
            skill = os.path.basename(os.path.dirname(md))
            frames.add((name, skill))                    # skill の枠そのもの（中の鍵は表で照らす）
            with open(md, encoding="utf-8") as f:
                keys |= _keys_of_skill(name, skill, f.read())
    keys |= {("guard", k) for k in G.DEFAULTS}
    frames |= {k[:i] for k in keys for i in range(1, len(k))}
    heads = {"common", *roots}
    missing = [n for n in FOUNDATION if n not in roots]
    return keys, frames, heads, missing


def _leaf(path, keys):
    """path（tuple）が知っている鍵か、その下（`.*` か値の中）か。"""
    return any(path[:len(b)] == b for b in ((k[:-1] if k[-1] == "*" else k) for k in keys))


def unknown(table, known=None):
    """値の表（dict）の中の、土台が読まない鍵（`a.b.c` の文字列）の並び。"""
    keys, frames, heads, _ = known or known_keys()
    out = []

    def walk(node, path):
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            if str(k).startswith("_"):
                continue
            p = path + (str(k),)
            if _leaf(p, keys):
                continue                                 # 知っている鍵（値の中は見ない）
            if p in frames:
                walk(v, p)                               # 知っている鍵の上の枠＝中を照らす
            else:
                out.append(".".join(p))

    if isinstance(table, dict):
        for head, v in table.items():
            if head in heads:
                walk(v, (head,)) if isinstance(v, dict) else None
    return out


def _is_values_path(path):
    path = (path or "").replace("\\", "/")
    return path.endswith("/" + G.VALUES_REL.replace(os.sep, "/")) or path == G.VALUES_REL.replace(os.sep, "/")


def _after(tool, inp, before_text):
    """書いた後の中身（読めなければ None）。"""
    if tool == "Write":
        return inp.get("content") if isinstance(inp.get("content"), str) else None
    if before_text is None:
        return None
    edits = inp.get("edits") if tool == "MultiEdit" else [inp]
    text = before_text
    for e in edits or []:
        old, new = e.get("old_string"), e.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str) or old not in text:
            return None
        text = text.replace(old, new) if e.get("replace_all") else text.replace(old, new, 1)
    return text


def _load(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def _say(keys, where):
    return ("値の表 %s に、土台が読まない鍵が在る（土台が畳んだ・名を変えた鍵か、書き違い）。読まれずに黙って効かない:\n%s\n"
            "直し方: 消すか、今の名の鍵へ移す（今の鍵は各 skill の SKILL.md の「repo ごとの値」の表と guard の値）。"
            "repo が自分で持つ値なら、土台の plugin の名と common の外の頭へ移す。この repo の PR で直す（skill `guard:guard-rules`）。"
            "土台の道具が今も読む鍵なのに表に行が無いだけなら、値の表は直さず、土台の repo でその skill の SKILL.md の「repo ごとの値」の表に行を足す PR を出す。"
            "古い鍵が残った訳（土台を直した仕事が使う側の値の表まで届かなかった等）は、細目 §3「まず構造を疑う」で原因から直す。"
            % (where, "\n".join("  - " + k for k in keys)))


def check(data, vals):
    tool = data.get("tool_name") or ""
    inp = data.get("tool_input") or {}
    if tool not in WRITE_TOOLS or not isinstance(inp, dict):
        return ""
    path = inp.get("file_path") or ""
    if not _is_values_path(path):
        return ""
    if not os.path.isabs(path):
        path = os.path.join(data.get("cwd") or G.project_dir(data) or os.getcwd(), path)
    before_text = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            before_text = f.read()
    after_text = _after(tool, inp, before_text)
    if after_text is None:
        return ""                                        # 書き換えが当たらない＝道具の側で失敗する
    after = _load(after_text)
    if after is None:
        return "値の表 %s が JSON として読めない形になる。土台の道具は読めない値の表を黙って既定で動くので、JSON の形を直してから書く。" % path
    known = known_keys()
    now = unknown(after, known)
    if not now:
        return ""
    was = unknown(_load(before_text) or {}, known) if before_text else []
    if set(now) < set(was):
        return ""                                        # 知らない鍵を減らす書き込みは通す（片付けの途中）
    return _say(now, path)


def resurface(data, vals):
    root = G.project_dir(data)
    path = os.environ.get("SKILL_VALUES") or (os.path.join(root, G.VALUES_REL) if root else "")
    if not path or not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        table = _load(f.read())
    if table is None:
        return "値の表 %s が JSON として読めない（土台の道具は黙って既定で動いている）。この repo の PR で直す。" % path
    keys = unknown(table)
    return _say(keys, path) if keys else ""


def main(argv):
    path = argv[1] if len(argv) > 1 else G.VALUES_REL
    try:
        with open(path, encoding="utf-8") as f:
            table = json.load(f)
    except Exception as e:      # noqa: BLE001
        print("値の表 %s が読めない: %s" % (path, e))
        return 1
    known = known_keys()
    if known[3]:
        print("土台の plugin が見つからず照らせない頭: %s" % ", ".join(known[3]))
    keys = unknown(table, known)
    if keys:
        print(_say(keys, path))
        return 1
    print("値の表 %s: 知らない鍵 0" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
