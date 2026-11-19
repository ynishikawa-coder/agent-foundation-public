"""PreToolUse — 外へ送る命令（skill が宣言した送る口）を、送る物を見せた後の人の go が無いまま打つ手を止める。

なぜ在るか: compose-message は「送る前に go を取る」、make-deck は「外へ入れる前に送信可否を確かめる」を SKILL の文で
  求めるだけで、AI が頼まれた同じターンのうちに送っても何も止めなかった（原因の台帳: してから次への跡を照らさない）。
  社外への送信はオーナーにしか決められない（核 §4）。

正本（写さない）: 送る口は各 skill の SKILL.md の頭（frontmatter）の `send-gate: <送る命令の形>` が宣言する。
  形は shell の 1 行（例 `<道具> source add`）。`{value:<plugin>.<skill>.<鍵…>}` は repo の値の表の値（字のまま）に
  置き換える（送る命令が会社ごとの物）。値が無い時はその宣言を使わない（送る口が無い＝送らない repo）。
  宣言を guard_common.parse_shell で読み、頭の解釈の道具（python3 など）を飛ばした最初の語が「送る道具」、その後の
  option でない語の並びが「送る段の名」（例 source add）。

送る命令かは、命令の字の並びでなく、命令を parse_shell で語に読んで決める（字の並びで決めると、並び替え・`--to=`・空白・
  python の包み・cd &&・変数で通った＝2026-11-19 のレビュー）:
  - 走る命令のどの位置の語でも、名（basename か拡張子を外した名）が送る道具に当たれば送る命令（読むだけの道具 READERS の
    引数は除く）。送る段の名を宣言する口は、その並びが後ろに在る時だけ。
  - 読み切れない形（parse_shell の unknowns・引数の位置の変数・解釈の道具に字で渡すコード・標準入力で渡すコード）は、
    送る道具の名の字が命令のどこかに在るか、読み手が「走る道具を走る時に決める」印（Unknown.code）を返した時に止める
    （既定で止める）。止めるかは印と命令の字の事実だけで決め、読み手の訳の言い回しには頼らない。読み手は parse_shell
    の 1 つ（PR #77 が持つ。ここに写さない）。
  - 試しの形は、送る道具のその単純な命令の引数に `--dry-run` が在る時だけ（`; echo --dry-run`・注の中は数えない）。
送る物は送る命令の引数から字のまま全部決める（決められなければ止める）:
  - option の名でない語と `--名=値` の値の全部。在る file は字の file なら中身、字でない file は絶対 path と sha256。
  - 変数・展開・当たる glob・解けない path・dir・標準入力（パイプ・<・ヒアドキュメント）で渡す形は止める。
  - 見せた: 会話ログの AI の文が、字の送る物を全部含む（空白の違いは見ない）。字でない file は絶対 path と sha256 の頭 12 字を
    書く（同じ名の別の file・見せた後に書き替えた file を通さない）。
  - go: 全部の送る物を見せた後に、人がタイプした行（guard_common.is_human_prompt＝人の行の形が全部そろう時だけ）か、
    答えの返った選択肢の画面が在る。
  人のいない窓（値の表の unattended_env が真・返し先が別の窓の子の窓）は go を取れないので止める（返し先へ返す）。
止まるのは AI の道具の呼び出しだけ。会話ログが読めない時も止める（go を確かめられない送信は出さない）。
"""
from __future__ import annotations

import fnmatch
import glob
import hashlib
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
# 宣言の頭で飛ばす解釈の道具（その次の語が送る道具）と、引数の file を読むだけで走らせない道具
INTERP = re.compile(r"(?:python[\d.]*|node|nodejs|deno|bun|ruby|perl|php|bash|sh|zsh|uv|pipx|npx|run)\Z")
INLINE_CODE = re.compile(r"(?:python[\d.]*|node|nodejs|deno|bun|ruby|perl|php)\Z")
READERS = frozenset(("cat", "head", "tail", "less", "more", "wc", "ls", "stat", "file", "grep", "egrep", "fgrep", "rg",
                     "diff", "cmp", "sha256sum", "sha1sum", "md5sum", "echo", "printf", "test", "[", "[[", "git", "gh"))
GLOB = re.compile(r"[*?\[]")
HASH_SHOWN = 12


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


