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
class Log:
    """会話ログを頭から全部読んだ物（末尾だけ読まない＝大きな出力の後ろに人の行が埋もれても落とさない）。
    rows: 読めた行（dict）／pos: 各行の頭のバイト位置／broken: 読めなかった行の番号（1 始まり）／
    partial: 改行で終わらず JSON として読めない最後の行（書きかけ）が在るか／size: 読んだバイト数。
    読めない行は黙って捨てない＝使う側は broken を見て、判定に要る所なら止める側に倒し、行の番号を文に出す。"""

    __slots__ = ("path", "rows", "pos", "broken", "partial", "broken_pos", "size")

    def __init__(self, path):
        self.path, self.rows, self.pos, self.broken, self.partial, self.broken_pos = path, [], [], [], False, []
        self.size = 0

    def after(self, offset):
        """offset（バイト位置）から後に書かれた行と、その範囲の読めなかった行の番号。"""
        rows = [r for r, p in zip(self.rows, self.pos) if p >= offset]
        return rows, [n for n, p in self.broken_pos if p >= offset]


def read_log(path):
    """会話ログを読む guard の 1 本の口（今は guard だけが使う。session-watch は自前の読み口を持ち、写しが残る＝持ち主は直す窓）。開けない時は OSError をそのまま上げる
    （読めないを「人の行が無い」と取り違えない）。"""
    log = Log(path)
    with open(path, "rb") as f:
        raw = f.read()
    log.size = len(raw)
    off = 0
    lines = raw.split(b"\n")      # 1 行 1 件の JSON は改行（\n）だけで割る（splitlines() は U+2028 などでも割る）
    for n, chunk in enumerate(lines, 1):
        here, off = off, off + len(chunk) + 1
        text = chunk.decode("utf-8", "replace").strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except ValueError:
            if n == len(lines):            # 改行で終わらない最後の行＝書きかけ（壊れ行と数えない）
                log.partial = True
            else:
                log.broken.append(n)
                log.broken_pos.append((n, here))
            continue
        if not isinstance(row, dict):
            log.broken.append(n)
            log.broken_pos.append((n, here))
            continue
        log.rows.append(row)
        log.pos.append(here)
    return log


def broken_note(path, numbers, limit=8):
    """読めなかった行を人に見せる 1 文（行の番号は頭の limit 個）。"""
    if not numbers:
        return ""
    shown = "・".join(str(n) for n in numbers[:limit]) + (" ほか %d 行" % (len(numbers) - limit) if len(numbers) > limit else "")
    return "会話ログ %s の %d 行が JSON として読めなかった（行の番号: %s）" % (path, len(numbers), shown)


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
# 正本はここ 1 か所（plugin session-watch は seeded_by_record を通してだけこれを読む。人の行の見分け〔is_owner_text〕は
# session-watch に自前の写しが残る＝持ち主は直す窓）。
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


def is_compact_summary(row):
    """会話を縮めた後の続きの行（人の行の形だが、Claude Code が書く要約）。"""
    return bool(isinstance(row, dict) and row.get("isCompactSummary"))


def starts_turn(row):
    """会話の番（ターン）を切る行か。人の行の見分けの正本 is_human_row と同じ（plugin session-watch がこの名で直に読む＝写さない）。"""
    return is_human_row(row)


def is_compact_boundary(row):
    """会話を縮めた境の行（これより前の中身は文脈から外れている）。"""
    return isinstance(row, dict) and row.get("type") == "system" and row.get("subtype") == "compact_boundary"


# 人が Esc で止めた時に Claude Code が書く印の行（人の行の形だが、人が打った頼みではない）。字は Claude Code が決める定まった文
INTERRUPT_MARK = re.compile(r"^\[Request interrupted by user(?: for tool use)?\]$")


def is_interrupt_mark(row):
    """人が止めた時に Claude Code が書く中断の印の行か（新しい頼みではない）。"""
    return isinstance(row, dict) and bool(INTERRUPT_MARK.match(text_of(row).strip()))


def is_human_row(row):
    """人がタイプした頼みの行か（正本はこの 1 つ）。知らせ・別の窓の頼み（seeded_by_record）・縮めた後の要約・中断の印は
    人の行でない。頼みを切る・オーナーが戻ったかを見る所は、どれもこれで見る（形だけの is_owner_row で番を切らない）。"""
    return (is_owner_row(row) and not seeded_by_record(row) and not is_compact_summary(row)
            and not is_interrupt_mark(row))


def last_human_index(rows):
    """最後の人の行の位置（無ければ -1）。人の頼みの番の頭。"""
    for i in range(len(rows) - 1, -1, -1):
        if is_human_row(rows[i]):
            return i
    return -1
