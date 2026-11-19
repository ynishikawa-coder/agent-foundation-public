"""守りの hook が共に使う小さな口: 値の表・置き場・人のいない窓の見分け・会話ログの読み方。

どの口も壊れた時は既定に倒す（見張りの故障で窓を止めない）。仕事の中身や特定の窓の名前は持たない。

値の表（在る時だけ読む・無ければ既定で動く）:
  repo の根の config/skill-values.json の "guard"。読む順は 環境変数 SKILL_VALUES → $CLAUDE_PROJECT_DIR → hook の cwd。
    context_limit            … 文脈の量の目安（token・既定 300000）
    context_stop_max         … 目安を越えて引き継がずに締める AI を同じターンで差し戻す回数の上限（既定 2・0 で差し戻さない）
    context_handoff          … 引き継ぎの跡とみなす道具の呼び出し（跡の形の並び。形は下の「跡の形」）
    unattended_env           … 真なら「人のいない窓」（夜の自走など）とみなす環境変数の名の並び（既定 ["AF_UNATTENDED"]）
    state_dir                … 未回答の台帳を置く dir（既定 ~/.claude/af-guard。相対なら repo の根から）
    paid_markers_extra       … 有料の上流の印（鍵名・エンドポイント）の足し
    irreversible_bash_extra  … 戻せない Bash の足し [{"pattern": 正規表現, "why": 理由}]
    irreversible_tools_extra … 戻せない道具の名の足し [{"pattern": 正規表現, "why": 理由}]
    qa_page_exempt           … 問いのページの検査から外す file（path に当てる正規表現の並び・問いのページでない物だけ）
    ask_pick_one_exempt      … 1 つだけ選ばせる問いの見張りから外す問いの文（正規表現の並び・意図や事実を問う問いだけ）
    ask_question_max_chars   … 選択肢の画面の問いの文の字数の上限（既定 60・0 で見ない）
    ask_question_max_sentences … 同じく文の数の上限（既定 1・0 で見ない）
    ask_inner_terms_extra    … AI の中の言葉とみなす字の足し（正規表現の並び）
    ask_term_allow           … 中の言葉と数えない字（見つけた字に当てる正規表現の並び・誤って止まる時だけ）
    ask_topic_stopwords_extra … 話題の語と数えない語の足し
    ask_shape_exempt         … 問いの形の見張りから外す問いの文（正規表現の並び・誤って止まる時だけ）
    ask_rec_notice_kinds     … 推奨の印を付けない問いの形 {名: [正規表現]}（既定は ask_shape.REC_NOTICE_KINDS・知らせるだけ）
    ask_rec_notice_exempt    … 上の知らせから外す問いの文（正規表現の並び）
    ask_prior_lookup         … 決定の記録と問いの表を引いた跡とみなす道具の呼び出し（跡の形の並び・会社ごとに違うので既定は
                               無し＝無い repo は docs-kit.qa-html.prior_check_cmd を走らせた跡で見る・それも無ければ照らさず
                               起動の時に知らせる）
    ask_prior_exempt         … 引いた跡の見張りから外す問いの文（正規表現の並び・引く要の無い問いだけ）
    outbound_secret_allow    … 外へ渡す道具の入力の鍵の照らしで、鍵と数えない字（当たった字に当てる正規表現の並び・作り物の見本だけ）
    number_request_exempt    … 番号だけの頼みの照らしから外す文（正規表現の並び・誤って止まる時だけ）
    pr_cleanup_exempt_repos  … PR 本文の整地の欄を照らさない repo（owner/repo に当てる正規表現の並び・整地を PR 本文の外に置く repo だけ）
    pr_words_exempt_repos    … PR の題・本文の言葉を照らさない repo（同じ形）
    public_repos_extra       … 手元に取り出しが無くても公開とみなす repo（同じ形）

跡の形（MATCHER_KEYS の値の 1 つ）: 会話ログの道具の呼び出しを、道具の名と入力の欄で見る（入力を JSON の字に直して
  正規表現を当てない＝その字を入力に含むだけの呼び出しを跡に数えない）。
    "<正規表現>"                                          … 道具の名の全体に当てる
    {"tool": "<正規表現>", "input": {"<欄>": "<正規表現>"}} … 道具の名の全体に当て、挙げた入力の欄（a.b で下の欄）にも全部当たる時
  読めない形・名に当たらない形（「"」や空白を含む＝入力の JSON に当てる古い形）は跡に数えず、value_faults が名指す。
"""
from __future__ import annotations

import glob
import json
import os
import re
import tempfile
from datetime import datetime, timezone

