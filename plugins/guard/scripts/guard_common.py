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
    値の表 guard.ask_prior_lookup の当てる相手の正本（schema.json の against と同じ形）。"""
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