def read_gate(text):
    """送る命令の形（shell の 1 行）を (送る道具の語, 送る段の名の並び) に。読めなければ None。"""
    cmds, unknowns = G.parse_shell(text)
    if unknowns or len(cmds) != 1:
        return None
    argv = cmds[0]
    i = 0
    while i < len(argv) and (INTERP.match(os.path.basename(argv[i])) or argv[i].startswith("-")):
        i += 1
    if i >= len(argv) or "$" in argv[i]:
        return None
    sub = []
    for w in argv[i + 1:]:
        if w.startswith("-"):
            break
        sub.append(w)
    return argv[i], tuple(sub)


def gates(data, guard_root=None):
    """(skill の名, (送る道具, 送る段の名) か None〔読めない宣言〕) の並び。"""
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
            decl = v.strip()
            if len(decl) >= 2 and decl[0] == decl[-1] == "'":     # YAML の字の囲み（{ で始まる式を囲む）
                decl = decl[1:-1].replace("''", "'")
            if VALUE.search(decl):
                if table is None:
                    table = _table(data)
                vals = [_lookup(table, d) for d in VALUE.findall(decl)]
                if not all(vals):
                    continue
                it = iter(vals)
                decl = VALUE.sub(lambda _m: next(it), decl)
            out.append((os.path.basename(os.path.dirname(md)), read_gate(decl)))
    return out


def _is_prog(word, prog):
    base, want = os.path.basename(word), os.path.basename(prog)
    if base == want or os.path.splitext(base)[0] == os.path.splitext(want)[0]:
        return True
    return bool(GLOB.search(base)) and fnmatch.fnmatchcase(want, base)


def _has_seq(words, seq):
    n = len(seq)
    return n == 0 or any(tuple(words[j:j + n]) == seq for j in range(len(words) - n + 1))


def _stdin_fed(cmd):
    """命令のどこかでパイプ・< の向け替え・ヒアドキュメントで標準入力を渡すか（読めなければ渡すと見る）。"""
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>\n")
        lex.whitespace, lex.whitespace_split, lex.commenters = " \t\r", True, ""
        toks = list(lex)
    except ValueError:
        return True
    for t in toks:
        if t and set(t) <= set(";&|()<>\n") and ("<" in t or "|" in t.replace("||", "")):
            return True
    return False


# 読み手（guard_common.parse_shell）の読み切れない所の印（Unknown.code）のうち、走る道具を走る時に決める物と、値を隠せる物
RUNTIME_PROGRAM = frozenset(("var_program", "unknown_wrapper", "exec_shell", "eval_dyn", "env_S", "pipe_to_shell",
                             "heredoc_to_shell", "nesting_deep", "not_text"))
HIDING = frozenset(("subst", "backtick", "process_subst"))


def _code(u):
    """読み切れない所 1 つの印。印の無い形（読み手が違う）は、走る道具を決められない側の印に倒す。"""
    c = getattr(u, "code", None)
    return c if isinstance(c, str) and c else "var_program"


def _said(u):
    """読み切れない所 1 つの人の読む訳（止めるかの決めには使わない）。"""
    return str(getattr(u, "message", u))


