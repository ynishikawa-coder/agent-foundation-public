"""PreToolUse — 選択肢の画面（AskUserQuestion）を出す前に、この窓の文脈（縮めた境より後）と助手の中で決定の記録と問いの表を引いた跡があるかを照らす。
跡が無ければ AI の呼び出しだけを止め、引いてから出し直させる。

なぜ在るか: 細目 §4 の「聞く前に決定の記録と問いの表を引く」は文で知らせるだけで、確認ページ（qa-html の prior_check_cmd）の
外では照らす物が無かった。そのため答え済みの事を何度も聞く形がオーナーに届いていた（オーナー同意 2026-11-19: 文で知らせる
だけの所は AI だけ止めて書き直させる形にしてよい・オーナーの操作は止めない）。止まるのは AI の呼び出しだけ（画面はまだ人に
出ていない）。

跡とは: この窓の今の文脈（会話ログの最後の「縮めた境」〔compact_boundary〕より後。境が無ければ頭から）にある道具の
  呼び出しのうち、「道具の名 + 入力の JSON」が値の表 guard.ask_prior_lookup（正規表現の並び）のどれかに当たる物。
  この窓が立てた助手（<会話ログ>/subagents/*.jsonl）の呼び出しも、境より後に書かれた物は数える（助手に引かせてよい）。
  人の頼みの行で番を切らない: 引いた中身は縮めるまで文脈に残る＝前の頼みで引いた跡も、子の窓の知らせが後に届いても数える。
  引く先（決定の記録・問いの表の置き場と道具）は会社ごとに違うので、名は値の表から読む（ここに決め打ちしない）。
読めない会話ログ: 跡が見つからず、会話ログか助手のログに読めない行がある・開けない時は、止める文にその行の番号を出す
  （黙って通さない・黙って「跡が無い」と言わない）。上限（ASK_PRIOR_MAX）は同じに当たる。
値の表に ask_prior_lookup が無い repo: 引いたかを機械で見分けられない＝知らない値。既定で止める側に倒し、窓ごとに 1 回だけ
  止めて「自分の引く先で引いてから出し直す・値の表に引く先を足す」を返す（2 回目からは通す＝引く先を知らない窓が回り続けない）。
上限: 値がある repo でも、同じ頼み（人が打った行の番）の中で止めるのは ASK_PRIOR_MAX 回まで（引く道具が繋がっていない窓が
  回り続けない）。越えたら通し、止まりの文で「引けなかった事を問いの前にチャットで書く」を求めてある。
誤って止めた時: 値の表 ask_prior_exempt（問いの文に当てる正規表現）に当たる問いだけの画面は照らさない（済んだかの確かめ等）。
  値の表は PR とレビューを通る＝窓の一存では外れない。
黙る時: 選択肢の画面の外・助手の中（transcript の path に /subagents/）。
止めた文の最後には入口（guard.py）が、出し直すだけで済ませず原因を細目 §3「まず構造を疑う」で探す行を付ける。
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


def _hit(rows, patterns):
    for row in rows:
        if row.get("type") != "assistant":
            continue
        for b in _tool_uses(row):
            if b.get("name") != ASK_TOOL and G.SV.hit(patterns, G.tool_sig(b)) is not None:
                return True
    return False


def _context_start(log):
    """最後の縮めた境の (バイト位置, 時刻)。境が無ければ (0, None)。"""
    for i in range(len(log.rows) - 1, -1, -1):
        if G.is_compact_boundary(log.rows[i]):
            return log.pos[i], G.parse_ts(log.rows[i].get("timestamp"))
    return 0, None


def helper_logs(tpath):
    """この窓が立てた助手の会話ログの path の並び（<会話ログの名>/subagents/*.jsonl）。"""
    d = os.path.join(os.path.splitext(tpath)[0], "subagents")
    try:
        return sorted(os.path.join(d, n) for n in os.listdir(d) if n.endswith(".jsonl"))
    except OSError:
        return []


def scan(tpath, patterns):
    """(人の頼みの番の印, 跡が在るか, 読めなかった事の文の並び)。"""
    log = G.read_log(tpath)
    start, since = _context_start(log)
    rows, broken = log.after(start)
    i = G.last_human_index(log.rows)
    turn = str(log.rows[i].get("uuid") or "row%d" % i) if i >= 0 else ""
    notes = [G.broken_note(tpath, broken)] if broken else []
    if _hit(rows, patterns):
        return turn, True, []
    for hp in helper_logs(tpath):
        try:
            h = G.read_log(hp)
        except OSError as e:
            notes.append("助手の会話ログ %s を開けなかった（%s）" % (hp, e.__class__.__name__))
            continue
        hrows = h.rows
        if since is not None:      # 縮めた境より前の助手は数えない（時刻の無い行は境の後と見る＝跡を落とさない）
            hrows = [r for r in hrows if (G.parse_ts(r.get("timestamp")) or since) >= since]
        if _hit(hrows, patterns):
            return turn, True, []
        if h.broken:
            notes.append(G.broken_note(hp, h.broken))
    return turn, False, notes


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
    head = ("[guard] 選択肢の画面を出す前に、この窓の文脈と助手の中で決定の記録と問いの表を引いた跡が会話ログに無いので止めた"
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
        turn, found, notes = scan(tpath, patterns)
    except OSError as e:       # 開けない＝跡を確かめられない。黙って通さず、訳を出して止める（上限は同じ）
        turn, found, notes = "", False, ["会話ログ %s を開けなかった（%s）" % (tpath, e.__class__.__name__)]
    if found:
        return ""
    if _bump("deny", sid + "-" + (turn or "head")) > ASK_PRIOR_MAX:
        return ""
    return "\n".join([
        head,
        "跡と数える物: この窓の文脈（最後に縮めた境より後）と、この窓が立てた助手の道具の呼び出しのうち、"
        "値の表 guard.ask_prior_lookup に当たる物（今の値: %s）。" % "・".join(str(r) for _, _, r in patterns[:6]),
    ] + ["読めなかった所（跡がそこに在ったかを確かめられない）: " + n for n in notes] + [
        "直し方: " + HOW,
        "引く道具が繋がっていない等で引けない時: 同じ頼みの中で %d 回止めた後は通す。その時は問いの前にチャットで"
        "「引けなかった（何で）」を書いてから出す。" % ASK_PRIOR_MAX,
        "誤って止めた時（引く要の無い問い。例: 手の作業が済んだかの確かめ）: 値の表の guard.ask_prior_exempt に問いの文に"
        "当てる正規表現を足す（PR とレビューを通す）。引いたのに止まった時は、使った道具に当たる形を guard.ask_prior_lookup "
        "に足す。細目は skill `guard:guard-rules`。",
    ])
