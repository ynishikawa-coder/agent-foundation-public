"""守りの hook が共に使う小さな口: 値の表・置き場・人のいない窓の見分け・会話ログの読み方。

どの口も壊れた時は既定に倒す（見張りの故障で窓を止めない）。仕事の中身や特定の窓の名前は持たない。

値の表（在る時だけ読む・無ければ既定で動く）: config/skill-values.json の "guard"。探し方・鍵の一覧・型・既定は
  plugin の lib/skill_values.py と lib/schema.json（＝土台の skill-values/ の正本への symlink）が持つ＝ここに写さない。
  知らない鍵・畳んだ鍵・型の違う値は、その鍵だけ既定で動き（守りを止めない）、窓の起動の時に名指しで知らせる（values_keys）。
  鍵の意味は skill guard:guard-rules の「値の表」。
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import tempfile
from typing import NamedTuple
from datetime import datetime, timezone

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import skill_values as SV  # noqa: E402  値の表の 1 本の口（土台の skill-values/ への symlink）

DEFAULTS = SV.defaults("guard")

# 窓の種類の決まり（session-watch の title-mark と同じ線）: 最初の頼みの文の返し先が別の窓なら子の窓（文脈の知らせだけが読む）。
RETURN_TO_WINDOW = re.compile(r"返し先\s*[=＝:：]\s*session_[A-Za-z0-9]+")
CHILD_OF = re.compile(r"（親窓\s*session_[A-Za-z0-9]+\s*の子）")


GUARD_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sibling_plugin_file(plugin, rel, guard_root=None):
    """隣の plugin の file の path か ""。正本を写さず直に読むための在り処探し。
    repo の形: plugins/guard と plugins/<plugin> が隣。
    入れた plugin の形: cache/<市場>/guard/<版> と cache/<市場>/<plugin>/<同じ版>。
    同じ版だけを見る（別の版へ降りない＝正本と guard の版が食い違ったまま照らさない。見つからなければ "" で、
    呼ぶ側が止めて「同じ版で入れ直す」と名指しする）。"""
    here = guard_root or GUARD_ROOT
    cand = os.path.join(os.path.dirname(here), plugin, rel)
    if os.path.isfile(cand):
        return cand
    ver = os.path.basename(here)
    market = os.path.dirname(os.path.dirname(here))
    same = os.path.join(market, plugin, ver, rel)
    return same if os.path.isfile(same) else ""


def foundation_file(rel, guard_root=None):
    """土台の repo の根からの file（plugin の外・例 public-guard/guard.py）の path か ""。
    repo の形: plugins/guard の 2 つ上が repo の根。
    入れた plugin の形: <plugins>/cache/<市場>/guard/<版> → <plugins>/marketplaces/<市場>/（市場の取り出し＝repo 全体）。"""
    here = guard_root or GUARD_ROOT
    cand = os.path.join(os.path.dirname(os.path.dirname(here)), rel)
    if os.path.isfile(cand):
        return cand
    market = os.path.dirname(os.path.dirname(here))
    cache = os.path.dirname(market)
    cand = os.path.join(os.path.dirname(cache), "marketplaces", os.path.basename(market), rel)
    return cand if os.path.isfile(cand) else ""


def load_module(name, path):
    """path の .py を名前 name で読み込む（正本を写さず直に呼ぶ）。読めなければ例外。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def project_dir(payload=None):
    d = os.environ.get("CLAUDE_PROJECT_DIR") or ""
    if not d and isinstance(payload, dict) and isinstance(payload.get("cwd"), str):
        d = payload["cwd"]
    return d


def _starts(payload):
    root = project_dir(payload)
    return [root] if root else []


def values(payload=None):
    """値の表の "guard" を既定に重ねて返す。読めない・問題のある鍵は既定のまま（名指しは values_problems）。"""
    out = dict(DEFAULTS)
    try:
        got, _ = SV.section("guard", strict=False, starts=_starts(payload))
    except Exception:  # noqa: BLE001  見張りの故障で窓を止めない
        return out
    for k, v in got.items():
        if k in DEFAULTS and v is not None:
            out[k] = v
    return out