def find_sends(cmd, gate):
    """命令 cmd の中の送る命令: ([(単純な命令の位置, argv, 送る道具の位置)], [止める訳])。"""
    prog, sub = gate
    stem = os.path.splitext(os.path.basename(prog))[0]
    named_word = bool(stem) and stem in cmd                               # 送る道具の名の字が命令のどこかに在る
    named = named_word and all(s in cmd for s in sub)                     # それと送る段の名の字も在る
    cmds, unknowns = G.parse_shell(cmd)
    hits, why = [], []
    for ci, argv in enumerate(cmds):
        reader = os.path.basename(argv[0]) in READERS
        for k, w in enumerate(argv):
            if (k == 0 or not reader) and _is_prog(w, prog) and _has_seq(argv[k + 1:], sub):
                hits.append((ci, argv, k))
                break
    # 読み切れない形の止めは、読み手が返す印（Unknown.code）と命令の字の事実だけで決め、訳の言い回しには頼らない
    # （訳の字に正規表現を当てていたので、言い回しの違う読み手の下で止めが外れた＝2026-11-19 のレビュー）:
    #  - 送る道具の名の字が命令のどこかに在る（語でも語の一部でも）なら、読み切れない所が 1 つでも在れば止める。
    #  - 走る道具を走る時に決める印（RUNTIME_PROGRAM: 道具の名の展開・表に無い命令の引数の展開・シェルへ流す形など）が
    #    在れば、名の字が無くても止める（`X=$(printf %s 送); python3 /…/${X}る口.py`）。送る段の名を宣言する口は、
    #    その字が全部命令に在るか、値を隠せる印（HIDING: $(…)・`…`）が在る時だけ（`"$V/notebooklm" doctor` は通す）。
    #  （値を隠せる印だけの命令〔`git commit -m "$(cat …)"`〕は止めない。置き換えの中で送る道具を走らせる形は、
    #   名の字が在れば上で止まり、名を隠せば別の script を走らせる形と同じ残る穴）
    codes = {_code(u) for u in unknowns}
    step = not sub or all(s in cmd for s in sub) or bool(codes & HIDING)
    if unknowns and (named_word or (codes & RUNTIME_PROGRAM and step)):
        why.append("命令を読み切れず、%s（%s）" % (
            "送る道具の名の字が在る" if named_word else "走る道具を走る時に決める形が在る", "・".join(map(_said, unknowns))))
    if named and not hits:
        for argv in cmds:
            name = os.path.basename(argv[0])
            if name in READERS:
                continue
            if INLINE_CODE.match(name) and any(re.fullmatch(r"-[A-Za-z]*[ce]|--eval", a) for a in argv[1:]):
                why.append("%s に字で渡すコードの中で送る道具の名を使う（%s）" % (name, os.path.basename(prog)))
            elif any("$" in a for a in argv[1:]):
                why.append("送る道具を変数で渡す（%s）" % " ".join(argv)[:120])
            elif INTERP.match(name) and all(a.startswith("-") for a in argv[1:]) and _stdin_fed(cmd):
                why.append("%s へ標準入力でコードを渡す" % name)
    return hits, why


def materials(argv, k, sub, cwd):
    """送る命令の引数から送る物: ([(種類 "text"|"bin", 中身か絶対 path, 名, sha256)], [止める訳])。"""
    out, why = [], []
    words = argv[k + 1:]
    if tuple(words[:len(sub)]) == tuple(sub):
        words = words[len(sub):]                          # 送る段の名（並びが離れていれば、その語も送る物に数える）
    for w in words:
        if w == "--":
            continue
        if w.startswith("--"):
            if "=" not in w:
                continue
            w = w.split("=", 1)[1]
        elif w.startswith("-") and len(w) > 1 and not re.fullmatch(r"-\d+(?:\.\d+)?", w):
            if len(w) <= 2:
                continue
            w = w[2:]                                     # -t値 の形（値を詰めて書く）も送る物に数える
        if not w:
            continue
        if "$" in w:
            why.append("引数に変数・展開が在る（%s）" % w[:80])
            continue
        p = os.path.expanduser(w)
        if not os.path.isabs(p):
            if cwd is None:
                why.append("cd の先が読めず、相対の path（%s）を解けない" % w[:80])
                continue
            p = os.path.join(cwd, p)
        p = os.path.normpath(p)
        if GLOB.search(w) and glob.glob(p):
            why.append("引数が glob で別の字に広がる（%s）" % w[:80])
            continue
        if os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    raw = f.read()
            except OSError as e:
                why.append("送る file が読めない（%s: %s）" % (w[:80], e))
                continue
            sha = hashlib.sha256(raw).hexdigest()
            try:
                text = raw.decode("utf-8") if b"\0" not in raw else None
            except UnicodeDecodeError:
                text = None
            if text is not None and text.strip():
                out.append(("text", text, os.path.basename(p), sha))
            else:
                out.append(("bin", os.path.realpath(p), os.path.basename(p), sha))
        elif os.path.exists(p):
            why.append("送る物が file でない（%s）" % w[:80])
        elif w.startswith(("/", "./", "../", "~")) or ("/" in w and "://" not in w):
            why.append("path が解けない（%s）" % w[:80])
        else:
            out.append(("text", w, "命令に書いた字「%s」" % w[:40], ""))
    return out, why


