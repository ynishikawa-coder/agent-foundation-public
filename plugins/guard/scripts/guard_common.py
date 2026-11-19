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
# 文の返し先は手で書いた写しなので、最初の頼みの行の記録（人が打った頼みでない＝seeded_by_record）と合う時だけ数える。
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


def _clone_git(clone, *args):
    import subprocess
    try:
        r = subprocess.run(["git", "-C", clone, *args], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def foundation_file(rel, guard_root=None):
    """土台の repo の根からの file（plugin の外・例 public-guard/guard.py）の、入った guard と同じ版の path か ""。
    repo の形: plugins/guard の 2 つ上が repo の根。
    入れた plugin の形: <plugins>/cache/<市場>/guard/<版> → <plugins>/marketplaces/<市場>/（市場の取り出し＝repo 全体）。
    市場の取り出しの今の checkout は入った guard と同じ版の時だけ読む（clone が先へ進んだ・古い clone が残った時に
    違う版の決まりで照らさない）。版が違えば、その版の中身を clone の歴史から取り出して読む（取り出せなければ ""
    ＝呼ぶ側が止めて名指しする）。版は cache の dir の名（commit の頭）。"""
    here = guard_root or GUARD_ROOT
    cand = os.path.join(os.path.dirname(os.path.dirname(here)), rel)
    if os.path.isfile(cand):
        return cand
    market = os.path.dirname(os.path.dirname(here))
    cache = os.path.dirname(market)
    clone = os.path.join(os.path.dirname(cache), "marketplaces", os.path.basename(market))
    ver = os.path.basename(here)
    if not os.path.isdir(clone) or not re.fullmatch(r"[0-9A-Za-z._-]{1,64}", ver or ""):
        return ""
    head = (_clone_git(clone, "rev-parse", "HEAD") or b"").decode().strip()
    at = (_clone_git(clone, "rev-parse", "--verify", "-q", f"{ver}^{{commit}}") or b"").decode().strip()
    if not head or not at:
        return ""  # 入った版が clone の歴史に無い・clone が git でない＝同じ版か分からない
    cand = os.path.join(clone, rel)
    if at == head:
        return cand if os.path.isfile(cand) else ""
    body = _clone_git(clone, "show", f"{at}:{rel.replace(os.sep, '/')}")
    if body is None:
        return ""
    out = os.path.join(tempfile.gettempdir(), "af-foundation-at", ver, rel)
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tmp = f"{out}.{os.getpid()}"
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, out)
    except OSError:
        return ""
    return out


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


# ── 会話ログ・hook の入力・窓の環境の値の読み方（正本はここ 1 か所。見張りは前提を自分で決めず、ここを呼ぶ）──
# どの読み方も、確かめた物（公式の文書か、Claude Code の本体の実物・実物の会話ログ）を BASIS に名指す。
# 確かめていない値（例: 会話ログの promptSource・窓の環境の CLAUDE_CODE_CHILD_SESSION）は読まない。
BASIS = {
    "人が打った行": "Claude Code 本体の判定（v2.1.328 の本体の人の行の判定）: type が user・isMeta でない・toolUseResult が無い・"
                  "isCompactSummary でない・origin が無いか origin.kind が human",
    "別の窓・仕組みから来た行": "実物の会話ログ（create_session で立った窓の最初の行）: origin.kind が task-notification。"
                          "本体の origin.kind は human のほか task-notification・peer・channel・remote・plugin・"
                          "auto-continuation 等（human 以外は人が打った頼みでない）",
    "助手の中の hook": "hooks の文書（code.claude.com/docs/en/hooks の Common input fields）: 助手の中で回る hook の入力に "
                    "agent_id が付く。SubagentStop の transcript_path は本体の会話ログ（助手の物は agent_transcript_path）",
    "クラウドの窓": "env-vars の文書: CLAUDE_CODE_REMOTE はクラウドの窓で自動で true",
    "窓の id": "cloud-environments の文書（Link output back to the session）: CLAUDE_CODE_REMOTE_SESSION_ID の cse_ を "
             "session_ に替えると窓の URL の id",
    "Stop の入力": "hooks の文書（Stop input）: stop_hook_active は stop の hook の差し戻しで続いている時 true・"
                 "last_assistant_message は今の返事の本文（会話ログは遅れて書かれる）",
    "文脈の大きさ": "Messages API の usage: 1 回の呼び出しの入力は input_tokens・cache_read_input_tokens・"
               "cache_creation_input_tokens の和（実物の会話ログの最新の行で約 20 万＝窓の文脈と合う）。助手の行は本体の"
               "会話ログに入らず subagents/ の別の file（hooks の文書の agent_transcript_path）。本体の行は isSidechain が偽",
    "repo の根": "hooks の文書: CLAUDE_PROJECT_DIR は hook の処理に渡る（窓を始めた repo の根）。Bash の道具の中には無い"
               "（実物の窓の環境で確かめた）＝Bash から呼ぶ道具は今の dir から探す",
}

