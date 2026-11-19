"""守りの hook が共に使う小さな口: 値の表・置き場・人のいない窓の見分け・会話ログの読み方。

どの口も壊れた時は既定に倒す（見張りの故障で窓を止めない）。仕事の中身や特定の窓の名前は持たない。

値の表（在る時だけ読む・無ければ既定で動く）: config/skill-values.json の "guard"。探し方・鍵の一覧・型・既定は
  plugin の lib/skill_values.py と lib/schema.json（＝土台の skill-values/ の正本への symlink）が持つ＝ここに写さない。
  知らない鍵・畳んだ鍵・型の違う値は、その鍵だけ既定で動き（守りを止めない）、窓の起動の時に名指しで知らせる（values_check）。
  鍵の意味は skill guard:guard-rules の「値の表」。
"""
from __future__ import annotations

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


def is_child_prompt(text):
    return bool(RETURN_TO_WINDOW.search(text or "") or CHILD_OF.search(text or ""))