# ── 跡の形（会話ログの道具の呼び出しを、名と入力の欄で見る）──
# 形: "<正規表現>"（道具の名の全体に当てる）か {"tool": "<正規表現>", "input": {"<欄>": "<正規表現>"}}（名の全体と、挙げた入力の欄
# 〔a.b で下の欄〕の全部に当たる時）。入力を JSON の字に直して当てない＝その字を入力に含むだけの呼び出しを跡に数えない。
def compile_matcher(spec):
    """跡の形 1 つを (名の正規表現, {欄: 正規表現}) に。読めない形は ValueError か re.error。"""
    if isinstance(spec, str):
        spec = {"tool": spec}
    if not isinstance(spec, dict) or not set(spec) <= {"tool", "input"}:
        raise ValueError('形が違う（文字列か {"tool": …, "input": {…}}）')
    tool = spec.get("tool")
    if not isinstance(tool, str) or not tool:
        raise ValueError("tool が無い")
    if '"' in tool or re.search(r"\s", tool):
        raise ValueError("道具の名に当たらない形（入力の JSON に当てる古い形は読まない。入力は input の欄で書く）")
    fields = spec.get("input") or {}
    if not isinstance(fields, dict) or not all(isinstance(k, str) and k and isinstance(v, str) and v
                                               for k, v in fields.items()):
        raise ValueError("input は {欄の名: 正規表現}")
    return re.compile(tool), {k: re.compile(v) for k, v in fields.items()}


def tool_matchers(vals, key):
    """値の表の跡の形の並びを (読める形の並び, 壊れた形の名指しの並び) に。壊れた形は跡に数えない（数える側に倒さない）。"""
    ok, bad = [], []
    for spec in vals.get(key) or []:
        try:
            ok.append(compile_matcher(spec))
        except (ValueError, TypeError, re.error) as e:
            bad.append("跡の形として読めない %s（%s）" % (json.dumps(spec, ensure_ascii=False)[:160], e))
    return ok, bad


def tool_uses(row):
    """assistant の行の道具の呼び出し（tool_use の塊）の並び。"""
    if row.get("type") != "assistant":
        return []
    msg = row.get("message")
    c = msg.get("content") if isinstance(msg, dict) else None
    return [b for b in c if isinstance(b, dict) and b.get("type") == "tool_use"] if isinstance(c, list) else []


def _field(inp, path):
    """入力の欄（a.b で下の欄）の値を字で。無ければ None。"""
    cur = inp
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur if isinstance(cur, str) else json.dumps(cur, ensure_ascii=False, sort_keys=True)


def matches_tool(block, matchers):
    """道具の呼び出し 1 つが跡の形のどれかに当たるか（名の全体と、挙げた欄の全部）。"""
    name = str(block.get("name") or "")
    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
    for rx, fields in matchers:
        if rx.fullmatch(name) and all(_hit(frx, _field(inp, k)) for k, frx in fields.items()):
            return True
    return False


def _hit(rx, text):
    return text is not None and bool(rx.search(text))


