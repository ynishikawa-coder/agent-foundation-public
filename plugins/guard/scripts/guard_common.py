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
import shlex
import sys
import tempfile
from datetime import datetime, timezone

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import skill_values as SV  # noqa: E402  値の表の 1 本の口（土台の skill-values/ への symlink）
import af_place as P  # noqa: E402  土台の在り処探しの 1 本の口（同じ symlink）

DEFAULTS = SV.defaults("guard")

# 窓の種類の決まり（session-watch の title-mark と同じ線）: 最初の頼みの文の返し先が別の窓なら子の窓（文脈の知らせだけが読む）。
# 文の返し先は手で書いた写しなので、最初の頼みの行の記録（人が打った頼みでない＝seeded_by_record）と合う時だけ数える。
RETURN_TO_WINDOW = re.compile(r"返し先\s*[=＝:：]\s*session_[A-Za-z0-9]+")
CHILD_OF = re.compile(r"（親窓\s*session_[A-Za-z0-9]+\s*の子）")


GUARD_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sibling_plugin_file(plugin, rel, guard_root=None):
    """隣の plugin の file の path か ""（在り処探しの正本は lib/af_place.py）。"""
    return P.sibling_plugin_file(plugin, rel, guard_root or GUARD_ROOT)


def foundation_file(rel, guard_root=None):
    """土台の repo の根からの file の、入った guard と同じ版の path か ""（在り処探しの正本は lib/af_place.py）。"""
    return P.foundation_file(rel, guard_root or GUARD_ROOT)


load_module = P.load_module


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


def patterns(vals, key, flags=0):
    """値の表 guard の正規表現の鍵を、型の正本（schema.json の against・match）の当て方で読んだ形（SV.hit に渡す）。
    鍵ごとに re.search・fullmatch を書き分けない＝当て方の正本は schema の spec の 1 か所。"""
    return SV.patterns_of("guard", None, key, vals, flags)


