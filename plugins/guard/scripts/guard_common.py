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
# 字を書く・探す・見せるだけの道具。並び（|）の全部がこれなら、その並びの引数・heredoc の中身は動かない字。
# 1 つでも外の命令が並びに居れば（echo … | psql・cat <<EOF | sh）、並びの字は全部動く側に数える。
TEXT_ONLY = frozenset(("echo", "printf", "cat", "tee", "grep", "egrep", "fgrep",
                       "head", "tail", "wc", "true", ":", "test", "["))
# 中で命令を動かせる道具は、動かす口の無い形の時だけ字を挙げる側（_text_only）。
# git: 部分命令がこの組で、-c・--config-env・--exec-path・環境変数の前置き（GIT_PAGER など）が無い時だけ。
#   rebase --exec・-c alias.x='!…'・-c core.pager=…・bisect run・submodule foreach・difftool -x・grep -O は動く側。
# gh: 部分命令がこの組（alias・extension・利用者の別名は中で命令を動かせる）で環境変数の前置きが無い時だけ。
# rg: --pre（読む前に命令を通す）と環境変数の前置き（RIPGREP_CONFIG_PATH で --pre を足せる）が無い時だけ。
_GIT_TEXT = frozenset(("commit", "add", "status", "diff", "log", "show", "tag", "fetch", "push", "pull", "checkout",
                       "switch", "branch", "restore", "rm", "mv", "ls-files", "ls-tree", "rev-parse", "merge-base",
                       "blame", "reset", "remote", "stash", "describe", "shortlog", "cat-file", "grep"))
_GIT_EXEC_OPT = re.compile(r"^(?:-c|--config-env(?:=.*)?|--exec-path(?:=.*)?|-x|--exec(?:=.*)?|--extcmd(?:=.*)?"
                           r"|-O.*|--open-files-in-pager(?:=.*)?|--ext-diff|-c.+)$", re.S)
_GH_TEXT = frozenset(("pr", "issue", "api", "release", "search", "label", "repo", "run", "workflow", "browse",
                      "gist", "status", "secret", "variable", "cache", "ruleset", "project"))
_ENV = re.compile(r"[A-Za-z_]\w*=.*", re.S)
_REDIR = re.compile(r"\d*[<>]+&?\d*-?")


def _text_only(words):
    """1 つの命令（環境変数の前置きと語の並び）が字を挙げるだけか。"""
    k = 0
    while k < len(words) and _ENV.fullmatch(words[k]):
        k += 1
    env = words[:k]                       # 頭の環境変数の前置きだけ（引数の a=b は前置きでない）
    ws = [w for w in words[k:] if not _REDIR.fullmatch(w) and w != "\x00SB\x00"]
    if not ws:
        return True
    prog = os.path.basename(ws[0])
    if prog in TEXT_ONLY:
        return True
    args = ws[1:]
    if prog == "rg":
        return not env and not any(a == "--pre" or a.startswith("--pre=") or a.startswith("--pre-glob") for a in args)
    if prog == "git":
        if env or any(_GIT_EXEC_OPT.match(a) for a in args):
            return False
        sub = next((a for a in args if not a.startswith("-")), "")
        return sub in _GIT_TEXT
    if prog == "gh":
        sub = next((a for a in args if not a.startswith("-")), "")
        return not env and sub in _GH_TEXT
    return False


def _writes(words):
    """字を挙げるだけの命令が書く先の file（> と >> の的・tee の引数）。"""
    out, prev = [], ""
    for w in words:
        if prev in (">", ">>", ">|", "&>", "&>>") or re.fullmatch(r"\d*>>?\|?", prev or "-"):
            out.append(w)
        prev = w
    k = 0
    while k < len(words) and _ENV.fullmatch(words[k]):
        k += 1
    ws = words[k:]
    if ws and os.path.basename(ws[0]) == "tee":
        out += [w for w in ws[1:] if not w.startswith("-")]
    return [w for w in out if w not in ("/dev/null", "/dev/stdout", "/dev/stderr", "-")]


_HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_][\w.-]*)\2")
_OPS = frozenset(("&&", "||", ";", "&", ";;", "\n"))


class _Unread(Exception):
    """読み切れない形（閉じない引用・heredoc・$( )、` `・<( )）。"""


