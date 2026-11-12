"""守りの hook が共に使う小さな口: 値の表・置き場・人のいない窓の見分け・会話ログの読み方。

どの口も壊れた時は既定に倒す（見張りの故障で窓を止めない）。仕事の中身や特定の窓の名前は持たない。

値の表（在る時だけ読む・無ければ既定で動く）:
  repo の根の config/skill-values.json の "guard"。読む順は 環境変数 SKILL_VALUES → $CLAUDE_PROJECT_DIR → hook の cwd。
    context_limit            … 文脈の量の目安（token・既定 300000）
    unattended_env           … 真なら「人のいない窓」とみなす環境変数の名の並び（既定 ["AF_UNATTENDED"]）
    state_dir                … 未回答の台帳を置く dir（既定 ~/.claude/af-guard。相対なら repo の根から）
    paid_markers_extra       … 有料の上流の印（鍵名・エンドポイント）の足し
    irreversible_bash_extra  … 戻せない Bash の足し [{"pattern": 正規表現, "why": 理由}]
    irreversible_tools_extra … 戻せない道具の名の足し [{"pattern": 正規表現, "why": 理由}]
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone

VALUES_REL = os.path.join("config", "skill-values.json")
DEFAULTS = {
    "context_limit": 300_000,
    "unattended_env": ["AF_UNATTENDED"],
    "state_dir": os.path.join("~", ".claude", "af-guard"),
    "paid_markers_extra": [],
    "irreversible_bash_extra": [],
    "irreversible_tools_extra": [],
}

# 窓の種類の決まり（session-watch の title-mark と同じ線）: 最初の頼みの文の返し先が別の窓なら人のいない窓。
RETURN_TO_WINDOW = re.compile(r"返し先\s*[=＝:：]\s*session_[A-Za-z0-9]+")
CHILD_OF = re.compile(r"（親窓\s*session_[A-Za-z0-9]+\s*の子）")


def project_dir(payload=None):
    d = os.environ.get("CLAUDE_PROJECT_DIR") or ""
    if not d and isinstance(payload, dict) and isinstance(payload.get("cwd"), str):
        d = payload["cwd"]
    return d


def values(payload=None):
    """値の表の "guard" を既定に重ねて返す。読めない・型が違う値は既定のまま。"""
    out = dict(DEFAULTS)
    path = os.environ.get("SKILL_VALUES") or ""
    if not path:
        root = project_dir(payload)
        path = os.path.join(root, VALUES_REL) if root else ""
    if not path or not os.path.isfile(path):
        return out
    try:
        with open(path, encoding="utf-8") as f:
            table = json.load(f)
        got = table.get("guard") if isinstance(table, dict) else None
    except Exception:
        return out
    if not isinstance(got, dict):
        return out
    for k, v in got.items():
        if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])) and not (isinstance(v, bool)):
            out[k] = v
    return out


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
