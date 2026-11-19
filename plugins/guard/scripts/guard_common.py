"""守りの hook が共に使う小さな口: 値の表・置き場・人のいない窓の見分け・会話ログの読み方。

どの口も壊れた時は既定に倒す（見張りの故障で窓を止めない）。仕事の中身や特定の窓の名前は持たない。

値の表（在る時だけ読む・無ければ既定で動く）:
  repo の根の config/skill-values.json の "guard"。読む順は 環境変数 SKILL_VALUES → $CLAUDE_PROJECT_DIR → hook の cwd。
  鍵と既定の正本は、皆が使う 2 つ（下の COMMON）と、各見張りの file の頭の VALUES（その見張りだけが読む鍵）。
  鍵の意味と変え方は skills/guard-rules/SKILL.md（皆の鍵）と skills/guard-rules/見張り/<見張りの名>.md（各見張りの鍵）。
  ここに鍵の一覧を写さない（見張りを足す PR が全部この一覧へ足して衝突した）。
"""
from __future__ import annotations

import ast
import glob
import json
import os
import re
import tempfile
from datetime import datetime, timezone

VALUES_REL = os.path.join("config", "skill-values.json")
# 皆が使う鍵（人のいない窓の印・置き場）。各見張りの鍵は見張りの頭の VALUES が正本（declared() で読む）。
COMMON = {
    "unattended_env": ["AF_UNATTENDED"],
    "state_dir": os.path.join("~", ".claude", "af-guard"),
}
HERE = os.path.dirname(os.path.abspath(__file__))
HELPERS = ("guard", "guard_common")


def declared(path):
    """見張りの file の頭の宣言 {名: 値}（HOOKS・VALUES）を、import せず字の宣言として読む。宣言の無い名は入らない。
    宣言ごとに読む＝VALUES が壊れても HOOKS は読める（壊れた宣言は入らず、試験が「VALUES が無い」で赤にする）。
    file 自体が読めない（構文の誤り）時は例外を上げる（呼ぶ側がその file だけを外す）。"""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    out = {}
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id in ("HOOKS", "VALUES"):
                    try:
                        out[t.id] = ast.literal_eval(n.value)
                    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                        pass
    return out


def watcher_files(here=None):
    """同じ dir の見張りの file（手伝いの部品 guard・guard_common を除く）を名の順に。"""
    d = here or HERE
    return [p for p in sorted(glob.glob(os.path.join(d, "*.py")))
            if os.path.basename(p)[:-3] not in HELPERS]


def defaults(here=None):
    """値の表の既定 = COMMON ＋ 各見張りの VALUES。読めない宣言は飛ばす（1 つの故障で他の既定を落とさない）。"""
    out = dict(COMMON)
    for p in watcher_files(here):
        try:
            v = declared(p).get("VALUES")
        except Exception:   # noqa: BLE001
            continue
        if isinstance(v, dict):
            for k, x in v.items():
                out.setdefault(k, x)
    return out


DEFAULTS = defaults()

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


def values(payload=None):
    """値の表の "guard" を既定に重ねて返す。読めない・型が違う値は既定のまま。"""
    out = dict(DEFAULTS)
    for k, v in table("guard", payload).items():
        if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])) and not (isinstance(v, bool)):
            out[k] = v
    return out


def table(section, payload=None):
    """値の表の 1 つの節を dict で返す（無い・読めない時は {}）。読む順は values() と同じ。他の plugin の口も使う。"""
    path = os.environ.get("SKILL_VALUES") or ""
    if not path:
        root = project_dir(payload)
        path = os.path.join(root, VALUES_REL) if root else ""
    if not path or not os.path.isfile(path):
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
