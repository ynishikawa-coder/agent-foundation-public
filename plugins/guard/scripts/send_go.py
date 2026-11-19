"""PreToolUse — 外へ送る命令（skill が宣言した送る口）を、送る物を見せた後の人の go が無いまま打つ手を止める。

なぜ在るか: compose-message は「送る前に go を取る」、make-deck は「外へ入れる前に送信可否を確かめる」を SKILL の文で
  求めるだけで、AI が頼まれた同じターンのうちに送っても何も止めなかった（原因の台帳: してから次への跡を照らさない）。
  社外への送信はオーナーにしか決められない（核 §4）。

正本（写さない）: 送る口は各 skill の SKILL.md の頭（frontmatter）の `send-gate: <正規表現>` が宣言する。
  式の中の `{value:<plugin>.<skill>.<鍵…>}` は repo の値の表の値（字のまま）に置き換える（送る命令が会社ごとの物）。
  値が無い時はその宣言を使わない（送る口が無い＝送らない repo）。見張りの側は送る命令の形を持たない。
go の跡は「送る物」と「人の答え」を結んで見る（どこかで AI が何かを言った、では見ない）:
  - 送る物: 送る口に当たった所より後の引数のうち、在る file（読める字の file は中身・字でない file は名と書いた時刻）と、
    空白を含む引数（命令に直に書いた文）。見分けられなければ止める。
  - 見せた: 会話ログの AI の文が、送る物の中身を全部含む（空白の違いは見ない）。字でない file は、AI の文がその名を書き、
    file がその文より後に書き替わっていない。
  - go: 全部の送る物を見せた後に、人がタイプした行か答えの返った選択肢の画面が在る。人の行は人がタイプした行だけで、
    道具の返り・差し戻し・知らせ（origin の付いた行）は数えない。
  人のいない窓（値の表の unattended_env が真・返し先が別の窓の子の窓）は go を取れないので止める（返し先へ返す）。
止まるのは AI の道具の呼び出しだけ。会話ログが読めない時も止める（go を確かめられない送信は出さない）。
"""
from __future__ import annotations

import json
import os
import re
import shlex

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


def _human(row):
    """人がタイプした行か（道具の返り・差し戻し・知らせ〔origin の付いた行・system の頼み〕を除く）。"""
    if not G.is_owner_row(row):
        return False
    origin = row.get("origin")
    return not (isinstance(origin, dict) and origin.get("kind")) and row.get("promptSource") != "system"


WS = re.compile(r"\s+")


def _norm(t):
    return WS.sub("", t or "")


def materials(tail, cwd):
    """送る口に当たった所より後の命令の字から送る物を取る: [(種類 "text"|"file", 中身か path, 名)]。読めなければ None。"""
    try:
        lex = shlex.shlex(tail, posix=True, punctuation_chars=";&|")
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        return None
    out = []
    for t in toks:
        if t and set(t) <= set(";&|"):
            break                                   # 次の命令（送る命令の引数の外）
        if t.startswith("-"):
            if "=" not in t:
                continue
            t = t.split("=", 1)[1]
        p = os.path.expanduser(t)
        if cwd and not os.path.isabs(p):
            p = os.path.join(cwd, p)
        if t and os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    raw = f.read()
                text = raw.decode("utf-8") if b"\0" not in raw else None
            except (OSError, UnicodeDecodeError):
                text = None
            out.append(("text", text, os.path.basename(p)) if text is not None and text.strip() else ("file", p, os.path.basename(p)))
        elif WS.search(t.strip()):
            out.append(("text", t, "命令に書いた文"))
    return out


def _shown_at(rows, item):
    """送る物を見せた AI の行の位置（最初の 1 つ）か None。"""
    kind, val, _ = item
    if kind == "text":
        want = _norm(val)
    else:
        name = os.path.basename(val)
        try:
            mtime = os.path.getmtime(val)
        except OSError:
            return None
    for i, r in enumerate(rows):
        if r.get("type") != "assistant":
            continue
        t = G.text_of(r)
        if kind == "text":
            if want and want in _norm(t):
                return i
        elif name in t:
            ts = G.parse_ts(r.get("timestamp") or "")
            if ts is not None and mtime <= ts.timestamp():
                return i
    return None


def has_go(path, items):
    """送る物を全部見せた後に人の答えが在るか（True／False）。会話ログが読めなければ None。"""
    try:
        rows = list(G.iter_rows(path))
    except Exception:       # noqa: BLE001
        return None
    at = [_shown_at(rows, it) for it in items]
    if not items or any(i is None for i in at):
        return False
    after = max(at)
    return any(_human(r) or _answered_ask(r) for r in rows[after + 1:])


def check(data, vals):
    if str(data.get("tool_name") or "") != "Bash":
        return ""
    cmd = (data.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return ""
    hit, tails = [], []
    for name, rx in gates(data):
        if rx is None:
            return ("skill %s の SKILL.md の send-gate（送る口の宣言）が読めない正規表現なので、送る命令かを確かめられず止めました。"
                    "土台の plugin を入れ直すか、その skill の send-gate を直す PR を出す。" % name)
        m = rx.search(cmd)
        if m:
            hit.append(name)
            tails.append(cmd[m.end():])
    if not hit:
        return ""
    tpath = data.get("transcript_path") or ""
    if G.unattended_by_env(vals) or G.is_child_prompt(G.first_owner_text(tpath)):
        why = "人のいない窓（返し先が別の窓・夜の自走の印）は人の go を取れない"
    else:
        cwd = data.get("cwd") or G.project_dir(data) or ""
        items = []
        for tail in tails:
            got = materials(tail, cwd)
            items += got or []
            if not got:
                items = None
                break
        go = has_go(tpath, items) if items else False
        if go:
            return ""
        if not items:
            why = "送る物（送る文面の file・命令に書いた文）を命令から見分けられない"
        elif go is None:
            why = "会話ログが読めず go を確かめられない"
        else:
            names = "・".join(n for _, _, n in items)
            why = "送る物（%s）を返事で見せた後の人の go が会話ログに無い" % names
    return ("外へ送る命令（skill %s の送る口）を、%sので止めました。\n"
            "直し方（skill guard:guard-rules の send_go）:\n"
            "  ① 送る文面・素材（何を・誰へ・どこへ）を返事で見せ、そのターンを締めて人の go を待つ"
            "（選択肢の画面で「送る／直す／送らない」を聞いてもよい）。文面は送る file の中身をそのまま全部見せる"
            "（字でない file は名を書く）。見せた後に file を書き替えたら、見せ直して go を取り直す\n"
            "  ② go が返ってから同じ命令を打つ。文面だけ見たい時は送る命令の試しの形（--dry-run など）を使う\n"
            "  人のいない窓は送らず、返し先へ「送る物と go の要る事」を返す。" % ("・".join(hit), why))
