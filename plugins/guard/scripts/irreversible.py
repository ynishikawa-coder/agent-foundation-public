"""PreToolUse — 問いが答えのないまま閉じ、オーナーが席を外している間、戻せない操作を止める。

窓は狭い: 止まるのは ①この窓（セッション）で問いが答えのないまま閉じ ②まだオーナーが戻っていない 間だけ。
  答えが 1 つでも返れば閉じる。オーナーが何か打てば閉じる（会話ログの人の行で判定）。持ち越した問いは窓を開けない。
  人の手の命令は止めない（止めるのは離席中の AI の道具の呼び出しだけ）。

Bash は網を既定にする（bash_verbs）: 命令の全部の語（cmd_read.mentions＝引用符を外して割った語・変数を解いた語・
  中の -c の語）に、消す・捨てる動詞の語（DESTROY を語に割った物〔dropdb・FLUSHALL・rmtree・--delete も〕）か
  危ない語の組（{reset,--hard}・{branch,-D}・{push,--force}・{dd,of=} など）が在り、読み手が全部の段を
  「読むだけの命令」と証せない（cmd_read.inert が False）なら止める。段の頭の位置（words[0]）で形を見分けない
  （if/then・!・timeout -s・env -u・echo … | sh・git -C・python3 -c の中も、語が網に掛かる＝知らない形は止まる）。
  上書きのリダイレクト（`: > file`）は、的が在って戻せない時に止める。走らせる命令が読めない段（$CMD …）も止める。
  通す側の見分けは 2 つだけ（読めた時だけ通す）:
  - rm（再帰も 1 つの file も）: 消す先ごとに見て、どれも次のどれかなら通す: 在らない／一時の置き場（作業場）の中／
    git に全部記録済み（未記録の変更・未追跡・ignore の物が無い）／変更の無い git の作業部屋（worktree）。`cd` は追い、
    glob は展開して見る。判定できない時（展開・変数・rm が区切りの先頭に無い〔`| xargs rm`・`sudo rm`・`bash -c "rm …"`〕・
    在らない先への cd・rm より前に cd 以外の命令がある〔`mv keep gone && rm -rf gone`〕）は止める。
  - 記録していない変更を捨てる git（reset --hard・clean -f・restore・checkout --・stash drop/clear）: 今の dir の
    作業の木が綺麗（捨てる物が無い）で、別の dir を指していない（-C・--git-dir・--work-tree が無い）時だけ通す。
道具は名の動詞と入力の入れ子で読む（tool_verbs）: MCP の道具（mcp__<server>__<動詞>…）の名が削除の動詞（DESTROY）なら止め、
  読む動詞（READ）・戻せる書き込みの動詞（UNDOABLE）のどれでもない＝知らない動詞も止める。入力は JSON の入れ子を全部歩き、
  削除・捨てる・閉じる・置き換える類の語（TOOL_DESTROY）が、短い語の値（action・op・state・command など）か、
  真の値を持つ鍵（{"trashed": true}）に在れば止める（batch の中の delete・update_page の replace_content・
  update_file の trashed・issue_write の state=closed）。読むだけの道具（名の動詞が READ だけ）の入力は見ない。
  道具の名を 1 つずつ並べる表は持たない（並べていない削除の道具が通る穴の形）。
射程の天井: 別の script の file の中で消す形は見えない。足したい形は値の表の irreversible_bash_extra /
  irreversible_tools_extra へ。
費用: 在席中は離席の印の stat 1 回で終わる。
"""
from __future__ import annotations

import glob
import os
import re
import shlex
import subprocess
import tempfile

import cmd_read as R
import guard_common as G
import paid_upstream as PU      # Bash が書く先（リダイレクトの的）の読み
import unanswered as UQ

STEMS_SHOWN = 3   # 止めの文に載せる閉じた問いの数（越えた分は「ほか N 件」と置き場を出す）
RM_WHY = "git で戻せない削除"
_RM = re.compile(r"-[a-zA-Z]*[rR][a-zA-Z]*|--recursive")
# 道具の名・命令の名の動詞（語に割ってから照らす＝字の並びでなく語の類）
DESTROY = {"delete", "del", "remove", "rm", "rmdir", "trash", "drop", "destroy", "purge", "erase", "wipe", "shred",
           "truncate", "revoke", "terminate", "unpublish", "nuke", "obliterate", "expunge", "reset", "clear", "prune",
           "unlink", "uninstall", "flush", "rmtree", "rb"}