# ── Bash の命令を語に分ける（命令の字に正規表現を当てず、走る命令を見分ける）──
# 読み切れない形は「知らない」と返す（unknowns）。呼ぶ側はそれを照らす側に倒す＝知っている形の表に無い形を、黙って通さない。
SHELLS = ("bash", "sh", "zsh", "dash", "ksh")
# 後ろの命令をそのまま走らせる前置き → その前置きが値を取る option（値を取らない option は "-" で始まる語として飛ばす）
PREFIXES = {
    "env": ("-u", "--unset", "-C", "--chdir"),
    "command": (), "builtin": (), "exec": ("-a",), "nohup": (), "time": ("-f", "--format", "-o", "--output"),
    "sudo": ("-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "--close-from", "-D", "--chdir",
             "-r", "--role", "-t", "--type", "-U", "--other-user", "-T", "--command-timeout"),
    "nice": ("-n", "--adjustment"), "stdbuf": ("-i", "-o", "-e", "--input", "--output", "--error"),
    "timeout": ("-s", "--signal", "-k", "--kill-after"),
    "xargs": ("-a", "--arg-file", "-d", "--delimiter", "-E", "-e", "-I", "-i", "-L", "-l", "-n", "--max-args", "-P",
              "--max-procs", "-s", "--max-chars"),
}
# 引数を命令として走らせない（と分かっている）命令。ここに無い命令の引数に git・シェルの語・変数の展開が在れば読み切れないと見る
NONEXEC = frozenset(("echo", "printf", "grep", "egrep", "fgrep", "rg", "cat", "head", "tail", "wc", "test", "[", "true",
                     "false", "ls", "cd", "pushd", "popd", "pwd", "jq", "diff", "sort", "uniq", "tr", "cut", "basename",
                     "dirname", "realpath", "readlink", "mkdir", "touch", "git"))
KEYWORDS = ("!", "{", "}", "then", "do", "else", "elif", "if", "while", "until", "fi", "done")
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
_OPS = (";;&", "<<-", "<<<", "&>>", "&&", "||", "|&", ";;", ";&", ">>", "<<", ">&", "<&", "&>", ">|", "<>",
        ";", "&", "|", "(", ")", "<", ">", "\n")
_REDIRS = frozenset(("<", ">", ">>", "<<", "<<-", "<<<", ">&", "<&", "&>", "&>>", ">|", "<>"))
_GIT_WORD = re.compile(r"(?<![\w.-])git(?![\w-])")


class Unknown(NamedTuple):
    """parse_shell の読み切れない所 1 つ。code は機械で分ける変わらない名（呼ぶ側は code で決め、message の字に正規表現を当てない）。
    message は人が読む訳。"""
    code: str
    message: str


# Unknown.code の全部（足す時はここと試験に足す）
UNKNOWN_CODES = frozenset((
    "subst",             # $(…)
    "backtick",          # `…`
    "process_subst",     # <(…)・>(…)
    "unclosed_quote",    # 閉じない引用符
    "var_program",       # 命令の名が変数の展開・命令の置き換え
    "function_def",      # function f・f ()
    "compound",          # case・coproc・select
    "subshell",          # ( … )
    "pipe_to_shell",     # … | bash
    "heredoc_to_shell",  # bash <<EOF・bash <<< '…'・bash < file
    "exec_shell",        # bash -c の中が変数などで読めない
    "dash_c_dashdash",   # bash -c -- '…'
    "env_S",             # env -S
    "eval_dyn",          # eval の中が変数の展開
    "unknown_wrapper",   # 表に無い命令が引数の命令を走らせるかを読めない（flock・watch・find -exec など）
    "git_alias",         # git -c alias.…
    "nesting_deep",      # bash -c・eval の入れ子が深い
    "not_text",          # 命令が字でない
))


class _Word(str):
    """語（引用を外した字）。dyn＝変数・命令の置き換えなど、走る時まで値の決まらない所を含む。"""
    dyn = False


def _skip_group(s, i, open_, close):
    """s[i] が open_ の所から、対になる close の次の位置（入れ子を数える。閉じなければ len(s)）。"""
    depth = 0
    while i < len(s):
        if s[i] == open_:
            depth += 1
        elif s[i] == close:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(s)


def _dollar(s, i, unknowns, where):
    """s[i] == "$" の所を読む。(次の位置, 足す字, 値が決まらないか)。"""
    nxt = s[i + 1:i + 2]
    if nxt == "(":
        unknowns.append(Unknown("subst", "%s$(…) の命令の置き換え" % where))
        return _skip_group(s, i + 1, "(", ")"), "", True
    if nxt == "{":
        return _skip_group(s, i + 1, "{", "}"), "", True
    m = re.match(r"[A-Za-z_][A-Za-z0-9_]*|[0-9#?$!@*-]", s[i + 1:])
    if m:
        return i + 1 + m.end(), "", True
    return i + 1, "$", False


