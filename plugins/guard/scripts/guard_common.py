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


# ── Bash の命令のうち実際に動かす所（字を渡す口の値と分ける） ──
# 外すのは、命令の行が 1 つの素の命令だけの時（_read_whole: shell の特別な字〔改行・| & ; < > $ ` \ ( ) { }・\r〕と引用の外の
# glob の字〔* ? [〕が 1 つも無く、命令の名が path を含まない素の名で、代入・環境へ出す手でない）で、しかもその行の引数が全部
# 「字を渡す口の名」「その口の値」「動かす口が無いと確かめた前置き・その値・位置の引数」のどれかの時だけ（_SLOTS の表）。
# 外すのは口の値（commit の文・grep の型・echo の字など）だけで、前置き・部分命令の語は打った字のまま当てる。
# 道具の名で「字を挙げるだけ」を決めない（git・rg・test・gh と、道具の名で決めた所から同じ類の抜け道が続いたため）。
# 表の外の道具・部分命令・前置き（-c・--・--pre・-O・-w・--editor・--body-file・-p など）が 1 つでも在れば外さず、
# 呼ぶ側が前の版と同じく打った字（注釈は除く）で見る。shell の読み手が bash と同じに区切る前提にも頼らない。
#
# 表の 1 行の欄:
#   text_long・text_short … 値が字として渡るだけの前置き（その値を外す）
#   val_long・val_short   … 値が字として渡るだけでなく、動かす口も無い前置き（値は打った字のまま当てる）
#   flag_long・flag_short … 値を取らず、動かす口の無い前置き
#   num                   … -5 のような数だけの前置きを通すか
#   pos                   … 位置の引数: "text"＝全部が字（外す）／"pattern"＝最初の 1 つが型（外す・-e が無い時）で
#                           残りは file の名／"inert"＝revision や番号など動かす口の無い字（外さない）／None＝置けない
# 確かめた結果（各道具の引数が評価・実行される口を持たないか）:
#   echo・printf・true・: … 引数を字として出す・捨てるだけ（printf -v は _read_whole が外さない）。前置きも字に数える。
#   grep・egrep・fgrep … 型と file の名を読むだけ。-f（型の file）・-P の外の前置きは表の外。
#   rg … 型と file の名を読むだけ。--pre・-z（外の道具で展開する）は表の外。
#   git commit … -m の文を字として渡すだけ。前置きは動かす口の無い物だけ（-c・--exec-path などの git の前置きは表の外）。
#   git log … --grep・-S・-G の型を字として渡すだけ。-p・--stat・--ext-diff（外の diff・textconv を動かしうる）は表の外。
#   gh pr／issue の create・edit・comment … --title・--body を字として渡すだけ。-w（browser）・-e（editor）・
#   --body-file・`--` は表の外。gh repo clone のように `--` の後を git へ渡す部分命令は表に置かない。
#   test・[ は置かない（bash の組み込みの test -v は配列の添字を算術として評価し、添字の中の $(…) や添字に書いた変数の
#   値が命令を動かす＝bash で確かめた）。cat・head・tail・wc も置かない（字を渡す口が無い＝外して得る物が無い）。
#   git grep も置かない（-O<prog> が当たった file を引数に命令を動かす）。
def _spec(text_long=(), text_short="", val_long=(), val_short="", flag_long=(), flag_short="", num=False, pos=None):
    return {"text_long": frozenset(text_long), "text_short": text_short, "val_long": frozenset(val_long),
            "val_short": val_short, "flag_long": frozenset(flag_long), "flag_short": flag_short, "num": num, "pos": pos}


_ALL_TEXT = _spec(pos="text")
_GREP = _spec(text_long=("--regexp",), text_short="e",
              val_long=("--max-count", "--after-context", "--before-context", "--context", "--include", "--exclude",
                        "--exclude-dir", "--color", "--colour"),
              val_short="mABC",
              flag_long=("--recursive", "--dereference-recursive", "--line-number", "--ignore-case", "--no-ignore-case",
                         "--files-with-matches", "--files-without-match", "--word-regexp", "--line-regexp",
                         "--invert-match", "--count", "--extended-regexp", "--fixed-strings", "--basic-regexp",
                         "--with-filename", "--no-filename", "--only-matching", "--quiet", "--silent", "--no-messages",
                         "--byte-offset", "--null", "--text", "--initial-tab"),
              flag_short="rRnilLwxvcEFGHhosqbZaT", num=True, pos="pattern")
