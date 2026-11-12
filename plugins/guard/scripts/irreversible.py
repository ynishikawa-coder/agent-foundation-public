"""PreToolUse — 問いが答えのないまま閉じ、オーナーが席を外している間、元に戻せない操作を止める。

決まり: 答えを聞けない間は、元に戻せる作業だけを推奨案で進め、戻せない作業は進まず待つ。
  条文だけにすると、実行するのは答えを持っていない側。外した時のやり直しが最も高くつく操作だけは機械が手を止める。
  第 1 層は unanswered の capture が閉じた瞬間に鳴らす 1 行、これは「それでも手が出た時」の第 2 層。

窓は狭い（安全の設計の要）: 止まるのは ①この窓（セッション）で問いが答えのないまま閉じ ②まだオーナーが戻っていない 間だけ。
  答えが 1 つでも返れば閉じる。オーナーが何か打てば閉じる（会話ログの人の行で判定）。持ち越した問いは窓を開けない。

止めるのは 4 つだけ: 社外への送信・課金・本番への出荷・git で戻せない削除。
  削除は「git で戻せるか」で分ける: 消す先が全部 git に記録済みで、未記録の変更・未追跡・ignore の物が無ければ通す。
  `git reset --hard`・`git clean` も、失う物が無ければ通す。判定できない時（git の外・存在しない・`.git` を含む・
  repo の根かそれより上・コマンドの中で場所を変える〔cd・pushd・`git -C`・`--git-dir`・`--work-tree`〕・
  rm が区切りの先頭に無い〔`| xargs rm`・`sudo rm`〕・`..` を含む・途中にシンボリックリンク・展開がある）は戻せない側に倒す。
  `git checkout`／`git switch` の `-f`・`--force`・`--discard-changes` は戻せるかを判定せず止める。
  枝の強制削除は止めない（reflog で gc までは戻せる）。

射程の天井（正直に書く）: 判定は列挙であって証明ではない。列挙の外（`find … -delete`・再帰なしの `rm -f`・
  `git checkout -- .`・`git restore .`・リダイレクトで中身を消す形）は素通りする。足したい形は値の表の
  irreversible_bash_extra / irreversible_tools_extra へ。オーナーが居る間の破壊操作は permissions.deny の受け持ち。

費用: 在席中は離席の印の stat 1 回で終わる。会話ログを読むのは「窓が開いている ∧ 当たった」時だけ。
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess

import guard_common as G
import unanswered as UQ

RECURSIVE_RM_WHY = "ファイルの再帰削除"
RESET_WHY = "作業内容の破棄（git reset --hard）"
CLEAN_WHY = "未追跡ファイルの削除（git clean）"

_BASH = [
    # 削除・破棄（再帰の option が 1 つでもあれば当てる。git の前置き option を挟んだ形も当てる）
    (r"\brm\b[^\n;&|]*?\s(?:-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)(?=\s|$)", RECURSIVE_RM_WHY),
    (r"\bgit\b[^\n;&|]*?\sreset\b[^\n;&|]*?\s--hard\b", RESET_WHY),
    (r"\bgit\b[^\n;&|]*?\s(?:checkout|switch)\b[^\n;&|]*?\s(?:-[a-zA-Z]*f[a-zA-Z]*|--force|--discard-changes)(?=\s|$)",
     "作業内容の破棄（git checkout／switch -f）"),
    (r"\bgit\b[^\n;&|]*?\sclean\b[^\n;&|]*?\s(?:-[a-zA-Z]*f[a-zA-Z]*|--force)(?=\s|$)", CLEAN_WHY),
    (r"\bgit\s+push\s+.*(--force|--delete|\s-f\b)", "履歴の強制上書き／リモートの削除"),
    (r"\bgit\s+worktree\s+remove\s+--force\b", "作業部屋の強制削除"),
    (r"\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+TABLE)\b", "DB の破棄"),
    # 本番への出荷
    (r"\bvercel\b[^\n]*--prod\b", "本番への出荷（Vercel）"),
    (r"\bnetlify\s+deploy\b[^\n]*--prod\b", "本番への出荷（Netlify）"),
    (r"\bwrangler\s+(publish|deploy)\b", "本番への出荷（Cloudflare）"),
    (r"\b(npm|pnpm|yarn)\s+run\s+deploy\b", "本番への出荷"),
    (r"\bgh\s+release\s+create\b", "リリースの公開"),
    (r"\beas\s+submit\b", "ストアへの提出"),
    # データの移行・スキーマの変更
    (r"\bsupabase\s+db\s+(push|reset)\b", "DB スキーマの適用"),
    (r"\bprisma\s+migrate\s+(deploy|reset)\b", "DB マイグレーションの適用"),
    (r"\balembic\s+upgrade\b", "DB マイグレーションの適用"),
    # 社外への送信
    (r"api\.telegram\.org[^\n]*sendMessage", "Telegram への送信"),
]
# 道具の名の形で判る分（MCP の server 名は窓ごとに違う＝名を書かず形で引く）
_TOOLS = [
    (r"^mcp__[\w-]+__(?:send_?(?:e?mail|draft)|sendEmail|sendDraft)$", "メールの送信"),
    (r"^mcp__notion[\w-]*__API-delete-a-block$", "Notion の物理削除"),
]
GIT_RESTORABLE_CHECK = (RECURSIVE_RM_WHY, RESET_WHY, CLEAN_WHY)
RECURSIVE_RM = re.compile(_BASH[0][0], re.IGNORECASE)
TAIL_BYTES = 200_000

_LOCATION_SHIFT = re.compile(r"(?:^|[\s;&|(`])(?:cd|pushd|popd)(?:\s|$)|--git-dir\b|--work-tree\b"
                             r"|\bGIT_(?:DIR|WORK_TREE|COMMON_DIR|INDEX_FILE)=|\bcore\.worktree\b")
_GIT_C = re.compile(r"\bgit\b[^\n;&|]*?(?:^|\s)-C(?:\s|=|$)")
_REDIRECT = re.compile(r"(?:\d*(?:>>|>|<)&?|&>>?)\s*\S+")
_SPLIT = re.compile(r"&&|\|\||;|\n|\||&")
RESET_PLAIN = {"--hard", "-q", "--quiet", "HEAD"}


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


def _rm_targets(cmd):
    """コマンド全体が素の rm だけの時の消す先。他の命令が 1 つでも混ざる・展開がある時は None（止める側）。
    option は最初の消す先か `--` まで（それより後ろは `-x` の形でも消す先）。"""
    segs = _segments(cmd)
    if not segs:
        return None
    out = []
    for toks in segs:
        if toks[0] not in ("rm", "/bin/rm"):
            return None
        opts_done = False
        for t in toks[1:]:
            if not opts_done and t == "--":
                opts_done = True
                continue
            if not opts_done and t.startswith("-"):
                continue
            opts_done = True
            if any(c in t for c in "*?[]{}$`~"):
                return None
            out.append(t)
    return out or None


def _plain_reset(cmd):
    segs = _segments(cmd)
    if not segs or len(segs) != 1:
        return False
    toks = segs[0]
    return toks[:2] == ["git", "reset"] and "--hard" in toks[2:] and set(toks[2:]) <= RESET_PLAIN


def _plain_git(cmd, sub):
    segs = _segments(cmd)
    return bool(segs) and len(segs) == 1 and len(segs[0]) >= 2 and segs[0][:2] == ["git", sub]


def _link_on_the_way(t, cwd):
    """消す先かその途中がシンボリックリンクか。`..` を含む形も読まない（True）。"""
    raw = t.split(os.sep)
    if ".." in raw:
        return True
    cur = cwd if not os.path.isabs(t) else os.sep
    for x in (x for x in raw if x and x != "."):
        cur = os.path.join(cur, x)
        if os.path.islink(cur):
            return True
    return False


def _holds_git_dir(p):
    if os.path.basename(p) == ".git":
        return True
    if not os.path.isdir(p):
        return False
    for _root, dirs, files in os.walk(p):
        if ".git" in dirs or ".git" in files:
            return True
    return False


def git_restorable(why, cmd, cwd):
    """その削除が git で全部戻せるなら True。判定できない時は False（止める側）。"""
    try:
        if not cwd or _LOCATION_SHIFT.search(cmd) or _GIT_C.search(cmd):
            return False
        if why == RECURSIVE_RM_WHY:
            targets = _rm_targets(cmd)
            if not targets:
                return False
            for t in targets:
                if _link_on_the_way(t, cwd):
                    return False
                p = os.path.realpath(t if os.path.isabs(t) else os.path.join(cwd, t))
                if not os.path.exists(p) or _holds_git_dir(p):
                    return False
                base = p if os.path.isdir(p) else os.path.dirname(p)
                top = _git(base, "rev-parse", "--show-toplevel")
                if top.returncode != 0:
                    return False
                root = os.path.realpath(top.stdout.strip())
                if p == root or root.startswith(p + os.sep):
                    return False
                if not _git(base, "ls-files", "--", p).stdout.strip():
                    return False
                st = _git(base, "status", "--porcelain", "--ignored", "--untracked-files=all", "--", p)
                if st.returncode != 0 or st.stdout.strip():
                    return False
            return True
        if why == RESET_WHY:
            if not _plain_reset(cmd):
                return False
            st = _git(cwd, "status", "--porcelain", "--untracked-files=no")
            return st.returncode == 0 and not st.stdout.strip()
        if why == CLEAN_WHY:
            if not _plain_git(cmd, "clean"):
                return False
            st = _git(cwd, "status", "--porcelain", "--untracked-files=all", "--ignored")
            return st.returncode == 0 and not any(l[:2] in ("??", "!!") for l in st.stdout.splitlines())
    except Exception:
        return False
    return False


def _token_recursive_rm(cmd):
    """引用符で割った綴り（rm "-rf" x・r''m -rf x）も字句で読み、区切りの中の rm に再帰の option があるか。"""
    flat = _REDIRECT.sub(" ", cmd).replace("(", ";").replace(")", ";")
    for seg in _SPLIT.split(flat):
        try:
            toks = shlex.split(seg)
        except ValueError:
            continue
        for i, t in enumerate(toks):
            if os.path.basename(t).lower() == "rm" and any(
                    re.fullmatch(r"-[a-zA-Z]*[rR][a-zA-Z]*|--recursive", o) for o in toks[i + 1:]):
                return True
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
    bash = _compile(_BASH) + _compile(vals.get("irreversible_bash_extra") or [])
    if _token_recursive_rm(cmd) and not RECURSIVE_RM.search(cmd):
        return "" if git_restorable(RECURSIVE_RM_WHY, cmd, cwd) else RECURSIVE_RM_WHY
    for rx, why in bash:
        if rx.search(cmd):
            if why in GIT_RESTORABLE_CHECK and git_restorable(why, cmd, cwd):
                continue
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
        return ""     # 人のいない窓には「オーナーの離席」が無い（そもそもモーダルで聞かない）
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
        "その間は元に戻せない操作（%s）を行いません。\n"
        "閉じた問い: %s\n"
        "進め方: ①元に戻せる範囲の作業を先に進める ②この操作が要るなら AskUserQuestion で同じ問いを出し直し、"
        "答えが返ってから行う（答えが返るか、オーナーが何か打てば、この止めは自動で解けます）。"
    ) % (len(qs), why, stems)