def _lex(s, unknowns):
    """字を ("w", 語) と ("op", 区切り) の並びに。ヒアドキュメントの本文は外す。注は語の頭の # から行の末まで。"""
    toks, i, n, pending = [], 0, len(s), []
    cur = None                                              # 今の語の字の並び（None＝語の外）
    dyn = False

    def flush():
        nonlocal cur, dyn
        if cur is not None:
            w = _Word("".join(cur))
            w.dyn = dyn
            toks.append(("w", w))
        cur, dyn = None, False

    def word():
        nonlocal cur
        if cur is None:
            cur = []

    while i < n:
        c = s[i]
        if c in " \t\r":
            flush()
            i += 1
        elif c == "\n":
            flush()
            toks.append(("op", "\n"))
            i += 1
            for delim, tabs in pending:                     # ヒアドキュメントの本文を区切りの行まで外す
                while i < n:
                    j = s.find("\n", i)
                    line, i = (s[i:], n) if j < 0 else (s[i:j], j + 1)
                    if (line.lstrip("\t") if tabs else line) == delim:
                        break
            pending = []
        elif c == "#" and cur is None:
            j = s.find("\n", i)
            i = n if j < 0 else j
        elif c == "\\":
            if s[i + 1:i + 2] == "\n":
                i += 2
            else:
                word()
                cur.append(s[i + 1:i + 2])
                i += 2
        elif c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                unknowns.append(Unknown("unclosed_quote", "引用符 ' が閉じない"))
                flush()
                return toks
            word()
            cur.append(s[i + 1:j])
            i = j + 1
        elif c == '"':
            word()
            i += 1
            while i < n and s[i] != '"':
                ch = s[i]
                if ch == "\\" and i + 1 < n and s[i + 1] in '$`"\\\n':
                    if s[i + 1] != "\n":
                        cur.append(s[i + 1])
                    i += 2
                elif ch == "$":
                    i, add, d = _dollar(s, i, unknowns, "引用の中の ")
                    cur.append(add)
                    dyn = dyn or d
                elif ch == "`":
                    unknowns.append(Unknown("backtick", "引用の中の `…` の命令の置き換え"))
                    j = s.find("`", i + 1)
                    i, dyn = (n if j < 0 else j + 1), True
                else:
                    cur.append(ch)
                    i += 1
            if i >= n:
                unknowns.append(Unknown("unclosed_quote", '引用符 " が閉じない'))
                flush()
                return toks
            i += 1
        elif c == "$":
            word()
            if s[i + 1:i + 2] == "'":                       # $'…'（中の \ の書き替えは読まず、値が決まらない語と見る）
                j = i + 2
                while j < n and s[j] != "'":
                    j += 2 if s[j] == "\\" else 1
                if j >= n:
                    unknowns.append(Unknown("unclosed_quote", "引用符 $' が閉じない"))
                    flush()
                    return toks
                cur.append(s[i + 2:j])
                i, dyn = j + 1, True
            else:
                i, add, d = _dollar(s, i, unknowns, "")
                cur.append(add)
                dyn = dyn or d
        elif c == "`":
            unknowns.append(Unknown("backtick", "`…` の命令の置き換え"))
            word()
            j = s.find("`", i + 1)
            i, dyn = (n if j < 0 else j + 1), True
        elif c in "<>" and s[i + 1:i + 2] == "(":
            unknowns.append(Unknown("process_subst", "%s(…) のプロセスの置き換え" % c))
            word()
            i, dyn = _skip_group(s, i + 1, "(", ")"), True
        elif c in ";&|()<>":
            if c in "<>" and cur is not None and not dyn and "".join(cur).isdigit():
                cur = None                                  # 2>&1 の 2（fd の番号）は語でない
            flush()
            op = next(o for o in _OPS if s.startswith(o, i))
            toks.append(("op", op))
            i += len(op)
            if op in ("<<", "<<-"):                         # 区切りの語を先に読み、次の改行の後の本文を外す
                m = re.match(r"[ \t]*(\S+)", s[i:])
                if m:
                    delim = re.sub(r"[\"'\\]", "", m.group(1))
                    toks.append(("w", _Word(delim)))
                    pending.append((delim, op == "<<-"))
                    i += m.end()
        else:
            word()
            cur.append(c)
            i += 1
    flush()
    return toks