_RG = _spec(text_long=("--regexp",), text_short="e",
            val_long=("--glob", "--iglob", "--type", "--type-not", "--max-count", "--after-context", "--before-context",
                      "--context", "--max-depth", "--sort", "--sortr", "--color", "--max-columns", "--max-filesize"),
            val_short="gtTmABCd",
            flag_long=("--hidden", "--no-ignore", "--no-ignore-vcs", "--line-number", "--no-line-number",
                       "--ignore-case", "--smart-case", "--case-sensitive", "--fixed-strings", "--word-regexp",
                       "--line-regexp", "--invert-match", "--count", "--count-matches", "--files-with-matches",
                       "--files-without-match", "--only-matching", "--no-heading", "--heading", "--json",
                       "--multiline", "--multiline-dotall", "--follow", "--vimgrep", "--no-filename",
                       "--with-filename", "--column", "--null", "--trim", "--stats", "--files", "--no-messages",
                       "--quiet", "--text", "--unrestricted", "--no-config"),
            flag_short="nNiSsFwxvcloUHIqLu.", num=False, pos="pattern")
_GIT_COMMIT = _spec(text_long=("--message",), text_short="m",
                    flag_long=("--all", "--amend", "--no-edit", "--quiet", "--signoff", "--allow-empty",
                               "--allow-empty-message", "--no-verify", "--verbose"),
                    flag_short="aqsnv", pos="inert")
_GIT_LOG = _spec(text_long=("--grep",), text_short="SG",
                 val_long=("--max-count", "--since", "--until", "--after", "--before", "--author", "--committer",
                           "--skip"),
                 val_short="n",
                 flag_long=("--oneline", "--all", "--name-only", "--name-status", "--no-merges", "--merges",
                            "--pickaxe-regex", "--pickaxe-all", "--regexp-ignore-case", "--all-match", "--invert-grep",
                            "--fixed-strings", "--extended-regexp", "--basic-regexp", "--reverse", "--first-parent",
                            "--no-decorate", "--decorate", "--abbrev-commit", "--no-color"),
                 flag_short="iEF", num=True, pos="inert")
_GH_TEXT = _spec(text_long=("--title", "--body"), text_short="tb",
                 val_long=("--base", "--head", "--repo", "--label", "--assignee", "--reviewer", "--milestone",
                           "--add-label", "--remove-label", "--add-assignee", "--remove-assignee"),
                 val_short="BHRlarm",
                 flag_long=("--draft", "--fill"), flag_short="df", pos="inert")
# 命令の頭の語の並び → 表の行。git は頭の語の間に -C <dir>・--no-pager・-P だけを置ける（_head）。
_SLOTS = {("echo",): _ALL_TEXT, ("printf",): _ALL_TEXT, ("true",): _ALL_TEXT, (":",): _ALL_TEXT,
          ("grep",): _GREP, ("egrep",): _GREP, ("fgrep",): _GREP, ("rg",): _RG,
          ("git", "commit"): _GIT_COMMIT, ("git", "log"): _GIT_LOG}
for _k in ("pr", "issue"):
    for _v in ("create", "edit", "comment"):
        _SLOTS[("gh", _k, _v)] = _GH_TEXT
_ENV = re.compile(r"[A-Za-z_]\w*=.*", re.S)
# 素の命令でも、それだけで外さない物とする命令（環境・変数・別名へ出す手・file を書く手・他を読み込む手）。
_UNREAD_PROG = frozenset(("export", "set", "declare", "typeset", "readonly", "local", "unset", "alias", "source", ".",
                          "env", "tee", "shopt", "trap", "hash", "builtin", "command"))


def _head(words):
    """(表の行, 頭の語の数)。表の外は (None, 0)。git の頭の語の間は -C <dir>・--no-pager・-P だけ。"""
    if words[0] == "git":
        i = 1
        while i < len(words) and words[i].startswith("-"):
            if words[i] == "-C" and i + 1 < len(words):
                i += 2
            elif words[i] in ("--no-pager", "-P"):
                i += 1
            else:
                return None, 0                   # -c・--config-env・--exec-path・一覧の外の前置き
        if i < len(words) and ("git", words[i]) in _SLOTS:
            return _SLOTS[("git", words[i])], i + 1
        return None, 0
    for n in (3, 1):
        key = tuple(words[:n])
        if key in _SLOTS:
            return _SLOTS[key], n
    return None, 0


