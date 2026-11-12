"""PostToolUse — 窓の文脈（会話の長さ）の見張り。目安を越えた最初の 1 回だけ知らせる（止めない）。

決まり: 文脈の目安は値の表の context_limit（既定 30 万 token）の 1 本。越えたら
  - 人のいる窓: 区切りの良い所で引き継ぎを書き、後継の窓へ替える（後継は返し先を継ぐ）。
  - 人のいない窓（返し先が別の窓の子の窓・値の表の unattended_env が真）: 今の段を終え、引き継ぎを書いて止まる。

測り方: 会話ログの最新の assistant の入力の総量（input + cache_read + cache_creation）＝今の文脈の大きさ。
  知らせた印は窓ごとに 1 個（一時の箱）＝2 回目からは黙る。
黙る時: 助手の中（transcript の path に /subagents/）・会話ログや usage が読めない・もう知らせた。
"""
from __future__ import annotations

import os

import guard_common as G

TAIL_BYTES = 4_000_000   # 最新の assistant の行は末尾にある＝道具のたびに全部を読まない

MSG_HUMAN = (
    "<context-watchdog>\n"
    "この窓の文脈が目安（{limit:,} token）を越えました（知らせはこの 1 回だけ）。"
    "区切りの良い所で引き継ぎを書き、後継の窓へ替えてください（今の作業を途中で投げ出す必要はありません）。"
    "後継の窓は返し先を継ぎます（オーナーへ返す窓の後継は、オーナーへ返す窓のまま）。\n"
    "</context-watchdog>"
)
MSG_UNATTENDED = (
    "<context-watchdog>\n"
    "この窓の文脈が目安（{limit:,} token）を越えました（知らせはこの 1 回だけ）。"
    "人のいない窓なので、今の段を終えたら引き継ぎを書いて止まってください（次の段へ進まない）。\n"
    "</context-watchdog>"
)


def measure(tpath):
    """最新の assistant の入力の総量＝今の文脈の大きさ。"""
    ctx = 0
    for row in G.iter_rows(tpath, TAIL_BYTES):
        if row.get("type") != "assistant":
            continue
        u = (row.get("message") or {}).get("usage") or {}
        if not isinstance(u, dict):
            continue
        tot = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        if tot:
            ctx = tot
    return ctx


def unattended(tpath, vals):
    return G.unattended_by_env(vals) or G.is_child_prompt(G.first_owner_text(tpath))


def _mark(session_id):
    return os.path.join(G.tmp_dir("ctx"), session_id + ".told")


def check(data, vals):
    """隣に出す文（無ければ ""）。"""
    tpath = str(data.get("transcript_path") or "")
    if not tpath or not os.path.isfile(tpath) or "/subagents/" in tpath.replace(os.sep, "/"):
        return ""
    limit = vals.get("context_limit") or G.DEFAULTS["context_limit"]
    try:
        if measure(tpath) < limit:
            return ""
    except Exception:
        return ""
    sid = G.safe_id(data.get("session_id") or os.path.basename(tpath))
    if not sid or os.path.isfile(_mark(sid)):
        return ""
    try:
        os.makedirs(os.path.dirname(_mark(sid)), exist_ok=True)
        open(_mark(sid), "w").close()
    except OSError:
        return ""     # 印を残せない時は知らせない（毎回鳴るより黙る方を選ぶ）
    msg = MSG_UNATTENDED if unattended(tpath, vals) else MSG_HUMAN
    return msg.format(limit=limit)