def _strip_prefix(argv, unknowns):
    """前の代入（A=1）と前置き（env・command・time・sudo・nice・xargs など）を外した、実際に走る命令の語の並び。"""
    i = 0
    while i < len(argv):
        w = argv[i]
        if (ASSIGN.match(w) and not w.dyn) or w in KEYWORDS:
            i += 1
            continue
        name = os.path.basename(w)
        if name not in PREFIXES or w.dyn:
            break
        takes = PREFIXES[name]
        i += 1
        if name == "timeout":
            while i < len(argv) and argv[i].startswith("-"):
                i += 2 if argv[i] in takes else 1
            i += 1                                          # 時間の語
            continue
        while i < len(argv):
            w = argv[i]
            if w == "--":
                i += 1
                break
            if name == "env" and (w in ("-S", "--split-string") or w.startswith(("-S", "--split-string="))):
                unknowns.append(Unknown("env_S", "env -S（字を分けて走らせる）"))
                return []
            if name == "env" and ASSIGN.match(w):
                i += 1
            elif w.startswith("-") and len(w) > 1:
                i += 2 if w in takes else 1
            elif name == "nice" and re.fullmatch(r"[+-]?\d+", w):
                i += 1
            else:
                break
    return argv[i:]


def _command(words, depth, out, unknowns, stdin_redir=False):
    """単純な命令 1 つ（語の並び）を、走る命令の語の並びとして out に足す。読み切れない所は unknowns に足す。"""
    if not words:
        return
    head = words[0]
    if head == "function":
        unknowns.append(Unknown("function_def", "関数の定義（function）"))
        return
    if head in ("case", "coproc", "select"):
        unknowns.append(Unknown("compound", "%s の形" % head))
        return
    if head in ("for", "[["):
        return                                              # 繰り返しの頭・条件の式は命令を走らせない（中の $(…) は上で拾う）
    argv = _strip_prefix(words, unknowns)
    if not argv:
        return
    if argv[0].dyn:
        unknowns.append(Unknown("var_program", "命令の名が変数の展開・命令の置き換え"))
        return
    name = os.path.basename(argv[0])
    if name in SHELLS:
        j, inline, from_stdin = 1, False, False
        while j < len(argv):
            w = argv[j]
            if w in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
                j += 2
            elif w == "--":
                if inline:
                    unknowns.append(Unknown("dash_c_dashdash", "%s -c の後の --" % name))
                    return
                j += 1
                break
            elif w.startswith("--"):
                j += 1
            elif w[:1] in "-+" and len(w) > 1:
                inline = inline or (w[0] == "-" and "c" in w[1:])
                from_stdin = from_stdin or (w[0] == "-" and "s" in w[1:])
                j += 1
            else:
                break
        if inline:
            if j >= len(argv) or argv[j].dyn:
                unknowns.append(Unknown("exec_shell", "%s -c の中が読めない" % name))
                return
            _parse(argv[j], depth + 1, out, unknowns)
            return
        if j >= len(argv) or from_stdin:
            if stdin_redir:
                unknowns.append(Unknown("heredoc_to_shell", "ヒアドキュメント・<<<・< でシェル（%s）へ流す命令" % name))
            else:
                unknowns.append(Unknown("pipe_to_shell", "標準入力からシェル（%s）へ流す命令（| %s）" % (name, name)))
            return
        out.append(list(argv))                              # 別の script を走らせる（中は読まない）
        return
    if name == "eval":
        if any(w.dyn for w in argv[1:]):
            unknowns.append(Unknown("eval_dyn", "eval の中が変数の展開"))
            return
        _parse(" ".join(argv[1:]), depth + 1, out, unknowns)
        return
    if name not in NONEXEC:
        if any(w.dyn for w in argv[1:]):
            unknowns.append(Unknown("unknown_wrapper", "表に無い命令 %s の引数に変数の展開（走らせる命令を読めない）" % name[:40]))
        elif any(_GIT_WORD.search(w) or w in SHELLS or w == "eval" for w in argv[1:]):
            unknowns.append(Unknown("unknown_wrapper", "表に無い命令 %s が引数の命令を走らせるかを読めない" % name[:40]))
    if name == "git" and any(re.match(r"alias\.", w) for w in argv[1:]):
        unknowns.append(Unknown("git_alias", "git の別名（alias.）"))
    out.append(list(argv))                                  # 語は _Word（dyn＝走る時まで値の決まらない語）のまま返す


