"""PreToolUse — 問いが答えのないまま閉じ、オーナーが席を外している間、戻せない操作を止める。

窓は狭い: 止まるのは ①この窓（セッション）で問いが答えのないまま閉じ ②まだオーナーが戻っていない 間だけ。
  答えが 1 つでも返れば閉じる。オーナーが何か打てば閉じる（会話ログの人の行で判定）。持ち越した問いは窓を開けない。

止めるのは 4 つだけ: DB の破棄・メールの送信・Notion の物理削除・git で戻せない再帰の削除（rm -r）。
  強制 push・main への push・本番への出荷・sudo は、オーナーが居ても居なくても settings の permissions.deny の受け持ち（ここでは重ねない）。
  rm -r は消す先ごとに見て、どれも次のどれかなら通す: 在らない／一時の置き場（作業場）の中／git に全部記録済み
  （未記録の変更・未追跡・ignore の物が無い）／変更の無い git の作業部屋（worktree）。`cd` は追って場所を変え、glob は展開して見る。
  判定できない時（展開 `$(`・変数・rm が区切りの先頭に無い〔`| xargs rm`・`sudo rm`〕・在らない先への cd・
  rm より前に cd 以外の命令がある〔`mv keep gone && rm -rf gone`〕）は止める側に倒す。

射程の天井: 判定は列挙であって証明ではない（`find … -delete`・再帰なしの `rm -f`・`git restore .` などは素通り）。
  足したい形は値の表の irreversible_bash_extra / irreversible_tools_extra へ。
費用: 在席中は離席の印の stat 1 回で終わる。
"""
from __future__ import annotations

import glob
import os
import re
import shlex
import subprocess
import tempfile

import guard_common as G
import unanswered as UQ

RM_WHY = "git で戻せない再帰の削除"
_RM = re.compile(r"-[a-zA-Z]*[rR][a-zA-Z]*|--recursive")
_BASH = [
    (r"\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+TABLE)\b", "DB の破棄"),
    (r"\b(supabase\s+db|prisma\s+migrate)\s+reset\b", "DB の破棄"),
]
# 道具の名の形で判る分（MCP の server 名は窓ごとに違う＝名を書かず形で引く）
_TOOLS = [
    (r"^mcp__[\w-]+__(?:send_?(?:e?mail|draft)|sendEmail|sendDraft)$", "メールの送信"),
    (r"^mcp__[\w-]+__API-delete-a-block$", "Notion の物理削除"),
]
TAIL_BYTES = 200_000
_REDIRECT = re.compile(r"(?:\d*(?:>>|>|<)&?|&>>?)\s*\S+")
_SPLIT = re.compile(r"&&|\|\||;|\n|\||&")


def _compile(pairs):
    out = []
    for p in pairs:
        pat, why = (p.get("pattern"), p.get("why")) if isinstance(p, dict) else p
        try:
            out.append((re.compile(str(pat), re.IGNORECASE), str(why or "戻せない操作")))
        except re.error:
            continue
    return out


def _git(cwd, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=10, env=env)


def _segments(cmd):
    """区切り（&& || ; 改行 | &）で分けた字句の並び（リダイレクトは外す・括弧は区切り）。読めない・展開があれば None。"""
    if "$(" in cmd or "`" in cmd:
        return None
    flat = _REDIRECT.sub(" ", cmd).replace("(", ";").replace(")", ";")
    out = []
    for seg in _SPLIT.split(flat):
        try:
            toks = shlex.split(seg)
        except ValueError:
            return None
        if toks:
            out.append(toks)
    return out


def _is_rm(t):
    return os.path.basename(t).lower() == "rm"


def recursive_rm(cmd):
    """区切りの中のどこかに、再帰の option つきの rm があるか（引用符で割った綴りも字句で読む）。"""
    if re.search(r"\brm\b[^\n;&|]*?\s(?:-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)(?=\s|$)", cmd):
        return True
    for seg in _SPLIT.split(_REDIRECT.sub(" ", cmd).replace("(", ";").replace(")", ";")):
        try:
            toks = shlex.split(seg)
        except ValueError:
            continue
        for i, t in enumerate(toks):
            if _is_rm(t) and any(_RM.fullmatch(o) for o in toks[i + 1:]):
                return True
    return False


def rm_targets(cmd, cwd):
    """rm が消す先の絶対 path の並び（cd を追い、glob を展開する）。判定できない時は None。"""
    segs = _segments(cmd)
    if segs is None or not cwd:
        return None
    out, other = [], False
    for toks in segs:
        if toks[0] in ("cd", "pushd"):
            if len(toks) != 2 or "$" in toks[1]:
                return None
            nxt = os.path.join(cwd, os.path.expanduser(toks[1]))
            if not os.path.isdir(nxt):
                return None
            cwd = os.path.normpath(nxt)
            continue
        if any(_is_rm(t) for t in toks[1:]):
            return None          # xargs rm・sudo rm・env rm など
        if not _is_rm(toks[0]):
            other = True         # rm より前の命令が消す先を変えうる（mv・cp・git checkout など）
            continue
        if other:
            return None
        opts_done = False
        for t in toks[1:]:
            if not opts_done and t == "--":
                opts_done = True
                continue
            if not opts_done and t.startswith("-"):
                continue
            opts_done = True
            if "$" in t:
                return None
            p = os.path.join(cwd, os.path.expanduser(t))
            out.extend(glob.glob(p) if any(c in t for c in "*?[") else [p])
    return out