def _scan(cmd, i=0, sub=False):
    """命令の字を頭から読み、(heredoc の中身と $( ) を印に置き換えた字, heredoc の中身の並び, $( ) の中で動く並び, 終わりの位置)。
    印は \\x00HDn\\x00（heredoc の中身）と \\x00SB\\x00（$( ) の跡）。注釈（語の頭の #）は落とす。
    sub=True は $( の後から読み、対になる ) で終わる。読み切れなければ _Unread。"""
    out, bodies, inner, pending = [], [], [], []
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
            s_out, s_bodies, s_inner, j = _scan(cmd, i + 2, sub=True)
            parts = _parts(s_out, s_bodies, s_inner)
            inner.extend(s_inner + parts)
            out.append("\x00SB\x00")
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
                return "".join(out), bodies, inner, i + 1
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
    return "".join(out), bodies, inner, i


def _pipelines(flat):
    """印に置き換えた字を並び（| でつないだ命令の組）に分ける。各並びは命令ごとの語の並び。"""
    lex = shlex.shlex(flat, posix=True, punctuation_chars=";&|()<>\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        toks = list(lex)
    except ValueError:
        raise _Unread() from None
    if any(t in ("(", ")", "{", "}") for t in toks):
        raise _Unread()
    pipelines, cur, words = [], [], []
    for t in toks + ["\n"]:
        if t and set(t) <= set(";&\n"):
            if words:
                cur.append(words)
            if cur:
                pipelines.append(cur)
            cur, words = [], []
        elif t in ("|", "|&", "||"):
            if words:
                cur.append(words)
            words = []
            if t == "||":
                pipelines.append(cur)
                cur = []
        else:
            words.append(t)
    return [pl for pl in pipelines if pl]


def _parts(flat, bodies, inner=()):
    """並びごとに、字を挙げるだけの並びを除いた字の並び（heredoc の中身を戻す）。
    字を挙げるだけの並びでも、書いた file を同じ命令の中の動く並び（$( ) の中を含む）が読む形
    （printf '…' > q.sql && psql -f q.sql・cat > a.sh <<EOF … && bash a.sh）は動く側に数える。"""
    pls = _pipelines(flat)
    text_only = [all(_text_only(c) for c in pl) for pl in pls]
    run_words = set()
    for pl, t in zip(pls, text_only):
        if not t:
            for c in pl:
                run_words.update(c)
    for x in inner:
        run_words.update(x.split())
    run_names = run_words | {os.path.basename(w) for w in run_words}
    out = []
    for pl, t in zip(pls, text_only):
        if t:
            targets = [w for c in pl for w in _writes(c)]
            if not any(w in run_names or os.path.basename(w) in run_names for w in targets):
                continue
        text = " ".join(" ".join(c) for c in pl)
        out.append(re.sub(r"\x00HD(\d+)\x00", lambda m: "\n" + bodies[int(m.group(1))] + "\n", text))
    return out


_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")


def _bare_text_only(flat):
    """字を挙げるだけの並びの、引用と heredoc の中身を空にした字（命令そのものの語: git push --force・gh repo delete）。"""
    bare = _QUOTED.sub("''", flat)
    out = []
    for pl in _pipelines(bare):
        if all(_text_only(c) for c in pl):
            text = " ".join(" ".join(c) for c in pl)
            out.append(re.sub(r"\x00(?:HD\d+|SB)\x00", " ", text))
    return out


def executed_parts(cmd):
    """Bash の命令のうち、実際に動かす並び（| でつないだ命令の組）の字の並び。heredoc の中身はその並びに入れ、
    $( ) の中は中で動く並びだけを足す。字を挙げるだけの並び（_text_only: git commit -m の文・grep の語・
    echo・file へ書く heredoc）と注釈は入れない。ただし字を挙げるだけの並びが書いた file を動く並びが読むなら入れる。
    読み切れない形（` `・<( )・括弧の組・閉じない引用や heredoc）は None＝呼ぶ側が命令の字全体で見る（止める側に倒す）。"""
    if not isinstance(cmd, str):
        return None
    try:
        flat, bodies, inner, _ = _scan(cmd)
        return inner + _parts(flat, bodies, inner)
    except _Unread:
        return None


def command_words(cmd):
    """命令の語として当てる字: 動かす並び＋字を挙げるだけの並びの命令そのものの語（引用と heredoc の中身を除く）。
    値の表が git・gh を狙う行（git push --force・gh repo delete）を足していても当たる。読み切れない形は命令の字全体。"""
    if not isinstance(cmd, str):
        return [cmd]
    try:
        flat, bodies, inner, _ = _scan(cmd)
        return inner + _parts(flat, bodies, inner) + _bare_text_only(flat)
    except _Unread:
        return [cmd]


def shell_and_heredocs(cmd):
    """(注釈と heredoc の中身を抜いた命令の字, heredoc の中身の並び)。読み切れない形は None。"""
    try:
        flat, bodies, _inner, _ = _scan(cmd)
    except _Unread:
        return None
    return re.sub(r"\x00(?:HD\d+|SB)\x00", " ", flat), bodies


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
