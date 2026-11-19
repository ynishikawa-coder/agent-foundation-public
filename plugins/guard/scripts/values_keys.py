#!/usr/bin/env python3
"""値の表（使う側の repo の config/skill-values.json）に、土台が読まない鍵が残っていないかを照らす。

なぜ在るか: 土台が鍵を畳む・名を変えると、使う側の値の表に古い鍵が残り、読まれずに黙って効かない
（行き先を変えたつもりで変わらない）。土台は鍵を「無ければ既定で動く」で読むので、どこも赤にならなかった。

知っている鍵の正本（写さない・ここで並べない）: 値の表の 1 本の口 lib/skill_values.py と鍵の一覧 lib/schema.json
（＝土台の skill-values/ の正本への symlink）。照らしも同じ口の check を呼ぶ: 土台の欄（plugin の名と common）の
知らない鍵・畳んだ鍵（retired・理由と直し方つき）・型の違う値を名指す。repo 自身の欄と `_` で始まる注は見ない。
SKILL.md の「repo ごとの値」の表と鍵の一覧のずれは土台の試験（tests/test_skill_values.py）が両向きに照らす。

  values_keys.py [<skill-values.json>]  … 問題の鍵を並べ、在れば exit 1（使う側の CI・手元で回す口）
hook（guard.py から）:
  check(data, vals)     … PreToolUse: Write・Edit・MultiEdit で値の表を書いた後に問題の鍵が残り、
                          書く前より減っていなければ止める（AI の書き込みだけを止める・人の手は止めない）
  resurface(data, vals) … SessionStart: 値の表の問題（guard_common.values_problems＝問題の鍵と、guard の値の読めない中身・
                          古い形の跡）が在れば知らせる（止めない）
"""
from __future__ import annotations

import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import guard_common as G  # noqa: E402

SV = G.SV                                                # 値の表の 1 本の口（guard_common が lib/ から読む）
WRITE_TOOLS = ("Write", "Edit", "MultiEdit")
HOOKS = {"pre": "check", "start": "resurface"}


def unknown(table):
    """値の表（dict）の土台の欄の問題（「<鍵の path> は …」の文）の並び。正本は lib/skill_values.py の check。"""
    return SV.check(table) if isinstance(table, dict) else []


def _is_values_path(path):
    path = (path or "").replace("\\", "/")
    return path.endswith("/" + SV.REL_PATH.replace(os.sep, "/")) or path == SV.REL_PATH.replace(os.sep, "/")


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
    return ("値の表 %s に、土台が読まない鍵が在る（土台が畳んだ・名を変えた鍵か、書き違い・型の違う値）。読まれずに黙って効かない:\n%s\n"
            "直し方: 消すか、今の名の鍵へ移す（今の鍵の一覧の正本は土台の skill-values/schema.json・各 skill の SKILL.md の「repo ごとの値」の表と同じ）。"
            "repo が自分で持つ値なら、土台の plugin の名と common の外の頭へ移す。この repo の PR で直す（skill `guard:guard-rules`）。"
            "土台の道具が今も読む鍵なのに一覧に無いだけなら、値の表は直さず、土台の repo で skill-values/schema.json とその skill の SKILL.md の表に行を足す PR を出す。"
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
    now = unknown(after)
    if not now:
        return ""
    was = unknown(_load(before_text) or {}) if before_text else []
    if set(now) < set(was):
        return ""                                        # 知らない鍵を減らす書き込みは通す（片付けの途中）
    return _say(now, path)


def resurface(data, vals):
    path = SV.find(starts=G._starts(data))
    if not path:
        return ""
    table, problems = SV.load(path)
    if problems:
        return "値の表 %s が読めない（%s）。土台の道具は止まり、守りは既定で動いている。この repo の PR で直す。" % (path, "・".join(problems))
    keys = unknown(table)
    out = [_say(keys, path)] if keys else []
    faults = [f for f in G.values_problems(data)[1] if f not in keys]     # 名指しの 1 か所（guard_common.values_problems）
    if faults:
        out.append("値の表 %s の guard に、読めずに黙って効かない値か古い形の値が在る（見張りは読めない値を数えずに動いている）:\n%s\n"
                   "直し方: 形を直す PR を出す（形は skill `guard:guard-rules` の値の表）。壊れた値・古い形が残った訳は細目 §3"
                   "「まず構造を疑う」で原因から直す。" % (path, "\n".join("  - " + f for f in faults)))
    return "\n\n".join(out)


def main(argv):
    path = argv[1] if len(argv) > 1 else SV.REL_PATH
    try:
        with open(path, encoding="utf-8") as f:
            table = json.load(f)
    except Exception as e:      # noqa: BLE001
        print("値の表 %s が読めない: %s" % (path, e))
        return 1
    keys = unknown(table)
    if keys:
        print(_say(keys, path))
        return 1
    print("値の表 %s: 問題の鍵 0" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