READ = {"get", "list", "ls", "read", "search", "fetch", "query", "view", "describe", "find", "lookup", "retrieve",
        "download", "export", "whoami", "status", "check", "show", "count", "preview", "inspect", "suggest", "resolve",
        "guide", "load", "select", "watch", "wait", "query"}
UNDOABLE = {"create", "update", "add", "append", "insert", "set", "move", "copy", "upload", "write", "edit", "comment",
            "reply", "rename", "duplicate", "restore", "unarchive", "enable", "disable", "link", "subscribe",
            "unsubscribe", "send", "post", "push", "open", "close", "merge", "request", "respond", "react", "pin",
            "unpin", "archive", "run", "fire", "trigger", "batch", "apply", "convert", "complete", "mark", "assign",
            "report", "attach", "register", "spawn", "stop", "interrupt", "schedule", "share", "publish", "import",
            "generate", "use", "fork", "approve", "submit", "save", "start", "notify", "tag", "label"}
# 道具の入力の中で戻せない類の語（削除に、閉じる・置き換える＝前の中身を失う類を足す）
TOOL_DESTROY = DESTROY | {"close", "replace", "overwrite"}
MAIL = {"mail", "email", "gmail", "draft"}       # 送る動詞と並ぶとメールの送信（送った文は戻せない）
# Bash の網で、語だけでは戻せないと言えない動詞（組で見る: reset は git の --hard か git でない db の reset・clear は stash）
_PAIRED = {"reset", "clear"}
CONTROL_KEYS = ("action", "method", "operation", "op")     # MCP でない道具（Artifact など）で見る欄
TAIL_BYTES = 200_000


# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}


def _compile(pairs):
    """値の表の regex_why（型は値の表の 1 本の口が照らし、読めない物は鍵ごと既定に倒す）。"""
    out = []
    for p in pairs:
        pat, why = (p.get("pattern"), p.get("why")) if isinstance(p, dict) else p
        out.append((re.compile(str(pat), re.IGNORECASE), str(why or "戻せない操作")))
    return out


def _git(cwd, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=10, env=env)


def _segments(cmd):
    """区切り（&& || ; 改行 | &）で分けた字句の並び（リダイレクトは外す・括弧は区切り）。読めない・展開があれば None。"""
    if "$(" in cmd or "`" in cmd:
        return None
    flat = re.sub(r"(?:\d*(?:>>|>|<)&?|&>>?)\s*\S+", " ", cmd).replace("(", ";").replace(")", ";")
    out = []
    for seg in re.split(r"&&|\|\||;|\n|\||&", flat):
        try:
            toks = shlex.split(seg)
        except ValueError:
            return None
        if toks:
            out.append(toks)
    return out


def _is_rm(t):
    return os.path.basename(t).lower() == "rm"


def rm_targets(cmd, cwd):
    """rm が消す先の絶対 path の並び（cd を追い、glob を展開する）。判定できない時は None。
    rm の段が 1 つも読めない（bash -c "rm …" のように中に包まれた）時も None（読めない＝通さない）。"""
    segs = _segments(cmd)
    if segs is None or not cwd:
        return None
    out, other, found = [], False, False
    for toks in segs:
        if toks[0] in ("cd", "pushd"):
            if len(toks) != 2 or "$" in toks[1]:
                return None
            nxt = os.path.join(cwd, os.path.expanduser(toks[1]))
            if not os.path.isdir(nxt):
                return None
            cwd = os.path.normpath(nxt)
            continue
        if any(_is_rm(t) or "rm" in words_of(t) for t in toks[1:]):
            return None          # xargs rm・sudo rm・env rm・bash -c "rm …" など
        if not _is_rm(toks[0]):
            other = True         # rm より前の命令が消す先を変えうる（mv・cp・git checkout など）
            continue
        if other:
            return None
        found = True
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
    return out if found else None


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


def words_of(name):
    """道具の名・命令の名を語に割る（- _ . と小文字→大文字の境で切り、小文字にする）。"""
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name or ""))
    return [w for w in re.split(r"[^A-Za-z0-9]+", name.lower()) if w]


