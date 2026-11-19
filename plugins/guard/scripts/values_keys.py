#!/usr/bin/env python3
"""値の表（使う側の repo の config/skill-values.json）に、土台が読まない鍵が残っていないかを照らす。

なぜ在るか: 土台が鍵を畳む・名を変えると、使う側の値の表に古い鍵が残り、読まれずに黙って効かない
（行き先を変えたつもりで変わらない）。土台は鍵を「無ければ既定で動く」で読むので、どこも赤にならなかった。

知っている鍵の正本（写さない・ここで並べない）: 値の表の 1 本の口 lib/skill_values.py と鍵の一覧 lib/schema.json
（＝土台の skill-values/ の正本への symlink）。照らしも同じ口の check を呼ぶ: 土台の欄（plugin の名と common）の
知らない鍵・畳んだ鍵（retired・理由と直し方つき）・型の違う値を名指す。repo 自身の欄と `_` で始まる注は見ない。
SKILL.md の「repo ごとの値」の表と鍵の一覧のずれは土台の試験（tests/test_skill_values.py）が両向きに照らす。

  values_keys.py [<skill-values.json>]  … 問題の鍵を並べ、在れば exit 1（使う側の CI・手元で回す口）
  values_keys.py --keys <plugin> [<skill>] … その枠で読んでよい鍵を JSON で出す（正本は lib/skill_values.py keys）
hook（guard.py から）:
  check(data, vals)     … PreToolUse: Write・Edit・MultiEdit で値の表を書いた後に問題の鍵が残り、
                          書く前より減っていなければ止める（AI の書き込みだけを止める・人の手は止めない）。
                          どの道具でも、値の表の中身の控えを窓の一時の置き場に取る（下の after が照らす）。
  after(data, vals)     … PostToolUse: どの道具（Bash の sed -i・リダイレクト・python -c・他の道具）でも、道具の前の控えと
                          比べて値の表が変わり、問題の鍵が残って減っていなければ、元へ戻すよう強く知らせる
                          （書き方の字の形を並べない＝道具の前と後の中身で照らす。hook は AI の道具にだけ回る＝人の手は照らさない。
                          書いた後なので止めずに戻させる）
  resurface(data, vals) … SessionStart: 値の表に問題の鍵が在れば知らせる（止めない）
読み口（土台の道具が値の表を読む時は全部ここを通す・写さない）:
  section(data, plugin, skill)  … 値の表の 1 つの枠（dict）を、鍵の一覧に載った鍵だけを読ませる G.Strict にして返す。
                                  一覧に無い鍵を読むと実行の時に G.UnknownKey で止まる。鍵の一覧は lib/skill_values.py の frame_keys。
  require(path)                 … 鍵の path（tuple）が一覧に載っていなければ G.UnknownKey（1 つずつ引く読み口が使う）。
  他の plugin の Python の道具（dev-flow の codex_pack.py・spec-doc の seal.py）は、探す・読み込むのを自分の lib/skill_values.py で
  済ませ、読んだ欄をこの file の section で包む（この file を隣の plugin〔repo の形 plugins/guard・入れた plugin の形
  cache/<市場>/guard/<版>〕から直に読む）。make-deck は lib/skill_values.py の get（引く前に require で照らす）、
  qa-html の check.mjs は lib/skill_values.py keys の鍵の一覧で読み口（Proxy）を作る。
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import guard_common as G  # noqa: E402

SV = G.SV                                                # 値の表の 1 本の口（guard_common が lib/ から読む）
WRITE_TOOLS = ("Write", "Edit", "MultiEdit")
HOOKS = {"pre": "check", "post": "after", "start": "resurface"}
SNAP_TTL = 6 * 3600   # 道具が失敗して後の照らしが回らなかった控えを残す長さ（秒）


def unknown(table):
    """値の表（dict）の土台の欄の問題（「<鍵の path> は …」の文）の並び。正本は lib/skill_values.py の check。"""
    return SV.check(table) if isinstance(table, dict) else []


def frame_keys(frame):
    """枠（tuple）の中で読んでよい鍵の名の集まりと、中の名を repo が決める枠か（正本は lib/skill_values.py）。"""
    return SV.frame_keys(frame)


def section(data, *frame):
    """値の表の 1 つの枠を、鍵の一覧に載った鍵だけを読ませる読み口にして返す（data が dict でなければ空の枠）。"""
    names, any_key = frame_keys(frame)
    return G.Strict(data if isinstance(data, dict) else {}, frame, names, any_key)


def require(path):
    """鍵の path が鍵の一覧に載った鍵（かその下）でなければ G.UnknownKey（正本は lib/skill_values.py）。"""
    SV.require(path)


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
    try:
        _snap(data, vals)        # どの道具でも控える（止めない・壊れても下の照らしは回す）
    except Exception as e:      # noqa: BLE001
        sys.stderr.write("[guard] values_keys の控え: %s\n" % e)
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


def _table_path(data):
    """控えと照らしの値の表の path か ""。探し方は値の表の 1 本の口。表がまだ無い時は窓の repo の根の置き場
    （道具が値の表を新しく作るのも照らす）。"""
    found = SV.find(starts=G._starts(data))
    if found:
        return found
    root = G.project_dir(data)
    return os.path.join(root, SV.REL_PATH) if root else ""


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _snap_dir(data):
    return os.path.join(G.tmp_dir("values_keys"), G.safe_id(data.get("session_id") or "no-session"))


def _snaps_in(d):
    """控えの置き場の *.json の path の並び。"""
    try:
        return [os.path.join(d, n) for n in os.listdir(d) if n.endswith(".json")]
    except OSError:
        return []


def _snap(data, vals):
    """道具の前の値の表の中身を控える（道具ごとに 1 つ。窓の中だけ）。"""
    path = _table_path(data)
    if not path:
        return
    d = _snap_dir(data)
    os.makedirs(d, exist_ok=True)
    now = time.time()
    for old in _snaps_in(d):
        try:
            if now - os.path.getmtime(old) > SNAP_TTL:
                os.remove(old)
        except OSError:
            pass
    name = G.safe_id(data.get("tool_use_id") or "") or "no-tool-use"
    with open(os.path.join(d, name + ".json"), "w", encoding="utf-8") as f:
        json.dump({"path": path, "text": _read(path), "at": now}, f, ensure_ascii=False)


def after(data, vals):
    """道具の後: 控えの中で一番古い物（失敗して後の照らしが回らなかった道具の前も含む）と今の中身を比べる。"""
    path = _table_path(data)
    d = _snap_dir(data)
    if not path or not os.path.isdir(d):
        return ""
    snaps = []
    for p in _snaps_in(d):
        try:
            with open(p, encoding="utf-8") as f:
                s = json.load(f)
            if s.get("path") == path:
                snaps.append((s.get("at") or 0, p, s))
        except Exception:      # noqa: BLE001
            continue
    if not snaps:
        return ""
    snaps.sort(key=lambda x: x[0])
    before = snaps[0][2].get("text")
    mine = os.path.join(d, (G.safe_id(data.get("tool_use_id") or "") or "no-tool-use") + ".json")
    mine_at = next((at for at, p, _s in snaps if p == mine), None)
    now_text = _read(path)
    msg = "" if now_text == before else _judge(before, now_text, path)
    if msg:
        return ("AI の道具（%s）の間に値の表が書き換わった。%s\n"
                "書いた後なので止めていない: この道具で書いた物なら、今すぐ元へ戻す（`git diff -- %s` で見て、"
                "`git checkout -- %s` か書き直しで知らない鍵を残さない形にする）。人が書いた物なら戻さず人に知らせる。"
                % (data.get("tool_name") or "?", msg, path, path))
    if mine_at is not None:   # 照らしが済んだ＝この道具と、それより前の控えは要らない（後に始まった道具の控えは残す）
        for at, p, _s in snaps:
            if at <= mine_at:
                _drop(p)
    return ""


def _drop(p):
    try:
        os.remove(p)
    except OSError:
        pass


def _judge(before_text, now_text, path):
    """道具の前後の中身から、知らせる文か ""（Write・Edit の止めと同じ線: 知らない鍵が残り、減っていなければ）。"""
    if now_text is None:
        return ""
    now = _load(now_text)
    if now is None:
        return "値の表 %s が JSON として読めない形になった（土台の道具は読めない値の表を黙って既定で動く）。" % path
    keys = unknown(now)
    if not keys:
        return ""
    was = unknown(_load(before_text) or {}) if before_text else []
    if set(keys) < set(was):
        return ""
    return _say(keys, path)


def resurface(data, vals):
    path = SV.find(starts=G._starts(data))
    if not path:
        return ""
    table, problems = SV.load(path)
    if problems:
        return "値の表 %s が読めない（%s）。土台の道具は止まり、守りは既定で動いている。この repo の PR で直す。" % (path, "・".join(problems))
    keys = unknown(table)
    return _say(keys, path) if keys else ""


def main(argv):
    if len(argv) > 2 and argv[1] == "--keys":
        names, any_key = frame_keys(tuple(argv[2:]))
        print(json.dumps({"frame": argv[2:], "keys": sorted(names), "any": any_key}, ensure_ascii=False))
        return 0
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
