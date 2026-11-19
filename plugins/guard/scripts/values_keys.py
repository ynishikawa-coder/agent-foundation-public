#!/usr/bin/env python3
"""値の表（使う側の repo の config/skill-values.json）に、土台が読まない鍵が残っていないかを照らす。

なぜ在るか: 土台が鍵を畳む・名を変えると、使う側の値の表に古い鍵が残り、読まれずに黙って効かない
（行き先を変えたつもりで変わらない）。土台は鍵を「無ければ既定で動く」で読むので、どこも赤にならなかった。

知っている鍵の正本（写さない・ここで並べない）: 値の表の 1 本の口 lib/skill_values.py と鍵の一覧 lib/schema.json
（＝土台の skill-values/ の正本への symlink）。照らしも同じ口の check を呼ぶ: 土台の欄（plugin の名と common）の
知らない鍵・畳んだ鍵（retired・理由と直し方つき）・型の違う値を名指す。repo 自身の欄と `_` で始まる注は見ない。
SKILL.md の「repo ごとの値」の表と鍵の一覧のずれは土台の試験（tests/test_skill_values.py）が両向きに照らす。

  values_keys.py [<skill-values.json>]  … 問題の鍵を並べ、在れば exit 1（使う側の CI・手元で回す口）
値の表の path は自分で組まず、1 本の口の find（--values・SKILL_VALUES・$CLAUDE_PROJECT_DIR からの探し）で引く。
書く手は道具の名で見ず、入力の形で見る（content を持つ＝丸ごと書く・old_string/edits を持つ＝書き換える）。
Bash は読み手（cmd_read）の語で「どこへ書くか」を読む（paid_upstream.bash_writes）。

hook（guard.py から）:
  check(data, vals)     … PreToolUse: 値の表を書いた後に問題の鍵が残り、書く前より減っていなければ止める。
                          Bash で値の表へ確かに書く形（> の的・-i の段・of= の的）は、書いた後の中身を照らせないので止め、
                          Write・Edit で書かせる（AI の書き込みだけを止める・人の手は止めない）
  after_bash(data, vals) … PostToolUse: 読むだけでない Bash が値の表を指した後、表に問題の鍵が在れば知らせる
                          （python -c の open など、書くかもしれない形の受け口・止めない）
  resurface(data, vals) … SessionStart: 値の表に問題の鍵が在れば知らせる（止めない）
"""
from __future__ import annotations

import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cmd_read as R  # noqa: E402
import guard_common as G  # noqa: E402
import paid_upstream as PU  # noqa: E402  Bash が書く先の読み（bash_writes）

SV = G.SV                                                # 値の表の 1 本の口（guard_common が lib/ から読む）
HOOKS = {"pre": "check", "post": "after_bash", "start": "resurface"}


def unknown(table):
    """値の表（dict）の土台の欄の問題（「<鍵の path> は …」の文）の並び。正本は lib/skill_values.py の check。"""
    return SV.check(table) if isinstance(table, dict) else []


def _abs(path, data):
    path = os.path.expanduser(path or "")
    return os.path.realpath(os.path.join(data.get("cwd") or G.project_dir(data) or os.getcwd(), path))


def _is_values_path(path, data):
    """path が値の表か: この窓が読む表（1 本の口の find）か、その場所から find が引く表（別の repo の表も）。"""
    if not isinstance(path, str) or not path.strip():
        return False
    p = _abs(path, data)
    found = SV.find(starts=G._starts(data))
    if found and os.path.realpath(found) == p:
        return True
    near = SV.find(starts=[os.path.dirname(os.path.dirname(p))], env={})
    if near and os.path.realpath(near) == p:
        return True
    return p.endswith(os.sep + SV.REL_PATH)                # まだ無い表を新しく書く時（find が探す場所の形）


def _after(inp, before_text):
    """書いた後の中身（読めなければ None）。道具の名でなく入力の形で読む: content＝丸ごと・edits／old_string＝書き換え。"""
    if isinstance(inp.get("content"), str):
        return inp["content"]
    if before_text is None:
        return None
    edits = inp.get("edits") if isinstance(inp.get("edits"), list) else [inp]
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


def _bash_values(data, sure_only):
    cmd = (data.get("tool_input") or {}).get("command") if isinstance(data.get("tool_input"), dict) else None
    if not isinstance(cmd, str):
        return []
    sure, maybe = PU.bash_writes(cmd)
    cands = sure if sure_only else sure + maybe
    found = SV.find(starts=G._starts(data))
    names = {os.path.basename(SV.REL_PATH)} | ({os.path.basename(found)} if found else set())
    return [t for t in dict.fromkeys(cands) if os.path.basename(t) in names and _is_values_path(t, data)]


def check(data, vals):
    inp = data.get("tool_input") or {}
    if not isinstance(inp, dict):
        return ""
    if data.get("tool_name") == "Bash":
        hit = _bash_values(data, sure_only=True)
        if not hit:
            return ""
        return ("値の表 %s へ Bash で書く形は、書いた後の中身を照らせない（土台が読まない鍵が黙って残る道）。"
                "Write か Edit で書く（書いた後の中身を土台の鍵の一覧で照らしてから通す）。" % hit[0])
    path = inp.get("file_path") or inp.get("path") or ""
    if not _is_values_path(path, data):
        return ""
    path = _abs(path, data)
    before_text = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            before_text = f.read()
    after_text = _after(inp, before_text)
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


def after_bash(data, vals):
    """読むだけでない Bash が値の表を指した後、表に問題の鍵が残っていれば知らせる。"""
    if data.get("tool_name") != "Bash":
        return ""
    cmd = (data.get("tool_input") or {}).get("command") if isinstance(data.get("tool_input"), dict) else None
    if not isinstance(cmd, str) or R.inert(cmd):
        return ""
    for t in _bash_values(data, sure_only=False):
        table, problems = SV.load(_abs(t, data))
        keys = problems + unknown(table)
        if keys:
            return _say(keys, _abs(t, data))
    return ""


def resurface(data, vals):
    path, problems = G.values_problems(data)             # 表の探し方は guard_common の 1 本の口（読む順を写さない）
    return _say(problems, path) if problems else ""


def main(argv):
    path = SV.find(explicit=argv[1] if len(argv) > 1 else None)     # --values 相当・SKILL_VALUES・$CLAUDE_PROJECT_DIR・今の dir
    if not path:
        print("値の表が見つからない（探した: SKILL_VALUES・$CLAUDE_PROJECT_DIR と今の dir から上の %s）＝鍵は全部既定" % SV.REL_PATH)
        return 0
    table, problems = SV.load(path)
    keys = problems + unknown(table)
    if keys:
        print(_say(keys, path))
        return 1
    print("値の表 %s: 問題の鍵 0" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
