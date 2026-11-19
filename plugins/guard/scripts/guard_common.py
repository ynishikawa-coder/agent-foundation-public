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


def _session_watch():
    """窓の種類の正本 session-watch の session_watch.py（同じ版）。読めなければ None。"""
    path = os.environ.get("AF_SESSION_WATCH") or sibling_plugin_file("session-watch", os.path.join("scripts", "session_watch.py"))
    if not path or not os.path.isfile(path):
        return None
    try:
        sw = load_module("af_session_watch", path)
    except Exception:          # noqa: BLE001
        return None
    return sw if all(hasattr(sw, n) for n in ("kind_of", "own_id", "AI")) else None


def is_child_prompt(text, own=None):
    """最初の頼みの文が自分でない窓を指すか（＝その窓へ返す子の窓）。言い回し（「返し先: 」「返事は … へ」「親窓 … の子」）を
    並べず、窓の種類の正本 session_watch.kind_of（NFKC で寄せた文に自分でない窓の id が在るか・自分の id は環境の
    CLAUDE_CODE_REMOTE_SESSION_ID）を直に呼ぶ（写さない）。own を渡せば自分の id の印の後ろとして使う。
    正本が読めない時は子の窓と見ない（文脈の知らせの文の選び分けだけ＝人のいる窓の文に倒す）。"""
    sw = _session_watch()
    if sw is None:
        return False
    return sw.kind_of(text, own) == sw.AI


# ── 道具の呼び出しを類で読む（道具の名の字の並び・名の末尾の列挙でなく、名を語に割った動詞の類と入力の欄）──
# 動詞の類の正本は irreversible（DESTROY・READ・UNDOABLE と words_of）＝ここでは写さず、その中の「外へ出す」類を名指しする。
SEND_VERBS = frozenset({"send", "post", "reply", "respond", "notify", "tell", "broadcast", "dm"})          # 送る・投稿
MAKE_VERBS = frozenset({"create", "spawn", "start", "launch", "new", "fork", "open", "add", "insert", "append",
                        "write", "upload", "publish", "duplicate", "copy", "import", "generate", "save", "put"})  # 作る・立てる
SET_VERBS = frozenset({"set", "rename", "update", "edit"})                                                 # 付ける・替える
WINDOW_NOUNS = frozenset({"session", "sessions", "agent", "agents", "window", "windows"})                  # 窓（他の AI の窓）
LOCAL_OUT = frozenset({"send", "post", "reply", "publish", "share"})   # mcp でない道具で外へ出す動詞（Write・Edit は手元）
_ACTION_KEYS = ("action", "method", "operation", "op")


def _verb_reader():
    import irreversible as IR   # 動詞の類の正本（irreversible が guard_common を読むので、ここでは呼ぶ時に読む）
    return IR


def tool_words(name, tool_input=None):
    """(名の語, 入力の action・method の語)。MCP の道具は mcp__<server>__ の後ろだけを割る（server の名は語にしない）。"""
    IR = _verb_reader()
    name = str(name or "")
    part = name.split("__", 2)[-1] if name.startswith("mcp__") else name
    ti = tool_input if isinstance(tool_input, dict) else {}
    act = [w for k in _ACTION_KEYS if isinstance(ti.get(k), str) for w in IR.words_of(ti[k])]
    return IR.words_of(part), act


def is_prose(text):
    """文か（人や窓が読む字）。URL・path・id（空白の無い英数字と _ . : - だけ）だけの字でない物。"""
    t = str(text or "").strip()
    return bool(t) and not re.fullmatch(r"(?:https?://|/|~/|\./)\S*|[A-Za-z0-9_.:\-]+", t)


def input_strings(v, where="", out=None, limit=2000):
    """入力の中の字を (欄の場所, 字) で全部。"""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(v, str):
        out.append((where or "入力", v))
    elif isinstance(v, dict):
        for k, x in v.items():
            input_strings(x, "%s.%s" % (where, k) if where else str(k), out, limit)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            input_strings(x, "%s[%d]" % (where, i), out, limit)
    return out


class Call:
    """1 つの道具の呼び出しを類で読んだ物。
    reads   … 読むだけ（名か action の動詞が読む類で、書く・送る・消す類が無い。mcp でない道具は書く類が無ければ読む）
    sends   … 人か他の窓へ文を送る（送る・投稿の動詞があり、入力に文が在る）
    window  … 他の窓を立てる・付ける・送る（名の語が窓の類で、作る・立てる・付ける・送るの動詞）
    out     … 手元の外へ出す（mcp の道具で送る・作る・付ける類の動詞・mcp でない道具で外へ出す動詞）
    texts   … 入力の中の文 [(欄, 字)]
    title   … 窓の題（窓を立てる・付ける呼び出しの入力の title 欄）か None"""

    def __init__(self, name, tool_input):
        IR = _verb_reader()
        self.name = str(name or "")
        self.input = tool_input if isinstance(tool_input, dict) else {}
        words, act = tool_words(self.name, self.input)
        verbs = set(words) | set(act)
        self.mcp = self.name.startswith("mcp__")
        writes = verbs & (IR.UNDOABLE | IR.DESTROY | SEND_VERBS | MAKE_VERBS | SET_VERBS)
        self.reads = (bool(verbs & IR.READ) or not self.mcp) and not writes
        self.texts = [(w, t) for w, t in input_strings(self.input) if is_prose(t)]
        say = bool(verbs & SEND_VERBS)
        self.sends = say and bool(self.texts)
        self.window = bool(set(words) & WINDOW_NOUNS) and bool(verbs & (SEND_VERBS | MAKE_VERBS | SET_VERBS))
        self.out = (bool(verbs & (SEND_VERBS | MAKE_VERBS | SET_VERBS)) if self.mcp else bool(verbs & LOCAL_OUT))
        t = self.input.get("title")
        self.title = t if self.window and isinstance(t, str) and t.strip() else None
        self.spawns = self.window and bool(verbs & MAKE_VERBS)

    @property
    def asks(self):
        """他の窓か人へ頼みの文を渡す呼び出しか（送る・窓を立てる）。"""
        return bool(self.texts) and (self.sends or (self.window and not self.reads))


def read_call(name, tool_input):
    """道具の呼び出しを類で読む（outbound・qa_page・context_size・prior_ask・pr_text が共に呼ぶ 1 つの読み手）。"""
    return Call(name, tool_input)
