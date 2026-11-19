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
  values_keys.py --keys <plugin> [<skill>] … その枠で読んでよい鍵を JSON で出す（JS の道具の読み口が使う）
hook（guard.py から）:
  check(data, vals)     … PreToolUse: Write・Edit・MultiEdit で値の表を書いた後に知らない鍵が残り、
                          書く前より減っていなければ止める（AI の書き込みだけを止める・人の手は止めない）。
                          どの道具でも、値の表の中身の控えを窓の一時の置き場に取る（下の after が照らす）。
  after(data, vals)     … PostToolUse: どの道具（Bash の sed -i・リダイレクト・python -c・他の道具）でも、道具の前の控えと
                          比べて値の表が変わり、知らない鍵が残って減っていなければ、元へ戻すよう強く知らせる
                          （書き方の字の形を並べない＝道具の前と後の中身で照らす。hook は AI の道具にだけ回る＝人の手は照らさない。
                          書いた後なので止めずに戻させる）
  resurface(data, vals) … SessionStart: 値の表に知らない鍵が在れば知らせる
読み口（土台の道具が値の表を読む時は全部ここを通す・写さない）:
  section(data, plugin, skill)  … 値の表の 1 つの枠（dict）を、表に載った鍵だけを読ませる G.Strict にして返す。
                                  表に無い鍵を読むと実行の時に G.UnknownKey で止まる。
  require(path)                 … 鍵の path（tuple）が表に載っていなければ G.UnknownKey（1 つずつ引く読み口が使う）。
  他の plugin の道具（dev-flow の codex_pack.py・spec-doc の seal.py、docs-kit の skill_values.py・qa-html の check.mjs）は、
  この file を隣の plugin（repo の形 plugins/guard・入れた plugin の形 cache/<市場>/guard/<版>）から直に読む。
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import guard_common as G  # noqa: E402

FOUNDATION = ("core", "checker", "dev-flow", "docs-kit", "guard", "session-watch")
SECTION = re.compile(r"^## repo ごとの値[^\n]*\n(.*?)(?=^## |\Z)", re.M | re.S)
TICK = re.compile(r"`([^`]+)`")
WRITE_TOOLS = ("Write", "Edit", "MultiEdit")
HOOKS = {"pre": "check", "post": "after", "start": "resurface"}
SNAP_TTL = 6 * 3600   # 道具が失敗して後の照らしが回らなかった控えを残す長さ（秒）


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


def frame_keys(frame, known=None):
    """枠（tuple）の中で読んでよい鍵の名の集まりと、`.*` の枠か。"""
    keys = (known or known_keys())[0]
    frame = tuple(frame)
    n = len(frame)
    names = {k[n] for k in keys if len(k) > n and k[:n] == frame}
    return names - {"*"}, "*" in names


def section(data, *frame, known=None):
    """値の表の 1 つの枠を、表に載った鍵だけを読ませる読み口にして返す（data が dict でなければ空の枠）。"""
    names, any_key = frame_keys(frame, known)
    return G.Strict(data if isinstance(data, dict) else {}, frame, names, any_key)


def require(path, known=None):
    """鍵の path が表に載った鍵（かその下）でなければ G.UnknownKey。"""
    path = tuple(path)
    if not _leaf(path, (known or known_keys())[0]):
        raise G.UnknownKey("値の表に無い鍵 %s を読んだ（読む鍵は SKILL.md の「repo ごとの値」の表に行を足してから読む）"
                           % ".".join(path))


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
    known = known_keys()
    now = unknown(after, known)
    if not now:
        return ""
    was = unknown(_load(before_text) or {}, known) if before_text else []
    if set(now) < set(was):
        return ""                                        # 知らない鍵を減らす書き込みは通す（片付けの途中）
    return _say(now, path)


def _table_path(data):
    root = G.project_dir(data)
    return os.environ.get("SKILL_VALUES") or (os.path.join(root, G.VALUES_REL) if root else "")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _snap_dir(data):
    return os.path.join(G.tmp_dir("values_keys"), G.safe_id(data.get("session_id") or "no-session"))


def _snap(data, vals):
    """道具の前の値の表の中身を控える（道具ごとに 1 つ。窓の中だけ）。"""
    path = _table_path(data)
    if not path:
        return
    d = _snap_dir(data)
    os.makedirs(d, exist_ok=True)
    now = time.time()
    for old in glob.glob(os.path.join(d, "*.json")):
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
    for p in glob.glob(os.path.join(d, "*.json")):
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
    known = known_keys()
    keys = unknown(now, known)
    if not keys:
        return ""
    was = unknown(_load(before_text) or {}, known) if before_text else []
    if set(keys) < set(was):
        return ""
    return _say(keys, path)


def resurface(data, vals):
    path = _table_path(data)
    if not path or not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        table = _load(f.read())
    if table is None:
        return "値の表 %s が JSON として読めない（土台の道具は黙って既定で動いている）。この repo の PR で直す。" % path
    keys = unknown(table)
    return _say(keys, path) if keys else ""


def main(argv):
    if len(argv) > 2 and argv[1] == "--keys":
        names, any_key = frame_keys(tuple(argv[2:]))
        print(json.dumps({"frame": argv[2:], "keys": sorted(names), "any": any_key}, ensure_ascii=False))
        return 0
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