def tool_sig(block):
    """道具の呼び出し 1 つの当てる相手: 道具の名・空白 1 つ・入力の JSON（鍵の順に並べた 1 行）。
    値の表 guard.ask_prior_lookup・context_handoff の当てる相手の正本（schema.json の against と同じ形）。"""
    try:
        body = json.dumps(block.get("input") or {}, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        body = str(block.get("input") or "")
    return "%s %s" % (block.get("name") or "", body)


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


def is_owner_row(row):
    """人がタイプした行か（道具の返り・差し戻し〔isMeta〕を除く）。"""
    return (row.get("type") == "user" and not row.get("isMeta") and "toolUseResult" not in row
            and bool(text_of(row).strip()))


# 人が打った頼みの記録（会話ログの行の origin.kind。Claude Code が頼みを受けた口で付ける＝文の中身では変わらない）。
# 正本はここ 1 か所（plugin session-watch も隣の正本としてこれを直に読む＝写さない）。
HUMAN_ORIGINS = ("human", "person")
# 窓の環境の CLAUDE_CODE_CHILD_SESSION は読まない: 公式の文書（code.claude.com/docs/en/env-vars）では「Claude Code が Bash・
# hook・status line で起動する子プロセスに付く 1」で、どの窓でも hook の中では 1＝別の窓が立てた窓の見分けにならない。
# 頼みの行がまだ無い時の見分けは、サーバの記録（get_session の parent_session_id）を AI に読ませる（session-watch の知らせ）。


def seeded_by_record(row):
    """頼みの行が、人が打った物でなく別の窓・仕組みから来た事を、記録が示すか（子の窓の見分けの記録の正本）。
    記録: 頼みの行の origin.kind が人の物でない（別の窓の create_session・send_message・知らせ等）か promptSource が system。
    行が無い・記録が無い・読めない時は False（文だけで子の窓と決めない＝人の窓の側へ倒す）。"""
    if not isinstance(row, dict):
        return False
    origin = row.get("origin")
    if isinstance(origin, dict) and isinstance(origin.get("kind"), str) and origin["kind"]:
        return origin["kind"] not in HUMAN_ORIGINS
    return row.get("promptSource") == "system"


def first_owner_row(path):
    try:
        for row in iter_rows(path):
            if is_owner_row(row):
                return row
    except Exception:
        return None
    return None


def first_owner_text(path):
    row = first_owner_row(path)
    return text_of(row) if row else ""


def is_child_prompt(text, seeded=False):
    """子の窓か。頼みの文の返し先（写し）が別の窓を指し、かつ頼みの行の記録が人の打った物でない時だけ。
    オーナーが引き継ぎの文を貼った窓（記録は人）は、文に親窓や返し先が在っても子の窓にしない。"""
    if not seeded:
        return False
    return bool(RETURN_TO_WINDOW.search(text or "") or CHILD_OF.search(text or ""))


def is_child_log(path):
    """会話ログの最初の頼みの行で子の窓かを決める（文と記録の両方を読む）。"""
    row = first_owner_row(path)
    return bool(row) and is_child_prompt(text_of(row), seeded_by_record(row))


# ── Bash の命令のうち実際に動かす所（字を挙げるだけの所と分ける） ──
# 外すのは、命令の行が 1 つの素の命令だけの時（_read_whole: shell の特別な字〔改行・| & ; < > $ ` \ ( ) { }・\r〕が
# 1 つも無く、命令の名が path を含まない素の名で、代入・環境へ出す手でない）で、それが字を書く・探す・見せるだけの道具の時だけ。
# それ以外は呼ぶ側が命令の字全体で見る（前の版と同じ判定）。shell の読み手が bash と同じに区切る前提に頼らない
# （流れる道を 1 つずつ足して追う作りも、shlex で並びを区切る作りも、bash とのずれでまた抜けたのでやめた）。
TEXT_ONLY = frozenset(("echo", "printf", "cat", "grep", "egrep", "fgrep",
                       "head", "tail", "wc", "true", ":", "test", "["))
# 素の命令でも、それだけで外さない物とする命令（環境・変数・別名へ出す手・file を書く手・他を読み込む手）。
_UNREAD_PROG = frozenset(("export", "set", "declare", "typeset", "readonly", "local", "unset", "alias", "source", ".",
                          "env", "tee", "shopt", "trap", "hash", "builtin", "command"))
# 中で命令を動かせる道具（git・rg・gh）は、前置き（-x・--foo）を「動かす口が無いと分かっている物」の一覧で通し、
# 一覧の外の前置きが 1 つでも在れば動く側に数える（動かす口を数えて外す形は、次の口でまた抜ける＝
# push --receive-pack・fetch --upload-pack）。環境変数の前置き（GIT_PAGER・RIPGREP_CONFIG_PATH など）も動く側。
# git: 部分命令がこの組で、前置きが全部 _GIT_SAFE_OPT の時だけ。部分命令の前は -C <dir>・--no-pager・-P だけ。
# gh: 部分命令がこの組（alias・extension・利用者の別名は中で命令を動かせる）で環境変数の前置きが無い時だけ。
# rg: 前置きが全部 _RG_SAFE_OPT の時だけ（--pre・--pre-glob は一覧の外）。
_GIT_TEXT = frozenset(("commit", "add", "status", "diff", "log", "show", "tag", "fetch", "push", "pull", "checkout",
                       "switch", "branch", "restore", "rm", "mv", "ls-files", "ls-tree", "rev-parse", "merge-base",
                       "blame", "reset", "remote", "stash", "describe", "shortlog", "cat-file", "grep"))
_GIT_GLOBAL_SAFE = frozenset(("--no-pager", "-P", "--no-optional-locks", "--literal-pathspecs"))
_GIT_SAFE_LONG = frozenset((
    "message", "all", "amend", "no-edit", "no-verify", "quiet", "verbose", "signoff", "allow-empty",
    "allow-empty-message", "author", "date", "fixup", "squash", "cleanup", "no-gpg-sign", "file", "reuse-message",
    "oneline", "stat", "shortstat", "numstat", "name-only", "name-status", "cached", "staged", "patch", "no-patch",
    "format", "pretty", "graph", "decorate", "no-decorate", "abbrev-commit", "abbrev", "branches", "remotes", "tags",
    "since", "until", "after", "before", "grep", "committer", "max-count", "skip", "reverse", "first-parent",
    "no-merges", "merges", "follow", "diff-filter", "unified", "word-diff", "color", "no-color",
    "ignore-space-change", "ignore-all-space", "ignore-blank-lines", "merge-base", "porcelain", "short", "branch",
    "untracked-files", "ignored", "abbrev-ref", "show-toplevel", "verify", "is-ancestor", "symbolic-full-name",
    "git-dir", "show-prefix", "list", "contains", "merged", "no-merged", "sort", "points-at", "force",
    "force-with-lease", "force-if-includes", "set-upstream", "set-upstream-to", "unset-upstream", "track",
    "no-track", "delete", "move", "copy", "create", "detach", "orphan", "hard", "soft", "mixed", "keep", "merge",
    "ff-only", "no-ff", "ff", "rebase", "no-rebase", "autostash", "no-autostash", "depth", "deepen",
    "shallow-since", "unshallow", "prune", "prune-tags", "dry-run", "no-tags", "atomic", "follow-tags",
    "include-untracked", "keep-index", "index", "worktree", "source", "ours", "theirs", "others",
    "exclude-standard", "modified", "deleted", "error-unmatch", "full-name", "ignore-case", "line-number",
    "files-with-matches", "count", "word-regexp", "extended-regexp", "fixed-strings", "perl-regexp",
    "invert-match", "long", "exact-match", "always", "dirty", "full-history", "date-order", "topo-order",
    "relative-date", "summary", "check", "raw", "name-rev", "stdin", "intent-to-add", "update", "pathspec-from-file",
    "local", "verbose", "tracking", "upstream", "no-recurse-submodules", "set-head", "sparse", "no-commit",
))
_GIT_SAFE_OPT = re.compile(r"^(?:--|--end-of-options|-\d+|-[abdfmnpqsuvABDFMNPRSUWilrtwEGLIC]+"
                           r"|-[nUSGlMm]\S+|--(?:%s)(?:=.*)?)$" % "|".join(sorted(map(re.escape, _GIT_SAFE_LONG),
                                                                              key=len, reverse=True)), re.S)
_RG_SAFE_LONG = frozenset((
    "files", "hidden", "no-ignore", "no-ignore-vcs", "no-ignore-dot", "glob", "iglob", "type", "type-not",
    "type-list", "json", "no-heading", "heading", "line-number", "no-line-number", "column", "count",
    "count-matches", "files-with-matches", "files-without-match", "fixed-strings", "ignore-case", "smart-case",
    "case-sensitive", "word-regexp", "line-regexp", "invert-match", "only-matching", "context", "before-context",
    "after-context", "max-count", "max-depth", "follow", "multiline", "multiline-dotall", "null", "color",
    "colors", "no-filename", "with-filename", "sort", "sortr", "replace", "trim", "vimgrep", "stats", "text",
    "binary", "encoding", "max-columns", "max-filesize", "passthru", "pcre2", "engine", "unrestricted",
    "no-config", "regexp", "quiet", "no-messages", "field-match-separator", "field-context-separator",
))
_RG_SAFE_OPT = re.compile(r"^(?:--|-\d+|-[ABCEFHILMNSTUVabcefghijlmnopqrstuvwx]+\S*|--(?:%s)(?:=.*)?)$"
                          % "|".join(sorted(map(re.escape, _RG_SAFE_LONG), key=len, reverse=True)), re.S)
_GH_TEXT = frozenset(("pr", "issue", "api", "release", "search", "label", "repo", "run", "workflow", "browse",
                      "gist", "status", "secret", "variable", "cache", "ruleset", "project"))
_ENV = re.compile(r"[A-Za-z_]\w*=.*", re.S)


def _opts_safe(args, safe):
    """引数のうち前置き（- で始まる語・-- の後は path）が全部 safe に当たるか。"""
    for a in args:
        if a == "--":
            return True
        if a.startswith("-") and a != "-" and not safe.match(a):
            return False
    return True


def _git_text(args):
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] == "-C" and i + 1 < len(args):
            i += 2
            continue
        if args[i] not in _GIT_GLOBAL_SAFE:
            return False                  # -c・--config-env・--exec-path・一覧の外の前置き
        i += 1
    if i >= len(args) or args[i] not in _GIT_TEXT:
        return False
    return _opts_safe(args[i + 1:], _GIT_SAFE_OPT)