def _parse(cmd, depth, out, unknowns):
    if depth > 4:
        unknowns.append(Unknown("nesting_deep", "bash -c・eval の入れ子が深い"))
        return
    toks = _lex(cmd, unknowns)
    words, k, stdin_redir = [], 0, False
    while k <= len(toks):
        kind, val = toks[k] if k < len(toks) else ("op", ";")
        if kind == "w":
            words.append(val)
        elif val in _REDIRS:
            stdin_redir = stdin_redir or val in ("<", "<<", "<<-", "<<<")
            k += 1                                          # 先の語（ファイル・区切り）は命令の語でない
        else:
            if val == "(":
                if words and k + 1 < len(toks) and toks[k + 1] == ("op", ")"):
                    unknowns.append(Unknown("function_def", "関数の定義（%s ()）" % words[-1][:40]))
                    k += 2
                    words = []
                    continue
                if not words:
                    unknowns.append(Unknown("subshell", "subshell の組 ( … )"))
            _command(words, depth, out, unknowns, stdin_redir)
            words, stdin_redir = [], False
        k += 1


def parse_shell(cmd: str) -> tuple[list[list[str]], list[Unknown]]:
    """Returns (simple_commands, unknowns). simple_commands = argv lists after stripping known prefixes (VAR=, env, command,
    builtin, exec, time, nice, nohup, sudo, timeout, stdbuf, xargs) and descending into `bash|sh|zsh -c <literal>` and
    `eval <literal>`. Heredoc bodies are removed. Comments only start at a `#` that begins a word. unknowns = Unknown(code,
    message) tuples (code in UNKNOWN_CODES; callers decide by code, never by matching message) for anything not fully
    understood: $(…), backticks, variables in the program position, unclosed quotes, function definitions, pipes into a
    shell (| bash), find -exec / xargs with a shell, flock/other wrappers not in the list, `--` after -c, subshell groups.

    純（外を読まない・標準の道具だけ）。読み切れない形は unknowns に名指しで返す＝呼ぶ側が照らす側に倒す。"""
    out, unknowns = [], []
    if isinstance(cmd, str):
        _parse(cmd, 0, out, unknowns)
    else:
        unknowns.append(Unknown("not_text", "命令が字でない"))
    return out, unknowns


def is_dyn(word):
    """parse_shell の返した語が、変数の展開・命令の置き換えなど走る時まで値の決まらない所を含むか。"""
    return bool(getattr(word, "dyn", False))


# ── 走った証（呼び出しを tool_use_id で返りに結ぶ）──
# 字から読めても走ったとは限らない（拒まれた・hook に止められた・中断した）。走ったかは同じ tool_use_id の返りで見る。
EXIT_CODE = re.compile(r"\AExit code -?\d+\b")
EMPTY_OUTPUT = {"", "(No content)", "(Bash completed with no output)", "(no output)"}


def tool_results(row):
    """user の行の道具の返り（tool_result の塊）の並び。"""
    if row.get("type") != "user":
        return []
    msg = row.get("message")
    c = msg.get("content") if isinstance(msg, dict) else None
    return [b for b in c if isinstance(b, dict) and b.get("type") == "tool_result"] if isinstance(c, list) else []


