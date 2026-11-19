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
SHELLS = ("bash", "sh", "zsh", "dash", "ksh")
# 後ろの命令をそのまま走らせる前置き → その前置きが値を取る option（値を取らない option は "-" で始まる語として飛ばす）
PREFIXES = {
    "env": ("-u", "--unset", "-C", "--chdir", "-S", "--split-string"),
    "command": (), "builtin": (), "exec": ("-a",), "nohup": (), "time": ("-f", "--format", "-o", "--output"),
    "sudo": ("-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "--close-from", "-D", "--chdir",
             "-r", "--role", "-t", "--type", "-U", "--other-user", "-T", "--command-timeout"),
    "doas": ("-u", "-C"), "nice": ("-n", "--adjustment"), "ionice": ("-c", "--class", "-n", "--classdata", "-t"),
    "stdbuf": ("-i", "-o", "-e", "--input", "--output", "--error"), "chrt": (), "taskset": (),
    "timeout": ("-s", "--signal", "-k", "--kill-after"),
    "xargs": ("-a", "--arg-file", "-d", "--delimiter", "-E", "-e", "-I", "-i", "-L", "-l", "-n", "--max-args", "-P",
              "--max-procs", "-s", "--max-chars"),
}
KEYWORDS = ("!", "{", "}", "then", "do", "else", "elif", "if", "while", "until")
OPERATORS = (";", "&&", "||", "|", "&", "\n", "(", ")", ";;", "|&")
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def _tokens(cmd):
    """shlex で語と区切り（; && || | & 改行 括弧）に分ける。読めない（引用符が閉じない等）時は ValueError。"""
    import shlex
    lex = shlex.shlex(cmd, posix=True, punctuation_chars="();<>|&\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = "#"
    return list(lex)


def _strip_prefix(argv):
    """前の代入（A=1）と前置き（env・command・time・sudo・nice・xargs など）を外した、実際に走る命令の語の並び。"""
    i = 0
    while i < len(argv):
        w = argv[i]
        if ASSIGN.match(w) or w in KEYWORDS:
            i += 1
            continue
        name = os.path.basename(w)
        if name not in PREFIXES:
            break
        takes = PREFIXES[name]
        i += 1
        if name == "timeout":
            while i < len(argv) and argv[i].startswith("-"):
                i += 2 if argv[i] in takes else 1
            i += 1                          # 時間の語
            continue
        while i < len(argv):
            w = argv[i]
            if w == "--":
                i += 1
                break
            if name == "env" and ASSIGN.match(w):
                i += 1
            elif w.startswith("-") and len(w) > 1:
                i += 2 if w in takes else 1
            elif name in ("nice", "ionice", "chrt", "taskset") and re.fullmatch(r"[+-]?\d+|0x[0-9a-f]+", w):
                i += 1
            else:
                break
    return argv[i:]


def shell_commands(cmd, _depth=0):
    """Bash の命令の字を、走る単純な命令の語の並びの並びにする（前置きを外し、bash -c と eval の中も開く）。
    読めない字（引用符が閉じない等）は ValueError（呼ぶ側が止める側に倒す）。"""
    if not isinstance(cmd, str) or _depth > 4:
        return []
    out, cur = [], []
    for t in _tokens(cmd) + [";"]:
        if t and (t[0] in "<>" or (t[0] == "&" and ">" in t)):
            cur.append(t)                   # リダイレクト（次の語が先）は語として残し、下で外す
        elif t in OPERATORS or (t and set(t) <= set("();|&\n")):
            argv = _drop_redirects(cur)
            if argv:
                out += _expand(argv, _depth)
            cur = []
        else:
            cur.append(t)
    return out


def _drop_redirects(words):
    """リダイレクトの印と先（`> f`・`2>&1` の 2 と 1）を外した語の並び。"""
    out, skip = [], False
    for w in words:
        if skip:
            skip = False
        elif w and set(w) <= set("<>&"):
            if out and out[-1].isdigit():
                out.pop()
            skip = True
        else:
            out.append(w)
    return out


def _expand(argv, depth):
    argv = _strip_prefix(argv)
    if not argv:
        return []
    name = os.path.basename(argv[0])
    if name in SHELLS:
        for j, w in enumerate(argv[1:], 1):
            if w == "-c" or (w.startswith("-") and not w.startswith("--") and "c" in w[1:]):
                return shell_commands(argv[j + 1], depth + 1) if j + 1 < len(argv) else []
    if name == "eval":
        return shell_commands(" ".join(argv[1:]), depth + 1)
    return [argv]


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


def is_owner_row(row):
    """人がタイプした行か（道具の返り・差し戻し〔isMeta〕を除く）。"""
    return (row.get("type") == "user" and not row.get("isMeta") and "toolUseResult" not in row
            and bool(text_of(row).strip()))


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