def _text_only(words):
    """素の 1 つの命令（語の並び）が字を挙げるだけか。命令の名は path を含まない素の名だけ（./grep・~/bin/echo は同じ名の
    別の実行ファイルかもしれない＝動く側）。"""
    if "/" in words[0]:
        return False
    prog = words[0]
    args = words[1:]
    if prog in TEXT_ONLY:
        return True
    if prog == "rg":
        return _opts_safe(args, _RG_SAFE_OPT)
    if prog == "git":
        return _git_text(args)
    if prog == "gh":
        sub = next((a for a in args if not a.startswith("-")), "")
        return sub in _GH_TEXT
    return False


_HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_][\w.-]*)\2")


class _Unread(Exception):
    """読み切れない形（閉じない引用・heredoc・$( )、` `・<( )）。"""


def _scan(cmd, i=0, sub=False):
    """命令の字を頭から読み、(heredoc の中身と $( ) を印に置き換えた字, heredoc の中身の並び, 空の並び〔前の形の名残〕,
    終わりの位置, $( ) の中の字の並び)。印は \\x00HDn\\x00（heredoc の中身）と \\x00SBn\\x00（n 番目の $( ) の跡）。
    注釈（語の頭の #）は落とす。sub=True は $( の後から読み、対になる ) で終わる。読み切れなければ _Unread。"""
    out, bodies, inner, pending, subs = [], [], [], [], []
    n, q, depth = len(cmd), "", 0
    while i < n:
        c = cmd[i]
        if c == "`":
            raise _Unread()
        if q == "'":
            out.append(c)
            q = "" if c == "'" else q
            i += 1
            continue
        if cmd.startswith("$(", i) and not cmd.startswith("$((", i):
            j = _scan(cmd, i + 2, sub=True)[3]
            subs.append(cmd[i + 2:j - 1])     # 中の字（$( ) が在る行は読み切れない形＝executed_parts が None）
            out.append("\x00SB%d\x00" % (len(subs) - 1))
            i = j
            continue
        if q == '"':
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(cmd[i + 1])
                i += 2
                continue
            q = "" if c == '"' else q
            i += 1
            continue
        if c in "'\"":
            q = c
            out.append(c)
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(cmd[i:i + 2])
            i += 2
            continue
        if c == "#" and (i == 0 or cmd[i - 1] in " \t\n;&|("):
            j = cmd.find("\n", i)
            i = n if j < 0 else j            # 注釈は動かない（改行は残す）
            continue
        if cmd.startswith("<(", i) or cmd.startswith(">(", i):
            raise _Unread()
        if sub and c == "(":
            depth += 1
        if sub and c == ")":
            if depth == 0:
                if pending:
                    raise _Unread()
                return "".join(out), bodies, inner, i + 1, subs
            depth -= 1
        if cmd.startswith("<<<", i):
            out.append("<<<")
            i += 3
            continue
        m = _HEREDOC.match(cmd, i)
        if m:
            bodies.append("")
            pending.append((len(bodies) - 1, m.group(3), bool(m.group(1))))
            out.append(" \x00HD%d\x00 " % (len(bodies) - 1))
            i = m.end()
            continue
        if c == "\n" and pending:
            out.append(c)
            i += 1
            for k, word, strip in pending:
                lines = []
                while True:
                    if i >= n:
                        raise _Unread()
                    j = cmd.find("\n", i)
                    line = cmd[i:] if j < 0 else cmd[i:j]
                    i = n if j < 0 else j + 1
                    if (line.lstrip("\t") if strip else line) == word:
                        break
                    lines.append(line)
                bodies[k] = "\n".join(lines)
            pending = []
            continue
        out.append(c)
        i += 1
    if q or pending or sub:
        raise _Unread()
    return "".join(out), bodies, inner, i, subs