VALUES_REL = os.path.join("config", "skill-values.json")
DEFAULTS = {
    "context_limit": 300_000,
    "context_stop_max": 2,
    # 後継の窓を立てる・返し先の窓へ送る・引き継ぎの file を書く（道具の名は Claude Code の窓の物。会社の物は持たない）
    "context_handoff": [r"(?:mcp__.+__)?(?:create_session|send_message)", "SendMessage",
                        {"tool": "Write|Edit|MultiEdit", "input": {"file_path": r"(?:引き継ぎ|handoff)[^/\\]*$"}}],
    "unattended_env": ["AF_UNATTENDED"],
    "state_dir": os.path.join("~", ".claude", "af-guard"),
    "paid_markers_extra": [],
    "irreversible_bash_extra": [],
    "irreversible_tools_extra": [],
    "qa_page_exempt": [],
    "ask_pick_one_exempt": [],
    "ask_question_max_chars": 60,
    "ask_question_max_sentences": 1,
    "ask_inner_terms_extra": [],
    "ask_term_allow": [],
    "ask_topic_stopwords_extra": [],
    "ask_shape_exempt": [],
    "ask_rec_notice_kinds": {},
    "ask_rec_notice_exempt": [],
    "ask_prior_lookup": [],
    "ask_prior_exempt": [],
    "outbound_secret_allow": [],
    "number_request_exempt": [],
    "pr_cleanup_exempt_repos": [],
    "pr_words_exempt_repos": [],
    "public_repos_extra": [],
}

# 値の表の鍵のうち、正規表現の並び（壊れた形を value_faults が名指す）と、跡の形の並び
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
    入れた plugin の形: cache/<市場>/guard/<版> と cache/<市場>/<plugin>/<版>。同じ版を先に、無ければ新しい物。"""
    here = guard_root or GUARD_ROOT
    cand = os.path.join(os.path.dirname(here), plugin, rel)
    if os.path.isfile(cand):
        return cand
    ver = os.path.basename(here)
    market = os.path.dirname(os.path.dirname(here))
    same = os.path.join(market, plugin, ver, rel)
    if os.path.isfile(same):
        return same
    import glob
    found = sorted(glob.glob(os.path.join(market, plugin, "*", rel)), key=os.path.getmtime, reverse=True)
    return found[0] if found else ""


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


def values(payload=None):
    """値の表の "guard" を既定に重ねて返す。読めない・型が違う値は既定のまま。"""
    out = dict(DEFAULTS)
    for k, v in table("guard", payload).items():
        if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])) and not (isinstance(v, bool)):
            out[k] = v
    for k in set(REGEX_LIST_KEYS) - set(SELF_NAMED_KEYS):
        out[k] = [p for p in out[k] if _regex_ok(p)]   # 読めない正規表現は渡さない（1 本で見張りごと落ちて黙って通らない・value_faults が名指す）
    return out


def _regex_ok(p):
    if not isinstance(p, str) or not p:
        return False
    try:
        re.compile(p)
    except re.error:
        return False
    return True


def values_path(payload=None):
    """値の表の file の path（無ければ ""）。読む順は 環境変数 SKILL_VALUES → $CLAUDE_PROJECT_DIR → hook の cwd。"""
    path = os.environ.get("SKILL_VALUES") or ""
    if not path:
        root = project_dir(payload)
        path = os.path.join(root, VALUES_REL) if root else ""
    return path if path and os.path.isfile(path) else ""


def value_faults(payload=None):
    """値の表の "guard" の、黙って効かない値の名指し（文の並び）: 型が違う値（既定で動く）・読めない正規表現・読めない跡の形。"""
    out = []
    for k, v in table("guard", payload).items():
        if k not in DEFAULTS:
            continue                       # 知らない鍵は values_keys が名指す
        if not isinstance(v, type(DEFAULTS[k])) or isinstance(v, bool):
            out.append("guard.%s: 型が違うので読まず既定で動いている（今の値: %s）" % (k, json.dumps(v, ensure_ascii=False)[:120]))
        elif k in REGEX_LIST_KEYS:
            for p in v:
                try:
                    if not isinstance(p, str) or not p:
                        raise ValueError("空か文字列でない")
                    re.compile(p)
                except (re.error, ValueError) as e:
                    out.append("guard.%s: 正規表現として読めない %s（%s）" % (k, json.dumps(p, ensure_ascii=False), e))
        elif k in MATCHER_KEYS:
            out += ["guard.%s: %s" % (k, b) for b in tool_matchers({k: v}, k)[1]]
        elif k in PATTERN_DICT_KEYS:
            for e in v:
                pat = e.get("pattern") if isinstance(e, dict) else None
                if not _regex_ok(pat):
                    out.append("guard.%s: pattern が正規表現として読めない %s" % (k, json.dumps(e, ensure_ascii=False)[:160]))
    return out


# ── 跡の形（会話ログの道具の呼び出しを、名と入力の欄で見る）──
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


def table(section, payload=None):
    """値の表の 1 つの節を dict で返す（無い・読めない時は {}）。読む順は values() と同じ。他の plugin の口も使う。"""
    path = values_path(payload)
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
        got = got.get(section) if isinstance(got, dict) else None
    except Exception:
        return {}
    return got if isinstance(got, dict) else {}


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
