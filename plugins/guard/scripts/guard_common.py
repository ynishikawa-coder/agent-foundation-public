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

DEFAULTS = SV.defaults("guard")

# 値の表の鍵のうち、正規表現の並び（壊れた形を values_problems が名指す）と、跡の形の並び
REGEX_LIST_KEYS = ("qa_page_exempt", "ask_pick_one_exempt", "ask_inner_terms_extra", "ask_term_allow", "ask_shape_exempt",
                   "ask_rec_notice_exempt", "ask_prior_exempt", "outbound_secret_allow", "number_request_exempt",
                   "pr_cleanup_exempt_repos", "pr_words_exempt_repos", "public_repos_extra")
# 見張りが自分で読めない形を名指す鍵＝values() で落とさない（ask_shape は分けて知らせ、outbound は鍵を外さず止める）
SELF_NAMED_KEYS = ("ask_term_allow", "ask_inner_terms_extra", "ask_rec_notice_exempt", "outbound_secret_allow")
MATCHER_KEYS = ("ask_prior_lookup", "context_handoff")
PATTERN_DICT_KEYS = ("irreversible_bash_extra", "irreversible_tools_extra")     # [{"pattern": 正規表現, "why": 理由}]

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
    for k in set(REGEX_LIST_KEYS) - set(SELF_NAMED_KEYS):
        out[k] = [p for p in out[k] if _regex_ok(p)]   # 読めない正規表現は渡さない（1 本で見張りごと落ちて黙って通らない・values_problems が名指す）
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
    """(表の path, 表全体の問題の並び)。表が無ければ (None, [])。名指しの 1 か所: 鍵と型（SV.check）に、guard の値の
    中身（読めない正規表現・読めない跡の形・古い形の跡）を足す。"""
    path = SV.find(starts=_starts(payload))
    table, problems = SV.load(path)
    problems = problems + SV.check(table)
    got = table.get("guard") if isinstance(table, dict) else None
    return path, problems + (_guard_value_problems(got) if isinstance(got, dict) else [])


def _regex_ok(p):
    if not isinstance(p, str) or not p:
        return False
    try:
        re.compile(p)
    except re.error:
        return False
    return True


def _guard_value_problems(got):
    """guard の欄の、型は合うが中身が読めずに黙って効かない値の名指し（型の違いは SV.check が名指す）。"""
    out = []
    for k, v in got.items():
        if k not in DEFAULTS or not isinstance(v, list):
            continue
        if k in REGEX_LIST_KEYS:
            out += ["guard.%s: 正規表現として読めない %s" % (k, json.dumps(p, ensure_ascii=False)[:160])
                    for p in v if not _regex_ok(p)]
        elif k in MATCHER_KEYS:
            out += ["guard.%s: %s" % (k, b) for b in tool_matchers({k: v}, k)[1]]
            olds = [spec for spec in v if isinstance(spec, str) and spec]
            if olds:
                out.append("guard.%s: 古い形の跡（文字列＝「道具の名 + 入力の JSON」の字に当てる・入力にその字を含むだけの呼び出し"
                           "も跡に数える）%s。今は読むが、新しい形 {\"tool\": 名の正規表現, \"input\": {欄: 正規表現}} へ移す"
                           "（2 段目で読まなくなる・CONTRIBUTING.md §8・形は skill `guard:guard-rules`）"
                           % (k, json.dumps(olds, ensure_ascii=False)[:200]))
        elif k in PATTERN_DICT_KEYS:
            out += ["guard.%s: pattern が正規表現として読めない %s" % (k, json.dumps(e, ensure_ascii=False)[:160])
                    for e in v if not _regex_ok(e.get("pattern") if isinstance(e, dict) else None)]
    return out