# shell の特別な字。命令の行にこの字が 1 つでも在れば、shell の読み手（shlex など）が bash と同じに読む前提に頼らず、
# 前の版と同じく命令の字全体で見る（| の後の改行・\ と改行・\r のように、読み手と bash のずれで抜けた形を作りで無くす）。
_SHELL_SPECIAL = frozenset("\n\r|&;<>$`\\(){}")


def _read_whole(cmd):
    """命令の行が 1 つの素の命令だけの時、その語の並び（引用を外した語）。shell の特別な字（改行・| & ; < > $ ` \\ ( ) { }・\\r）が
    1 つでも在る・命令の名が path を含む・代入や環境へ出す手・閉じない引用は None（呼ぶ側が命令の字全体で見る）。"""
    if not isinstance(cmd, str) or any(c in _SHELL_SPECIAL for c in cmd):
        return None
    try:
        lex = shlex.shlex(_strip_comment(cmd), posix=True)   # 特別な字の無い行で引用を外すだけに使う
        lex.whitespace_split = True
        lex.commenters = ""
        words = list(lex)
    except ValueError:
        return None
    if not words or "/" in words[0] or _ENV.fullmatch(words[0]) or words[0] in _UNREAD_PROG:
        return None
    if words[0] == "printf" and any(a.startswith("-v") for a in words[1:]):
        return None                               # printf -v は変数へ書く
    return words


_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def executed_parts(cmd):
    """Bash の命令のうち実際に動かす所の字の並び。命令の行が 1 つの素の命令の時だけ読み、字を挙げるだけ（_text_only:
    git commit -m '…' の文・grep の語・echo の字）なら [] （外す）、それ以外は注釈を落とした打った字 1 つ。素の命令でない行は
    None＝呼ぶ側が命令の字全体で見る（前の版と同じ判定）。"""
    words = _read_whole(cmd)
    if words is None:
        return None
    return [] if _text_only(words) else [_strip_comment(cmd)]