def _verb(word, verbs):
    """語が動詞の類か（活用の d・ed・s・es も同じ類: closed・trashed・deleted）。"""
    return word in verbs or any(word == v + s for v in verbs for s in ("d", "ed", "s", "es"))


def _walk(node, key=""):
    """入力の JSON の入れ子を全部歩いた (鍵, 値) の並び。"""
    if isinstance(node, dict):
        for k, v in node.items():
            yield str(k), v
            yield from _walk(v, str(k))
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, key)


def _input_destroys(ti, everywhere):
    """入力の入れ子のどこかで戻せない類の語を使うか。訳か ""。everywhere=False は CONTROL_KEYS の欄だけ見る。"""
    for k, v in _walk(ti):
        if not everywhere and k not in CONTROL_KEYS:
            continue
        if everywhere and v not in (None, False, "", 0, [], {}) and any(_verb(w, TOOL_DESTROY) for w in words_of(k)):
            return "戻せない操作（入力の鍵 %s）" % k
        if isinstance(v, str) and re.fullmatch(r"[\w.:-]{1,64}", v) and any(_verb(w, TOOL_DESTROY) for w in words_of(v)):
            return "戻せない操作（入力の %s=%s）" % (k, v)
    return ""


def tool_verbs(name, tool_input):
    """道具の呼び出しが戻せないなら訳、戻せるなら ""。MCP の道具は名の動詞と入力の入れ子、ほかの道具は入力の action・method。"""
    ti = tool_input if isinstance(tool_input, dict) else {}
    if not name.startswith("mcp__"):
        return _input_destroys(ti, everywhere=False)
    verb = words_of(name.split("__", 2)[-1])
    bad = [w for w in verb if w in DESTROY]
    if bad:
        return "戻せない削除（道具 %s の動詞 %s）" % (name, bad[0])
    if "send" in verb and set(verb) & MAIL:
        return "メールの送信（%s）" % name
    known = [w for w in verb if w in READ or w in UNDOABLE]
    if not known:
        return "戻せるか分からない道具（%s の名に知っている動詞が無い）" % name
    if not any(w in UNDOABLE for w in verb):
        return ""                                     # 読むだけの道具（名の動詞が READ だけ）の入力は見ない
    return _input_destroys(ti, everywhere=True)


def _words(cmd):
    """網の語: 読み手の mentions（字のまま）と、その小文字・語に割った物。"""
    ments = R.mentions(cmd)
    out = set(ments) | {m.lower() for m in ments}
    for m in ments:
        out.update(words_of(m))
    return ments, out