# ── 跡の形（会話ログの道具の呼び出しを、道具の名と入力の欄で見る）──
# 形（MATCHER_KEYS の値の 1 つ）:
#   {"tool": "<正規表現>"}                                … 道具の名の全体に当てる
#   {"tool": "<正規表現>", "input": {"<欄>": "<正規表現>"}} … 名の全体に当て、挙げた入力の欄（a.b で下の欄）の全部にも当たる時
#   "<正規表現>"（古い形・壊れる 1 段目で読み続ける）       … 「道具の名 + 入力の JSON」の字に search で当てる（入力にその字を
#                                                           含むだけの呼び出しも跡に数える）。起動の時に古い形と名指す
# 読めない形は跡に数えず（数える側に倒さない）、名指す。input を書くなら欄を 1 つ以上の {…}（[]・null・""・{} は読めない形
# ＝黙って名だけの形に広げない）。
def _sig(block):
    try:
        body = json.dumps(block.get("input") or {}, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        body = str(block.get("input") or "")
    return "%s %s" % (block.get("name") or "", body)


def compile_matcher(spec):
    """跡の形 1 つを「道具の呼び出し 1 つ（tool_use の塊）→ 当たるか」の関数に。読めない形は ValueError か re.error。"""
    if isinstance(spec, str):
        if not spec:
            raise ValueError("空の字")
        old = re.compile(spec)
        return lambda block: bool(old.search(_sig(block)))
    if not isinstance(spec, dict) or not set(spec) <= {"tool", "input"}:
        raise ValueError('形が違う（{"tool": …} か {"tool": …, "input": {…}}）')
    tool = spec.get("tool")
    if not isinstance(tool, str) or not tool:
        raise ValueError("tool が無い")
    rx = re.compile(tool)
    if "input" not in spec:
        return lambda block: bool(rx.fullmatch(str(block.get("name") or "")))
    fields = spec["input"]
    if not isinstance(fields, dict) or not fields:
        raise ValueError("input は欄を 1 つ以上の {欄の名: 正規表現}（%s は読まない＝名だけの形に広げない）"
                         % json.dumps(fields, ensure_ascii=False))
    if not all(isinstance(k, str) and k and isinstance(v, str) and v for k, v in fields.items()):
        raise ValueError("input は {欄の名: 正規表現}（欄の名も正規表現も空でない字）")
    frx = {k: re.compile(v) for k, v in fields.items()}

    def hit(block):
        inp = block.get("input") if isinstance(block.get("input"), dict) else {}
        return bool(rx.fullmatch(str(block.get("name") or ""))) and all(_hit(r, _field(inp, k)) for k, r in frx.items())
    return hit


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


def _hit(rx, text):
    return text is not None and bool(rx.search(text))


def matches_tool(block, matchers):
    """道具の呼び出し 1 つが跡の形（compile_matcher の関数）のどれかに当たるか。"""
    return any(m(block) for m in matchers)


# ── Bash の命令で走る物（命令の字に含むだけの echo・grep・# の注を、走らせた事に数えない）──
_SHELL_SEPS = {";", "&", "&&", "||", "|", "|&", "(", ")", ";;", ";&", ";;&"}
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
_WRAP_TAKES = {"sudo": ("-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"), "nice": ("-n",), "exec": ("-a",),
               "timeout": ("-k", "-s", "--signal", "--kill-after"), "env": ("-u", "-C", "-S", "--unset", "--chdir")}


def _strip_comments(cmd):
    """引用の外で語の頭に在る # から行末までを消す（行の終わりは残す）。"""
    out, i, n, q = [], 0, len(cmd), ""
    while i < n:
        c = cmd[i]
        if q == "'":
            q = "" if c == "'" else q
        elif c == "\\" and i + 1 < n:
            out.append(cmd[i:i + 2])
            i += 2
            continue
        elif q == '"':
            q = "" if c == '"' else q
        elif c in "'\"":
            q = c
        elif c == "#" and (i == 0 or cmd[i - 1] in " \t\n;&|()"):
            while i < n and cmd[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _tokens(cmd):
    lx = shlex.shlex(_strip_comments(cmd), posix=True, punctuation_chars=";&|()<>\n")
    lx.whitespace, lx.whitespace_split, lx.commenters = " \t\r", True, ""
    return list(lx)


def _unwrap(argv):
    """前置き（VAR=値・env・command・time・sudo・nohup・exec・nice・timeout・stdbuf）を外した argv。走らない形
    （command -v 等）は []。"""
    i = 0
    while i < len(argv):
        w = argv[i]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w, re.S):
            i += 1
            continue
        base = os.path.basename(w)
        if base in ("command", "builtin") and i + 1 < len(argv) and argv[i + 1] in ("-v", "-V"):
            return []
        if base not in ("env", "command", "builtin", "time", "nohup", "exec", "sudo", "nice", "timeout", "stdbuf"):
            break
        takes = _WRAP_TAKES.get(base, ())
        i += 1
        while i < len(argv) and (argv[i].startswith("-") or (base == "env" and "=" in argv[i])):
            i += 2 if argv[i] in takes else 1
        if base == "timeout" and i < len(argv):
            i += 1               # 時間
    return argv[i:]


def shell_runs(cmd, depth=0):
    """Bash の命令の字で走る命令ごとの argv の並び（前置きを外し、bash -c・eval の中へ降りる）。読めない字は []。
    走らせた事を字で見ず、走る道具（命令の頭）と引数の並びで見るための口。$(…) と `…` の中は数えない（数えない側＝止める側）。"""
    try:
        toks = _tokens(str(cmd or ""))
    except ValueError:
        return []
    runs, cur, skip = [], [], False
    for t in toks + [";"]:
        if skip:
            skip = False
            continue
        if t in _SHELL_SEPS or not t.strip("\n"):
            if cur:
                runs.append(cur)
            cur = []
        elif set(t) <= set("<>&|") and ("<" in t or ">" in t):
            skip = True          # 向け替えと、その先
            if cur and cur[-1].isdigit():
                cur.pop()        # 2>&1 の 2
        else:
            cur.append(t)
    out = []
    for argv in runs:
        argv = _unwrap(argv)
        if not argv:
            continue
        base = os.path.basename(argv[0])
        if depth < 3 and base in _SHELLS:
            flags = [j for j, a in enumerate(argv[1:], 1) if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a)]
            if flags and flags[0] + 1 < len(argv):
                out += shell_runs(argv[flags[0] + 1], depth + 1)
                continue
        if depth < 3 and base == "eval":
            out += shell_runs(" ".join(argv[1:]), depth + 1)
            continue
        out.append(argv)
    return out