def _cwd_before(cmds, upto, cwd):
    """upto 番目の単純な命令の前の cd を辿った作業の dir（読めない cd があれば None）。"""
    for argv in cmds[:upto]:
        if os.path.basename(argv[0]) not in ("cd", "pushd"):
            continue
        t = argv[1] if len(argv) > 1 else ""
        if not t or t == "-" or "$" in t or cwd is None:
            cwd = None
            continue
        cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(t)))
    return cwd


def _answered_ask(row):
    """答えの返った選択肢の画面の行か。"""
    r = row.get("toolUseResult")
    return row.get("type") == "user" and isinstance(r, dict) and isinstance(r.get("answers"), dict) and bool(r["answers"])


WS = re.compile(r"\s+")


def _norm(t):
    return WS.sub("", t or "")


def _shown_at(rows, item):
    """送る物を見せた AI の行の位置（最初の 1 つ）か None。"""
    kind, val, _, sha = item
    want = _norm(val) if kind == "text" else ""
    for i, r in enumerate(rows):
        if r.get("type") != "assistant":
            continue
        t = G.text_of(r)
        if kind == "text":
            if want and want in _norm(t):
                return i
        elif val in t and sha[:HASH_SHOWN] in t:
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
    return any(G.is_human_prompt(r) or _answered_ask(r) for r in rows[after + 1:])


def check(data, vals):
    if str(data.get("tool_name") or "") != "Bash":
        return ""
    cmd = (data.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return ""
    cwd0 = data.get("cwd") or G.project_dir(data) or ""
    hit, items, why_read = [], [], []
    cmds = None
    for name, gate in gates(data):
        if gate is None:
            return ("skill %s の SKILL.md の send-gate（送る口の宣言）が送る命令の形として読めないので、送る命令かを確かめられず"
                    "止めました。土台の plugin を入れ直すか、その skill の send-gate（値の表の送る命令）を直す。" % name)
        sends, why = find_sends(cmd, gate)
        sends = [s for s in sends if "--dry-run" not in s[1][s[2] + 1:]]     # 試しの形は送る道具の引数にある時だけ
        if not sends and not why:
            continue
        hit.append(name)
        why_read += why
        if sends and _stdin_fed(cmd):
            why_read.append("パイプ・< の向け替え・ヒアドキュメントで送る物を標準入力から渡しうる")
        if cmds is None:
            cmds = G.parse_shell(cmd)[0]
        for ci, argv, k in sends:
            got, bad = materials(argv, k, gate[1], _cwd_before(cmds, ci, cwd0 or None))
            items += got
            why_read += bad
    if not hit:
        return ""
    tpath = data.get("transcript_path") or ""
    if G.unattended_by_env(vals) or G.is_child_prompt(G.first_owner_text(tpath)):
        why = "人のいない窓（返し先が別の窓・夜の自走の印）は人の go を取れない"
    elif why_read:
        why = "送る物（送る文面の file・命令に書いた字）を命令から字のまま決められない（%s）" % "／".join(dict.fromkeys(why_read))
    else:
        go = has_go(tpath, items) if items else False
        if go:
            return ""
        if not items:
            why = "送る物（送る文面の file・命令に書いた字）が命令に無い"
        elif go is None:
            why = "会話ログが読めず go を確かめられない"
        else:
            names = "・".join(n for _, _, n, _ in items)
            why = "送る物（%s）を返事で見せた後の人の go が会話ログに無い" % names
    return ("外へ送る命令（skill %s の送る口）を、%sので止めました。\n"
            "直し方（skill guard:guard-rules の send_go）:\n"
            "  ① 送る文面・素材（何を・誰へ・どこへ）を返事で見せ、そのターンを締めて人の go を待つ"
            "（選択肢の画面で「送る／直す／送らない」を聞いてもよい）。文面は送る file の中身と、命令に書く字（宛先・"
            "ノートの名など）をそのまま全部見せる。字でない file は絶対 path と sha256 の頭 %d 字を書く。見せた後に"
            "file を書き替えたら、見せ直して go を取り直す\n"
            "  ② go が返ってから、送る道具を直に、引数を字のまま書いた 1 つの命令で打つ（変数・$(…)・パイプ・< ・"
            "ヒアドキュメント・包みを使わない）。文面だけ見たい時は送る道具の引数に --dry-run を付ける\n"
            "  人のいない窓は送らず、返し先へ「送る物と go の要る事」を返す。" % ("・".join(dict.fromkeys(hit)), why, HASH_SHOWN))