def _hits(cmd):
    """命令の語の網に掛かる戻せない類: [(訳, 類)]。類は rm（消す先で通す見分け）・git（作業の木で通す見分け）・hard。"""
    ments, W = _words(cmd)
    opts = [m for m in ments if m.startswith("-")]
    hits, claimed = [], set()
    git = "git" in W
    if "reset" in W:
        if not git:
            hits.append(("戻せない reset（%s）" % "reset", "hard"))
        elif any(o.startswith(("--hard", "--merge", "--keep")) for o in opts):
            hits.append(("記録していない変更を捨てる git（reset --hard）", "git"))
        claimed.add("reset")
    if git and "clean" in W and any(re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", o) or o == "--force" for o in opts):
        hits.append(("記録していない変更を捨てる git（clean -f）", "git"))
    if git and "restore" in W:
        hits.append(("記録していない変更を捨てる git（restore）", "git"))
    if git and "checkout" in W and ("--" in ments or "." in ments or "-f" in ments or "--force" in ments):
        hits.append(("記録していない変更を捨てる git（checkout --）", "git"))
    if git and "stash" in W and W & {"drop", "clear"}:
        hits.append(("記録していない変更を捨てる git（stash drop/clear）", "git"))
        claimed |= {"drop", "clear"}
    if git and "branch" in W and ("-D" in ments or ("--delete" in ments and ("--force" in ments or "-f" in ments))):
        hits.append(("戻せない git の枝の削除（branch -D）", "hard"))
    if git and "push" in W and any(o.startswith("--force") or o in ("-f", "--mirror") for o in opts) | any(
            m.startswith("+") and len(m) > 1 for m in ments):
        hits.append(("戻せない強制 push", "hard"))
    if any(m.startswith("of=") for m in ments) and "dd" in W:
        hits.append(("dd の上書き（of=）", "hard"))
    raw = {m.lower() for m in ments}
    verbs = DESTROY - _PAIRED
    for w in sorted(W - claimed - _PAIRED):
        if w.startswith("-") or (len(w) < 4 and w not in raw):
            continue                                   # 短い動詞（rm・del・rb）は 1 語で立つ時だけ（x.rb の rb は動詞でない）
        if w == "rm":
            hits.append(("git で戻せない削除（rm）", "rm"))
        elif w in verbs or (len(w) > 4 and any(w.startswith(v) for v in verbs if len(v) >= 4)):
            hits.append(("戻せない削除の語（%s）" % w, "hard"))
    return hits


def _overwrites(cmd, cwd):
    """上書きのリダイレクト（> ・>|・&>）の的のうち、在って戻せない物の訳か ""。的が読めない時も訳。"""
    cwd = cwd or os.getcwd()
    bases = [cwd] + [os.path.join(cwd, seg[1].text) for seg in R.read(cmd).segments
                     if R.prog_name(seg) in ("cd", "pushd") and len(seg) > 1]
    for op, w in PU._redirects(cmd):
        if ">>" in op or w.text.startswith("/dev/"):
            continue
        if w.opaque:
            return "上書きの的が読めないリダイレクト（%s %s）" % (op, w.text)
        for b in bases:
            p = os.path.join(b, os.path.expanduser(w.text))
            if os.path.lexists(p) and not target_restorable(p):
                return "戻せない上書き（%s %s）" % (op, w.text)
    return ""


def bash_verbs(cmd, cwd):
    """命令の語の網で戻せない命令を探す。訳か ""。読み手は「読むだけ」と証せた時に通す側にだけ使う。"""
    for words in R.read(cmd).segments:
        if words and words[0].opaque:
            return "走らせる命令が読めない段（%s）" % words[0].text
    why = _overwrites(cmd, cwd)
    if why:
        return why
    if R.inert(cmd):
        return ""
    hits = _hits(cmd)
    if not hits:
        return ""
    kinds = {k for _, k in hits}
    if "hard" in kinds:
        return next(w for w, k in hits if k == "hard")
    if "git" in kinds:
        moved = R.mentions(cmd) & {"-C", "--git-dir", "--work-tree"}
        if moved or not (cwd and _clean(cwd)):
            return next(w for w, k in hits if k == "git")
    if "rm" in kinds and not rm_restorable(cmd, cwd):
        return RM_WHY
    return ""


def match(tool_name, tool_input, cwd, vals):
    """戻せない操作なら理由、そうでなければ ""。"""
    name = str(tool_name or "")
    for rx, why in _compile(vals.get("irreversible_tools_extra") or []):
        if rx.search(name):
            return why
    if name != "Bash":
        return tool_verbs(name, tool_input)
    cmd = str((tool_input or {}).get("command") or "") if isinstance(tool_input, dict) else ""
    for rx, why in _compile(vals.get("irreversible_bash_extra") or []):
        if rx.search(cmd):
            return why
    return bash_verbs(cmd, cwd)


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
    stems = " / ".join("「%s」" % str(q)[:48] for q in qs[:STEMS_SHOWN]) or "(問いの控えなし)"
    if len(qs) > STEMS_SHOWN:
        stems += "（ほか %d 件。全部は離席の印 %s と台帳 %s）" % (
            len(qs) - STEMS_SHOWN, UQ.away_path(session_id), UQ.ledger_path(vals, data) or "(置き場を決められず)")
    return (
        "答えを聞けないまま閉じた問いが %d 件あり、オーナーは席を外しているとみなしています。"
        "その間は戻せない操作（%s）を行いません。\n"
        "閉じた問い: %s\n"
        "進め方: ①戻せる作業を先に進める ②この操作が要るなら AskUserQuestion で同じ問いを出し直し、"
        "答えが返ってから行う（答えが返るか、オーナーが何か打てば、この止めは自動で解けます）。"
    ) % (len(qs), why, stems)