def command_words(cmd):
    """命令の語として当てる字（前の版と同じく打った字のまま）。1 つの素の命令で字を挙げるだけの行は、引用の中身を空にした
    打った字（命令そのものの語: git push --force・gh repo delete）。素の命令で動く行は注釈を落とした打った字。それ以外は
    命令の字全体（前の版と同じ）。"""
    if not isinstance(cmd, str):
        return [cmd]
    parts = executed_parts(cmd)
    if parts is None:
        return [cmd]
    return parts or [_QUOTED.sub("''", _strip_comment(cmd))]


def _strip_comment(cmd):
    """特別な字の無い行の、引用の外の語の頭の # から後ろ（注釈）を落とした字。"""
    q = ""
    for i, c in enumerate(cmd):
        if q:
            q = "" if c == q else q
        elif c in "'\"":
            q = c
        elif c == "#" and (i == 0 or cmd[i - 1] in " \t"):
            return cmd[:i]
    return cmd


def shell_and_heredocs(cmd):
    """(注釈と heredoc の中身を抜いた命令の字, heredoc の中身の並び)。読み切れない形は None。"""
    try:
        flat, bodies, _inner, _, _subs = _scan(cmd)
    except _Unread:
        return None
    return re.sub(r"\x00(?:HD|SB)\d+\x00", " ", flat), bodies


# ── 書く中身のうちコードの所（注釈・docstring を除く） ──
_HASH_EXT = (".py", ".sh", ".bash", ".zsh", ".rb", ".pl", ".yml", ".yaml", ".toml", ".r")
_SLASH_EXT = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx", ".go", ".java", ".kt", ".kts",
              ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".swift", ".cs", ".scala", ".dart", ".php")


def code_only(text, path):
    """file の中身（全体）から注釈と Python の docstring を除いた字。引用の中の # や // は注釈でない。
    注釈: // と /* */（C 系）・#（Python は引用の外の全部、shell・YAML などは行の頭か空白の後の # だけ＝${#a}・$#・a#b は字）。
    docstring: 括弧の外・前の行が \\ で続かない所で、行の頭から始まる三重引用（文として置いた字＝何にも使われない）。
    括弧の中や続きの行に置いた三重引用（関数の引数・値）はコード。拡張子で注釈の形が決まらない file は字のまま返す。
    file の一部の断片には使わない（断片がどこから始まるか分からない＝呼ぶ側が全体を組んでから渡すか、字のまま見る）。"""
    ext = os.path.splitext(str(path or "").lower())[1]
    hash_, slash = ext in _HASH_EXT, ext in _SLASH_EXT
    if not (hash_ or slash):
        return text
    py = ext == ".py"
    out, i, n, q = [], 0, len(text), ""
    line_head = True                      # 行の頭からここまで空白だけか
    depth = 0                             # 引用の外の括弧の深さ
    cont = False                          # 前の行が \ で続く
    while i < n:
        c = text[i]
        if q:
            if c == "\\" and i + 1 < n:
                out.append(text[i:i + 2])
                i += 2
                continue
            if text.startswith(q, i):
                out.append(q)
                i += len(q)
                q = ""
                continue
            out.append(c)
            i += 1
            continue
        if py and (text.startswith('"""', i) or text.startswith("'''", i)):
            tq = text[i:i + 3]
            j = text.find(tq, i + 3)
            if line_head and depth == 0 and not cont:   # 文として置いた三重引用＝docstring（説明の文）
                i = n if j < 0 else j + 3
                continue
            out.append(text[i:] if j < 0 else text[i:j + 3])
            i = n if j < 0 else j + 3
            line_head = False
            continue
        if hash_ and c == "#" and (py or i == 0 or text[i - 1] in " \t\n"):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if slash and text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if slash and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "'\"" or (slash and c == "`"):
            q = c
            out.append(c)
            line_head = False
            i += 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}" and depth:
            depth -= 1
        out.append(c)
        if c == "\n":
            cont = i > 0 and text[i - 1] == "\\"
            line_head = True
        elif not c.isspace():
            line_head = False
        i += 1
    return "".join(out)


def executed_or_whole(cmd):
    """executed_parts の並び。読み切れない時は命令の字全体を 1 つの並びとして返す（止める側に倒す）。"""
    parts = executed_parts(cmd)
    return [cmd] if parts is None else parts