def _bash_runs(block):
    if block.get("name") != "Bash" or not isinstance(block.get("input"), dict):
        return []
    return shell_runs(block["input"].get("command"))


def runs_command(block, want):
    """Bash の呼び出し 1 つが、命令 want（shell の 1 行）を走らせたか。want の各命令について、走った命令のどれかの頭の道具
    （名だけで比べる）と引数の並びが頭から同じ時だけ（後ろに引数が足されてもよい）。"""
    wants = shell_runs(want)
    ran = _bash_runs(block) if wants else []
    return bool(ran) and all(any(_same_head(r, w) for r in ran) for w in wants)


def _same_head(ran, want):
    return (len(ran) >= len(want) and os.path.basename(ran[0]) == os.path.basename(want[0])
            and ran[1:len(want)] == want[1:])


def runs_script(block, script, flag):
    """Bash の呼び出し 1 つが、script（例 check.mjs）を flag（例 --run-prior）つきで走らせたか（node <script> … か
    <script> … の形。script は走らせた引数の名で見る）。"""
    for argv in _bash_runs(block):
        rest = argv
        if os.path.basename(argv[0]) in ("node", "nodejs"):
            args = [j for j, a in enumerate(argv[1:], 1) if not a.startswith("-")]
            if not args:
                continue
            rest = argv[args[0]:]
        if os.path.basename(rest[0]) == script and flag in rest[1:]:
            return True
    return False


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


# hook の差し戻しを会話ログに user の行で残す時の頭（Claude Code が書く決まった字）。版によって isMeta が付かない。
HOOK_FEEDBACK = ("Stop hook feedback:",)


def is_hook_feedback(row):
    """hook の差し戻しが user の行で残った物か（isMeta の有る無しに頼らない）。"""
    return (row.get("type") == "user" and "toolUseResult" not in row
            and text_of(row).lstrip().startswith(HOOK_FEEDBACK))


def is_owner_row(row):
    """人がタイプした行か（道具の返り・差し戻し〔isMeta か hook の差し戻しの頭〕を除く）。"""
    return (row.get("type") == "user" and not row.get("isMeta") and "toolUseResult" not in row
            and bool(text_of(row).strip()) and not is_hook_feedback(row))


def new_request(row, current_prompt_id):
    """頼みの境か: 人の行で、頼みの印（promptId）が今の頼みと違う物。同じ印の行は同じ頼みの続き（差し戻し等）。"""
    if not is_owner_row(row):
        return False
    pid = row.get("promptId")
    return not (pid and pid == current_prompt_id)


def first_owner_text(path):
    try:
        for row in iter_rows(path):
            if is_owner_row(row):
                return text_of(row)
    except Exception:
        return ""
    return ""


def is_child_prompt(text):
    return bool(RETURN_TO_WINDOW.search(text or "") or CHILD_OF.search(text or ""))