def _text_slots(words):
    """素の 1 つの命令（引用を外した語の並び）で、字を渡す口の値の (位置, 前に残す字) の並び。引数が 1 つでも表の外なら None。
    前に残す字は、--message=… や -m… のように前置きと値が 1 つの語の時の前置きの所（値だけを外す）。"""
    spec, i = _head(words)
    if spec is None:
        return None
    n = len(words)
    if spec["pos"] == "text":
        return [(j, "") for j in range(i, n)]
    out, pattern_given = [], False
    positional = []
    while i < n:
        w = words[i]
        if w.startswith("--") and len(w) > 2:
            name, eq, _val = w.partition("=")
            if name in spec["text_long"]:
                if eq:
                    out.append((i, name + "="))
                elif i + 1 < n:
                    out.append((i + 1, ""))
                    i += 1
                else:
                    return None
                pattern_given = True
            elif name in spec["val_long"]:
                if not eq:
                    if i + 1 >= n:
                        return None
                    i += 1
            elif not (name in spec["flag_long"] and not eq):
                return None
        elif w.startswith("-") and len(w) > 1:
            body = w[1:]
            if spec["num"] and body.isdigit():
                i += 1
                continue
            for k, c in enumerate(body):
                rest = body[k + 1:]
                if c in spec["text_short"]:
                    if rest:
                        out.append((i, "-" + body[:k + 1]))
                    elif i + 1 < n:
                        out.append((i + 1, ""))
                        i += 1
                    else:
                        return None
                    pattern_given = True
                    break
                if c in spec["val_short"]:
                    if not rest:
                        if i + 1 >= n:
                            return None
                        i += 1
                    break
                if c not in spec["flag_short"]:
                    return None
        else:
            positional.append(i)
        i += 1
    if positional:
        if spec["pos"] is None:
            return None
        if spec["pos"] == "pattern" and not pattern_given:
            out.append((positional[0], ""))
    elif spec["pos"] == "pattern" and not pattern_given:
        return None
    return out


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
# glob の字。引用の外に 1 つでも在れば同じく字全体で見る（file の名に開かれ、打った字と動く語がずれる）。引用の中は
# bash でも開かれない（上の特別な字の無い行では、引用は '…' と "…" の素の対だけ＝_QUOTED で外せる）。
_GLOB = frozenset("*?[")


_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def _tokens(line):
    """特別な字の無い行の語の並び [(引用を外した語, 打った字の始め, 終わり)]。閉じない引用は None。"""
    toks, i, n = [], 0, len(line)
    while i < n:
        if line[i] in " \t":
            i += 1
            continue
        start, val = i, []
        while i < n and line[i] not in " \t":
            c = line[i]
            if c in "'\"":
                j = line.find(c, i + 1)
                if j < 0:
                    return None
                val.append(line[i + 1:j])
                i = j + 1
            else:
                val.append(c)
                i += 1
        toks.append(("".join(val), start, i))
    return toks


def _read_whole(cmd):
    """命令の行が 1 つの素の命令だけの時、(注釈を落とした打った字, 語の並び)。shell の特別な字（改行・| & ; < > $ ` \\ ( ) { }・
    \\r）か引用の外の glob の字（* ? [）が 1 つでも在る・命令の名が空か path を含む・代入や環境へ出す手・閉じない引用は None
    （呼ぶ側が命令の字全体で見る）。"""
    if not isinstance(cmd, str) or any(c in _SHELL_SPECIAL for c in cmd):
        return None
    if any(c in _GLOB for c in _QUOTED.sub("", cmd)):
        return None
    line = _strip_comment(cmd)
    toks = _tokens(line)
    if not toks:
        return None
    first = toks[0][0]
    if not first or "/" in first or _ENV.fullmatch(first) or first in _UNREAD_PROG:
        return None
    if first == "printf" and any(t[0].startswith("-v") for t in toks[1:]):
        return None                               # printf -v は変数へ書く
    return line, toks


def _blanked(cmd):
    """(注釈を落とした打った字, 字を渡す口の値を '' にした打った字 or None)。素の命令でない行は None。"""
    read = _read_whole(cmd)
    if read is None:
        return None
    line, toks = read
    slots = _text_slots([t[0] for t in toks])
    if slots is None:
        return line, None
    out, last = [], 0
    for j, keep in sorted(slots):
        _w, s, e = toks[j]
        out.append(line[last:s])
        out.append(keep + "''")
        last = e
    out.append(line[last:])
    return line, "".join(out)


def executed_parts(cmd):
    """Bash の命令のうち実際に動かす所の字の並び。命令の行が 1 つの素の命令で、引数が全部字を渡す口の表（_SLOTS）に収まる
    行（git commit -m '…'・grep の型・echo の字）は [] （外す）、それ以外の素の命令は注釈を落とした打った字 1 つ。素の命令で
    ない行は None＝呼ぶ側が命令の字全体で見る（前の版と同じ判定）。"""
    b = _blanked(cmd)
    if b is None:
        return None
    return [] if b[1] is not None else [b[0]]


def command_words(cmd):
    """命令の語として当てる字（前の版と同じく打った字のまま）。表に収まる行は、字を渡す口の値だけを '' にした打った字
    （前置き・部分命令の語は打った字のまま＝'--force'・'delete' を引用で包んでも当たる）。素の命令で表の外の行は注釈を落とした
    打った字。それ以外は命令の字全体（前の版と同じ）。"""
    if not isinstance(cmd, str):
        return [cmd]
    b = _blanked(cmd)
    if b is None:
        return [cmd]
    return [b[1] if b[1] is not None else b[0]]


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