def _in_scratch(real):
    """一時の置き場（TMPDIR か /tmp。窓の scratchpad もここ）の中か。置き場の根そのものは含めない。"""
    return real.startswith(os.path.realpath(tempfile.gettempdir()) + os.sep)


def _link_on_the_way(p):
    cur = os.sep
    for x in (x for x in p.split(os.sep) if x):
        cur = os.path.join(cur, x)
        if os.path.islink(cur):
            return True
    return False


def _clean(cwd, path="."):
    st = _git(cwd, "status", "--porcelain", "--ignored", "--untracked-files=all", "--", path)
    return st.returncode == 0 and not st.stdout.strip()


def _holds_git_dir(p):
    if os.path.basename(p) == ".git":
        return True
    for _root, dirs, files in os.walk(p) if os.path.isdir(p) else ():
        if ".git" in dirs or ".git" in files:
            return True
    return False


def target_restorable(p):
    """消す先 1 つを失っても戻せるか。判定できない時は False。"""
    if not os.path.lexists(p):
        return True
    real = os.path.realpath(p)
    if real in (os.sep, os.path.realpath(os.path.expanduser("~"))):
        return False
    if _in_scratch(real):
        return True
    if os.path.isfile(os.path.join(real, ".git")):           # git の作業部屋（worktree）の根
        return _clean(real)
    if _link_on_the_way(os.path.normpath(p)) or _holds_git_dir(real):
        return False
    base = real if os.path.isdir(real) else os.path.dirname(real)
    top = _git(base, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        return False
    root = os.path.realpath(top.stdout.strip())
    if real == root or root.startswith(real + os.sep):
        return False
    return bool(_git(base, "ls-files", "--", real).stdout.strip()) and _clean(base, real)


def rm_restorable(cmd, cwd):
    try:
        targets = rm_targets(cmd, cwd)
        return targets is not None and all(target_restorable(p) for p in targets)
    except Exception:
        return False


def match(tool_name, tool_input, cwd, vals):
    """戻せない操作なら理由、そうでなければ ""。"""
    name = str(tool_name or "")
    for rx, why in _compile(_TOOLS) + _compile(vals.get("irreversible_tools_extra") or []):
        if rx.search(name):
            return why
    if name != "Bash":
        return ""
    cmd = str((tool_input or {}).get("command") or "") if isinstance(tool_input, dict) else ""
    if recursive_rm(cmd) and not rm_restorable(cmd, cwd):
        return RM_WHY
    for rx, why in _compile(_BASH) + _compile(vals.get("irreversible_bash_extra") or []):
        if rx.search(cmd):
            return why
    return ""


def owner_returned_since(tpath, since):
    """離席の印より後に、人がタイプした行があるか（席に戻ったか）。判定できなければ False。"""
    t0 = G.parse_ts(since)
    if t0 is None or not tpath or not os.path.isfile(tpath):
        return False
    try:
        for row in G.iter_rows(tpath, TAIL_BYTES):
            if G.is_owner_row(row):
                ts = G.parse_ts(row.get("timestamp"))
                if ts is not None and ts > t0:
                    return True
    except Exception:
        return False
    return False


def check(data, vals):
    """止めるなら理由、通すなら ""。"""
    if G.unattended_by_env(vals):
        return ""     # 人のいない窓の印（夜の自走など）には「オーナーの離席」が無い
    session_id = str(data.get("session_id") or "")
    win = UQ.read_away(session_id)       # 在席中はここで終わる
    if not win:
        return ""
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else ""
    why = match(data.get("tool_name"), data.get("tool_input") or {}, cwd, vals)
    if not why:
        return ""
    if owner_returned_since(str(data.get("transcript_path") or ""), win.get("since")):
        UQ.close_away(session_id)
        return ""
    qs = win.get("questions") or []
    stems = " / ".join("「%s」" % str(q)[:48] for q in qs[:3]) or "(問いの控えなし)"
    return (
        "答えを聞けないまま閉じた問いが %d 件あり、オーナーは席を外しているとみなしています。"
        "その間は戻せない操作（%s）を行いません。\n"
        "閉じた問い: %s\n"
        "進め方: ①戻せる作業を先に進める ②この操作が要るなら AskUserQuestion で同じ問いを出し直し、"
        "答えが返ってから行う（答えが返るか、オーナーが何か打てば、この止めは自動で解けます）。"
    ) % (len(qs), why, stems)