# 人が打った頼みの記録（会話ログの行の origin.kind）。Claude Code 本体が人の行と見るのは human だけ（BASIS）。
# 正本はここ 1 か所（plugin session-watch も隣の正本としてこれを直に読む＝写さない）。
HUMAN_ORIGINS = ("human",)
# 窓の環境の CLAUDE_CODE_CHILD_SESSION は読まない: 公式の文書（code.claude.com/docs/en/env-vars）では「Claude Code が Bash・
# hook・status line で起動する子プロセスに付く 1」で、どの窓でも hook の中では 1＝別の窓が立てた窓の見分けにならない。
# 頼みの行がまだ無い時の見分けは、サーバの記録（get_session の parent_session_id）を AI に読ませる（session-watch の知らせ）。


def _origin_kind(row):
    origin = row.get("origin")
    if isinstance(origin, dict) and isinstance(origin.get("kind"), str) and origin["kind"]:
        return origin["kind"]
    return None


def is_prompt_row(row):
    """ターンを始める頼みの行か（人が打った行も、別の窓・知らせから来た行も）。道具の返り・isMeta の行
    （見張りの差し戻し・自動の続き・plugin の差し込み）・会話の要約は除く（BASIS「人が打った行」の origin 以外の条件）。"""
    return (isinstance(row, dict) and row.get("type") == "user" and not row.get("isMeta")
            and "toolUseResult" not in row and not row.get("isCompactSummary") and bool(text_of(row).strip()))


def is_owner_row(row):
    """人がタイプした行か（BASIS「人が打った行」）。知らせ・別の窓からの送り（origin.kind が human でない）は数えない。"""
    if not is_prompt_row(row):
        return False
    kind = _origin_kind(row)
    return kind is None or kind in HUMAN_ORIGINS


def seeded_by_record(row):
    """頼みの行が、人が打った物でなく別の窓・仕組みから来た事を、記録が示すか（子の窓の見分けの記録の正本）。
    記録: 頼みの行の origin.kind が human でない（BASIS「別の窓・仕組みから来た行」）。
    行が無い・記録が無い・読めない時は False（文だけで子の窓と決めない＝人の窓の側へ倒す・本体も origin 無しを人と見る）。"""
    if not isinstance(row, dict):
        return False
    kind = _origin_kind(row)
    return kind is not None and kind not in HUMAN_ORIGINS


def in_subagent(payload):
    """hook が窓の中の助手（subagent）の中で回っているか（BASIS「助手の中の hook」）。"""
    return isinstance(payload, dict) and bool(payload.get("agent_id"))


def is_cloud(env=None):
    """クラウドの窓か（BASIS「クラウドの窓」）。"""
    env = os.environ if env is None else env
    return str(env.get("CLAUDE_CODE_REMOTE") or "").strip().lower() == "true"


def main_assistant_row(row):
    """本体（助手でない）の assistant 行か（BASIS「文脈の大きさ」）。文脈の大きさはこの行の usage だけから読む。"""
    return isinstance(row, dict) and row.get("type") == "assistant" and not row.get("isSidechain")


def first_prompt_row(path):
    """会話ログの最初の頼みの行（人の行か、別の窓・知らせから来た行か）。子の窓の見分けはこの行の文と記録を読む。"""
    try:
        for row in iter_rows(path):
            if is_prompt_row(row):
                return row
    except Exception:
        return None
    return None


def is_child_prompt(text, seeded=False):
    """子の窓か。頼みの文の返し先（写し）が別の窓を指し、かつ頼みの行の記録が人の打った物でない時だけ。
    オーナーが引き継ぎの文を貼った窓（記録は人）は、文に親窓や返し先が在っても子の窓にしない。"""
    if not seeded:
        return False
    return bool(RETURN_TO_WINDOW.search(text or "") or CHILD_OF.search(text or ""))


def is_child_log(path):
    """会話ログの最初の頼みの行で子の窓かを決める（文と記録の両方を読む）。"""
    row = first_prompt_row(path)
    return bool(row) and is_child_prompt(text_of(row), seeded_by_record(row))
