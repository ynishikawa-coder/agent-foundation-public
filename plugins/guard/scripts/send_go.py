"""PreToolUse — 外へ送る命令（skill が宣言した送る口）を、送る物を見せた後の人の go が無いまま打つ手を止める。

なぜ在るか: compose-message は「送る前に go を取る」、make-deck は「外へ入れる前に送信可否を確かめる」を SKILL の文で
  求めるだけで、AI が頼まれた同じターンのうちに送っても何も止めなかった（原因の台帳: してから次への跡を照らさない）。
  社外への送信はオーナーにしか決められない（核 §4）。

正本（写さない）: 送る口は各 skill の SKILL.md の頭（frontmatter）の `send-gate: <正規表現>` が宣言する。
  式の中の `{value:<plugin>.<skill>.<鍵…>}` は repo の値の表の値（字のまま）に置き換える（送る命令が会社ごとの物）。
  値が無い時はその宣言を使わない（送る口が無い＝送らない repo）。見張りの側は送る命令の形を持たない。
go の跡（会話ログを直に読む）: 人の最後の行の前に、その頼みの後の AI の返事（送る物を見せた文）が在る＝人が見せた物に
  答えた後、か、人の最後の行の後に答えの返った選択肢の画面が在る。人の行の無い窓（人のいない窓）は go を取れないので止める。
止まるのは AI の道具の呼び出しだけ。会話ログが読めない時も止める（go を確かめられない送信は出さない）。
"""
from __future__ import annotations

import json
import os
import re

import guard_common as G

# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}

FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
VALUE = re.compile(r"\{value:([\w.-]+)\}")
PLUGINS = ("docs-kit", "dev-flow", "checker", "session-watch", "core")


def _table(data):
    path = os.environ.get("SKILL_VALUES") or ""
    if not path:
        root = G.project_dir(data)
        path = os.path.join(root, G.VALUES_REL) if root else ""
    try:
        with open(path, encoding="utf-8") as f:
            t = json.load(f)
        return t if isinstance(t, dict) else {}
    except Exception:       # noqa: BLE001  （表が無い・読めない＝値で決まる送る口は無い）
        return {}


def _lookup(table, dotted):
    cur = table
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return ""
        cur = cur[k]
    return cur if isinstance(cur, str) else ""


def skill_dirs(guard_root=None):
    """隣の plugin の skills/<名>/SKILL.md の path。AF_SKILLS_ROOTS（: 区切りの plugin の根）で渡せる。"""
    import glob
    env = os.environ.get("AF_SKILLS_ROOTS") or ""
    roots = [r for r in env.split(os.pathsep) if r] if env else []
    if not roots:
        for p in PLUGINS:
            md = G.sibling_plugin_file(p, os.path.join(".claude-plugin", "plugin.json"), guard_root)
            if md:
                roots.append(os.path.dirname(os.path.dirname(md)))
    out = []
    for r in roots:
        out += sorted(glob.glob(os.path.join(r, "skills", "*", "SKILL.md")))
    return out


def gates(data, guard_root=None):
    """(skill の名, 正規表現) の並び。"""
    table = None
    out = []
    for md in skill_dirs(guard_root):
        try:
            with open(md, encoding="utf-8") as f:
                m = FRONT.match(f.read())
        except OSError:
            continue
        if not m:
            continue
        for ln in m.group(1).splitlines():
            k, _, v = ln.partition(":")
            if k.strip() != "send-gate":
                continue
            pat = v.strip()
            if len(pat) >= 2 and pat[0] == pat[-1] == "'":     # YAML の字の囲み（{ で始まる式を囲む）
                pat = pat[1:-1].replace("''", "'")
            if VALUE.search(pat):
                if table is None:
                    table = _table(data)
                vals = [_lookup(table, d) for d in VALUE.findall(pat)]
                if not all(vals):
                    continue
                it = iter(vals)
                pat = VALUE.sub(lambda _m: re.escape(next(it)), pat)
            try:
                out.append((os.path.basename(os.path.dirname(md)), re.compile(pat)))
            except re.error:
                out.append((os.path.basename(os.path.dirname(md)), None))
    return out


def _answered_ask(row):
    """答えの返った選択肢の画面の行か。"""
    r = row.get("toolUseResult")
    return isinstance(r, dict) and isinstance(r.get("answers"), dict) and bool(r["answers"])


def has_go(path):
    """会話ログに go の跡が在るか（True／False）。読めなければ None。"""
    try:
        rows = list(G.iter_rows(path))
    except Exception:       # noqa: BLE001
        return None
    owners = [i for i, r in enumerate(rows) if G.is_owner_row(r)]
    if not owners:
        return False
    last = owners[-1]
    if any(_answered_ask(r) for r in rows[last + 1:]):
        return True
    prev = owners[-2] if len(owners) > 1 else -1
    return any(r.get("type") == "assistant" and G.text_of(r).strip() for r in rows[prev + 1:last])


def check(data, vals):
    if str(data.get("tool_name") or "") != "Bash":
        return ""
    cmd = (data.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return ""
    hit = []
    for name, rx in gates(data):
        if rx is None:
            return ("skill %s の SKILL.md の send-gate（送る口の宣言）が読めない正規表現なので、送る命令かを確かめられず止めました。"
                    "土台の plugin を入れ直すか、その skill の send-gate を直す PR を出す。" % name)
        if rx.search(cmd):
            hit.append(name)
    if not hit:
        return ""
    go = has_go(data.get("transcript_path") or "")
    if go:
        return ""
    why = "会話ログが読めず go を確かめられない" if go is None else "送る物を見せた後の人の go が会話ログに無い"
    return ("外へ送る命令（skill %s の送る口）を、%sので止めました。\n"
            "直し方（skill guard:guard-rules の send_go）:\n"
            "  ① 送る文面・素材（何を・誰へ・どこへ）を返事で見せ、そのターンを締めて人の go を待つ"
            "（選択肢の画面で「送る／直す／送らない」を聞いてもよい）\n"
            "  ② go が返ってから同じ命令を打つ。文面だけ見たい時は送る命令の試しの形（--dry-run など）を使う\n"
            "  人のいない窓は送らず、返し先へ「送る物と go の要る事」を返す。" % ("・".join(hit), why))
