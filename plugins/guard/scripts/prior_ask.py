"""PreToolUse — 選択肢の画面（AskUserQuestion）を出す前に、この頼みの中で決定の記録と問いの表を引いた跡があるかを照らす。
跡が無ければ AI の呼び出しだけを止め、引いてから出し直させる。

なぜ在るか: 細目 §4 の「聞く前に決定の記録と問いの表を引く」は文で知らせるだけで、確認ページ（qa-html の prior_check_cmd）の
外では照らす物が無かった。そのため答え済みの事を何度も聞く形がオーナーに届いていた（オーナー同意 2026-11-19: 文で知らせる
だけの所は AI だけ止めて書き直させる形にしてよい・オーナーの操作は止めない）。止まるのは AI の呼び出しだけ（画面はまだ人に
出ていない）。

跡とは: 会話ログ（transcript_path）の、最後の頼み（人か親の窓が打った行）より後の道具の呼び出しのうち、
  「道具の名 + 入力の JSON」が値の表 guard.ask_prior_lookup（正規表現の並び）のどれかに当たる物。
  引く先（決定の記録・問いの表の置き場と道具）は会社ごとに違うので、名は値の表から読む（ここに決め打ちしない）。

値の表に ask_prior_lookup が無い repo: 引いたかを機械で見分けられない＝知らない値。既定で止める側に倒し、窓ごとに 1 回だけ
  止めて「自分の引く先で引いてから出し直す・値の表に引く先を足す」を返す（2 回目からは通す＝引く先を知らない窓が回り続けない）。
上限: 値がある repo でも、同じ頼みの中で止めるのは ASK_PRIOR_MAX 回まで（引く道具が繋がっていない窓が回り続けない）。越えたら
  通し、止まりの文で「引けなかった事を問いの前にチャットで書く」を求めてある。
誤って止めた時: 値の表 ask_prior_exempt（問いの文に当てる正規表現）に当たる問いだけの画面は照らさない（済んだかの確かめ等）。
  値の表は PR とレビューを通る＝窓の一存では外れない。
止めた文の最後には入口（guard.py）が、出し直すだけで済ませず原因を細目 §3「まず構造を疑う」で探す行を付ける。
黙る時: 選択肢の画面の外・助手の中（transcript の path に /subagents/）・会話ログが読めない（見張りの故障で窓を止めない）。
"""
from __future__ import annotations

import json
import os
import re

import guard_common as G

ASK_TOOL = "AskUserQuestion"
HOOKS = {"pre": "check"}
ASK_PRIOR_MAX = 2      # 同じ頼みの中で止める回数の上限


def _tool_uses(row):
    msg = row.get("message")
    c = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(c, list):
        return []
    return [b for b in c if isinstance(b, dict) and b.get("type") == "tool_use"]


def scan(tpath, patterns):
    """(最後の頼みの印, 跡が在るか)。最後の頼みより後の道具の呼び出しだけを見る。"""
    turn, found = "", False
    for i, row in enumerate(G.iter_rows(tpath)):
        if G.is_owner_row(row):
            turn, found = str(row.get("uuid") or "row%d" % i), False
            continue
        if found or row.get("type") != "assistant":
            continue
        for b in _tool_uses(row):
            if b.get("name") == ASK_TOOL:
                continue
            if G.SV.hit(patterns, G.tool_sig(b)) is not None:
                found = True
                break
    return turn, found


def _bump(kind, key):
    """印の数を 1 つ進めて返す。印を残せなければ大きい数（＝止めずに通す。毎回止めるより通す方を選ぶ）。"""
    path = os.path.join(G.tmp_dir("prior"), G.safe_id(key) + "." + kind)
    try:
        n = int(open(path).read().strip() or 0) if os.path.isfile(path) else 0
    except (OSError, ValueError):
        n = 0
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(str(n + 1))
    except OSError:
        return 1 << 30
    return n + 1


def _all_exempt(qs, vals):
    pats = G.patterns(vals, "ask_prior_exempt")
    texts = [str(q.get("question") or "") for q in qs if isinstance(q, dict)]
    return bool(pats) and bool(texts) and all(G.SV.hit(pats, t) is not None for t in texts)


HOW = ("聞く前に引く（細目 §4）: 問いの候補ごとに、この会社の決定の記録と問いの表（前に聞いた問いと答えの表）を、問いと同じ言葉で"
       "引く。答え済みの問い・資料で決まる事（AI が決めて進める）・道具の都合（原因の台帳の行にする）は問いから外し、残った問いだけを"
       "出し直す。引いた結果（照らした記録の在り処か、引いて無かった事）は問いの前にチャットで 1 行書く。")


def check(data, vals):
    """止めるなら理由、通すなら ""。"""
    if str(data.get("tool_name") or "") != ASK_TOOL:
        return ""
    ti = data.get("tool_input")
    qs = ti.get("questions") if isinstance(ti, dict) else None
    if not isinstance(qs, list) or not qs or _all_exempt(qs, vals):
        return ""
    tpath = str(data.get("transcript_path") or "")
    if not tpath or not os.path.isfile(tpath) or "/subagents/" in tpath.replace(os.sep, "/"):
        return ""
    sid = G.safe_id(data.get("session_id") or os.path.basename(tpath)) or "window"
    patterns = G.patterns(vals, "ask_prior_lookup")
    head = ("[guard] 選択肢の画面を出す前に、この頼みの中で決定の記録と問いの表を引いた跡が会話ログに無いので止めた"
            "（オーナー同意 2026-11-19・人の操作は止めていない・画面はまだ人に出ていない）。")
    if not patterns:
        if _bump("novalue", sid) > 1:
            return ""
        return "\n".join([
            head,
            "この repo の値の表（config/skill-values.json の guard.ask_prior_lookup）に引く先が無いので、引いたかを機械で"
            "見分けられない。この窓では 1 回だけ止める（次からは通す）。",
            "直し方: " + HOW,
            "引く先を足す: 値の表の guard.ask_prior_lookup に、決定の記録と問いの表を引く道具の呼び出しに当たる正規表現"
            "（道具の名 + 入力の JSON に当てる）を足す PR を出す。細目は skill `guard:guard-rules`。",
        ])
    try:
        turn, found = scan(tpath, patterns)
    except Exception:          # noqa: BLE001  会話ログが読めない＝見張りの故障。窓を止めない
        return ""
    if found:
        return ""
    if _bump("deny", sid + "-" + (turn or "head")) > ASK_PRIOR_MAX:
        return ""
    return "\n".join([
        head,
        "跡と数える物: 最後の頼みより後の道具の呼び出しのうち、値の表 guard.ask_prior_lookup に当たる物"
        "（今の値: %s）。" % "・".join(str(r) for _, _, r in patterns[:6]),
        "直し方: " + HOW,
        "引く道具が繋がっていない等で引けない時: 同じ頼みの中で %d 回止めた後は通す。その時は問いの前にチャットで"
        "「引けなかった（何で）」を書いてから出す。" % ASK_PRIOR_MAX,
        "誤って止めた時（引く要の無い問い。例: 手の作業が済んだかの確かめ）: 値の表の guard.ask_prior_exempt に問いの文に"
        "当てる正規表現を足す（PR とレビューを通す）。引いたのに止まった時は、使った道具に当たる形を guard.ask_prior_lookup "
        "に足す。細目は skill `guard:guard-rules`。",
    ])
