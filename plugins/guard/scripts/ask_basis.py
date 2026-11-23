"""ask_shape の PostToolUse の知らせから呼ぶ部品（自分の hook は持たない）— 選択肢の画面（AskUserQuestion）が出た後に、その前のチャットに「判断を頼む理由:」の行が
在ったかを照らし、無ければ AI に知らせる（止めない）。「具体例:」は ask_shape の premise が画面を出す前に照らす（正本は 1 つ・ここでは見ない）。

意図: オーナーに判断を頼む時は、この件で実際に何が起きるか（具体例）と、なぜ AI が決めずに頼むか（理由）を先に見せ、
中の言葉だけの問いをオーナーに届けない（細目 §4「見せてから聞く」）。
課題: 「名指しの検査が切れる」のような中の言葉だけで判断を頼み、オーナーが何を決めるのか・なぜ自分が決めるのかが
分からなかった（オーナーの言葉 2026-11-23・原因の台帳 420a40dc）。
原因: 細目 §4 は「案・前提・材料を先に見せる」とだけ書き、何を見せれば足りるか（具体例と頼む理由）を決めておらず、
画面の前のチャットを照らす物も無かった（ask_shape は画面の中の字だけを照らす）。

照らし方: 会話ログ（transcript_path）で、今出た画面（入力の questions が同じ AskUserQuestion の呼び出し）の前、最後の頼みの
  行（人か親の窓が打った行）か 1 つ前の画面より後に AI が書いた文に、行の頭の「判断を頼む理由:」
  （「：」も可）が在るかを見る。今の画面が会話ログにまだ無ければ、最後の頼みより後の最後の文までを見る。
知らせるだけ: 画面は出た後なので止めない（新しく止める物はオーナーの同意が要る・核 §3）。字の形の推し量りで、
  理由の中身が線（オーナーだけの情報・言葉の解釈・戻せない・お金・社外）に当たるかは読まない（残る穴）。
黙る時: 選択肢の画面の外・済んだかの確かめだけの画面（手の窓の「終わりましたか」等＝ask_shape の済んだかの形）・
  助手の中（transcript の path に /subagents/）・会話ログが読めない（見張りの故障で窓を止めない）。
"""
from __future__ import annotations

import os
import re

import ask_shape
import guard_common as G

ASK_TOOL = "AskUserQuestion"

LABELS = {
    "判断を頼む理由": re.compile(r"(?m)^[\s>*\-・]*\**判断を頼む理由\**\s*[:：]\s*\S"),
}


def _blocks(row):
    msg = row.get("message")
    c = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return [b for b in c if isinstance(b, dict)] if isinstance(c, list) else []


def text_before(tpath, qs):
    """今の画面の前に AI が書いた文（最後の頼みか 1 つ前の画面より後）。"""
    buf, hit = [], None
    for row in G.iter_rows(tpath):
        if G.is_owner_row(row):
            buf, hit = [], None
            continue
        if row.get("type") != "assistant":
            continue
        for b in _blocks(row):
            if b.get("type") == "text":
                buf.append(str(b.get("text") or ""))
            elif b.get("type") == "tool_use" and b.get("name") == ASK_TOOL:
                inp = b.get("input")
                if isinstance(inp, dict) and inp.get("questions") == qs:
                    hit = "\n".join(buf)
                buf = []
    return hit if hit is not None else "\n".join(buf)


def _only_done_checks(qs):
    pats = ask_shape.REC_NOTICE_KINDS["済んだかの確認"]
    texts = [ask_shape._text(q.get("question")) for q in qs if isinstance(q, dict)]
    return bool(texts) and all(any(re.search(p, t) for p in pats) for t in texts)


def missing(text):
    return [name for name, pat in LABELS.items() if not pat.search(text or "")]


def notice(data, vals):
    """欠けた行があれば知らせの文、無ければ ""。"""
    if str(data.get("tool_name") or "") != ASK_TOOL:
        return ""
    ti = data.get("tool_input")
    qs = ti.get("questions") if isinstance(ti, dict) else None
    if not isinstance(qs, list) or not qs or _only_done_checks(qs):
        return ""
    tpath = str(data.get("transcript_path") or "")
    if not tpath or not os.path.isfile(tpath) or "/subagents/" in tpath.replace(os.sep, "/"):
        return ""
    try:
        lack = missing(text_before(tpath, qs))
    except Exception:          # noqa: BLE001  会話ログが読めない＝見張りの故障。窓を止めない
        return ""
    if not lack:
        return ""
    return "\n".join([
        "[guard] 選択肢の画面の前のチャットに %s の行が無かった（知らせるだけ・止めていない。細目 §4「見せてから聞く」）。"
        % "・".join("「%s:」" % n for n in lack),
        "直し方: 答えを待つ間に、チャットで「判断を頼む理由:」の行を足して見せる＝AI が決めずに頼む訳（オーナーだけの情報・言葉の解釈・戻せない・お金・社外のどれか）。"
        "理由が書けない問いだったなら、答えを待たず AI が決めて進め、そう書く。",
    ])