def result_text(res):
    c = (res or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(str(b.get("text") or "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def result_state(res):
    """返り 1 つの読み: "ok"（誤りなく返った）・"exit"（Bash が走って 0 でない数で終わった＝返りの頭が Exit code N）・
    "none"（返りが無い）・"no"（拒まれた・hook に止められた・中断・読めない＝走った証にしない）。"""
    if not isinstance(res, dict):
        return "none"
    if res.get("is_error") is not True:
        return "ok"
    return "exit" if EXIT_CODE.match(result_text(res)) else "no"


def tool_use_ran(transcript_rows, tool_use_id):
    """道具の呼び出し 1 つ（tool_use の id）が実際に走ったか。(走ったか, 返りの字, 走ったと見ない理由)。
    走った＝同じ tool_use_id の返りが在り、is_error が偽か、is_error が真で返りの頭が Exit code N（Bash が走って 0 でない数で
    終わった＝物差しが赤を返した等）。走ったと見ない＝返りが無い・is_error の欄が無い（走った証が読めない）・拒まれた・hook に
    止められた・中断した（is_error が真で Exit code で始まらない）。transcript_rows は会話ログの行（dict）の並び。"""
    if not tool_use_id:
        return False, "", "tool_use の id が無い"
    for row in transcript_rows:
        if not isinstance(row, dict):
            continue
        for res in tool_results(row):
            if res.get("tool_use_id") != tool_use_id:
                continue
            text = result_text(res)
            if "is_error" not in res:
                return False, text, "返りに is_error の欄が無い"
            state = result_state(res)
            if state in ("ok", "exit"):
                return True, text, ""
            return False, text, "拒まれた・hook に止められた・中断した返り"
    return False, "", "返りが無い"


def table(section, payload=None):
    """値の表の 1 つの節を dict で返す（無い・読めない時は {}）。探し方は値の表の 1 本の口（lib/skill_values.py）。他の plugin の口も使う。"""
    try:
        tbl, _ = SV.load(SV.find(starts=_starts(payload)))
    except Exception:  # noqa: BLE001  見張りの故障で窓を止めない
        return {}
    got = tbl.get(section) if isinstance(tbl, dict) else None
    return got if isinstance(got, dict) else {}


def values_problems(payload=None):
    """(表の path, 表全体の問題の並び)。表が無ければ (None, [])。"""
    path = SV.find(starts=_starts(payload))
    table, problems = SV.load(path)
    return path, problems + SV.check(table)


def truthy(v):
    v = str(v or "").strip().lower()
    return bool(v) and v not in ("0", "false", "no", "off")


def unattended_by_env(vals, env=None):
    env = os.environ if env is None else env
    return any(truthy(env.get(name)) for name in vals.get("unattended_env") or [] if isinstance(name, str))


def safe_id(text, limit=120):
    return "".join(c for c in str(text or "") if c.isalnum() or c in "-_.")[:limit].strip(".")


def tmp_dir(kind):
    """1 つの窓の中で閉じる印の置き場（窓をまたぐ道に使わない）。AF_GUARD_TMP で差し替える（試験）。"""
    base = os.environ.get("AF_GUARD_TMP") or os.path.join(tempfile.gettempdir(), "af-guard")
    return os.path.join(base, kind)


def state_dir(vals, payload=None):
    """窓をまたいで残す台帳の置き場。AF_GUARD_STATE で差し替える（試験）。"""
    d = os.environ.get("AF_GUARD_STATE") or vals.get("state_dir") or DEFAULTS["state_dir"]
    d = os.path.expanduser(d)
    if not os.path.isabs(d):
        root = project_dir(payload)
        if not root:
            return ""
        d = os.path.join(root, d)
    return d


GUARD_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_ts(text):
    """ISO 8601 の時刻を UTC の datetime に。読めなければ None（Z と +09:00 を字で比べない）。"""
    t = str(text or "").strip()
    if not t:
        return None
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    m = re.match(r"^(.*T\d\d:\d\d:\d\d)(\.\d+)?(.*)$", t)
    if m:   # 小数の桁を 6 に揃える（古い fromisoformat 向け）
        frac = (m.group(2) or ".0")[1:7].ljust(6, "0")
        t = "%s.%s%s" % (m.group(1), frac, m.group(3))
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


# ── 会話ログ（transcript の JSONL）──
def iter_rows(path, tail_bytes=0):
    """1 行ずつ dict で返す（壊れ行は飛ばす）。tail_bytes>0 なら末尾だけ読む。"""
    with open(path, "rb") as f:
        if tail_bytes:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            raw = f.read()
            if size > tail_bytes and b"\n" in raw:
                raw = raw.split(b"\n", 1)[1]
        else:
            raw = f.read()
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            yield row


def text_of(row):
    msg = row.get("message")
    c = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text") or "" for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


# 人がタイプした行の見分け（1 か所）: 印の無さで人と決めず、人がタイプした行の形が全部そろう時だけ人に数える（既定で人に数えない）。
# 形の外の行（知らない印の付いた行・知らない中身の塊）は人に数えない＝go や席に戻った跡にならない側（止める側）へ倒れる。
NOT_TYPED_FLAGS = ("isMeta", "isCompactSummary", "isVisibleInTranscriptOnly", "isSidechain")
TYPED_BLOCKS = ("text", "image")
# 人の字でなく Claude Code や別の窓が user の行に書く頭（中断の印・知らせ・別の窓の頼み・hook の差し戻し・手元の命令の出力）
NOT_TYPED_HEADS = ("[Request interrupted", "<task-notification", "Another Claude session sent a message",
                   "Stop hook feedback:", "<local-command-", "<command-", "Caveat:", "This session is being continued")
_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
_ENVELOPE = re.compile(r"\A<[A-Za-z][\w-]*[\s>]")


def is_human_prompt(row):
    """人がタイプした頼みの行か。人に数えるのは次が全部そろう時だけ:
    type が user・道具の返り（toolUseResult・tool_result の塊）でない・NOT_TYPED_FLAGS のどれも立たない・origin が無い・
    promptSource が無いか user・中身が字（か字と画像の塊だけ）・system-reminder を除いた字が空でない・
    頭が NOT_TYPED_HEADS でも <名…> の包みでもない。"""
    if not isinstance(row, dict) or row.get("type") != "user" or "toolUseResult" in row:
        return False
    if any(row.get(k) for k in NOT_TYPED_FLAGS) or "origin" in row:
        return False
    if row.get("promptSource") not in (None, "user"):
        return False
    msg = row.get("message")
    c = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(c, list):
        if not c or not all(isinstance(b, dict) and b.get("type") in TYPED_BLOCKS for b in c):
            return False
    elif not isinstance(c, str):
        return False
    text = _REMINDER.sub("", text_of(row)).strip()
    return bool(text) and not text.startswith(NOT_TYPED_HEADS) and not _ENVELOPE.match(text)


def is_owner_row(row):
    """人がタイプした行か（is_human_prompt と同じ 1 つの見分け）。"""
    return is_human_prompt(row)


def _prompt_like(row):
    """窓の最初の頼みを読む口: 道具の返りと差し戻し（isMeta）でない user の行。子の窓の印（返し先）を読むために、
    人の行より広く取る（狭めると親の頼みを読み落とし、子の窓を人のいる窓と取り違える＝止めない側へ倒れる）。"""
    return (row.get("type") == "user" and not row.get("isMeta") and "toolUseResult" not in row
            and bool(text_of(row).strip()))


def first_owner_text(path):
    try:
        for row in iter_rows(path):
            if _prompt_like(row):
                return text_of(row)
    except Exception:
        return ""
    return ""


def is_child_prompt(text):
    return bool(RETURN_TO_WINDOW.search(text or "") or CHILD_OF.search(text or ""))
