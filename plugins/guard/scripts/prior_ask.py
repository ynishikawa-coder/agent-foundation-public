"""PreToolUse — 選択肢の画面（AskUserQuestion）を出す前に、この頼みの中で決定の記録と問いの表を引いた跡があるかを照らす。
跡が無ければ AI の呼び出しだけを止め、引いてから出し直させる。

なぜ在るか: 細目 §4 の「聞く前に決定の記録と問いの表を引く」は文で知らせるだけで、確認ページ（qa-html の prior_check_cmd）の
外では照らす物が無かった。そのため答え済みの事を何度も聞く形がオーナーに届いていた（オーナー同意 2026-11-19: 文で知らせる
だけの所は AI だけ止めて書き直させる形にしてよい・オーナーの操作は止めない）。止まるのは AI の呼び出しだけ（画面はまだ人に
出ていない）。

跡とは: 会話ログ（transcript_path）の、今の頼みの中の道具の呼び出しのうち、引く先の跡の形に名と入力の欄が当たり、
  かつ走った証が在る物。走ったかは頼んだ字で決めず、同じ tool_use_id の返り（tool_result）で見る: 返りが無い・拒まれた・
  hook に止められた・中断した（is_error で返りの頭が Exit code N でない）呼び出しは跡に数えない（guard_common.result_state）。
  （形は guard_common の「跡の形」。新しい形は入力を JSON の字に直して当てない＝その字を入力に含むだけの呼び出しは跡でない。
  文字列の古い形は壊れる 1 段目として今までどおり字に当て、起動の時に古い形と名指す）。
  頼みの境は guard_common.new_request（人の行で、頼みの印 promptId が今の頼みと違う物。hook の差し戻しの行は境でない）。
引く先（どこから読むか・上から順に最初に在る物）:
  1. 値の表 guard.ask_prior_lookup（会社ごとに違うので、名は値の表から読む＝ここに決め打ちしない）。
  2. 値の表 docs-kit.qa-html.prior_check_cmd（確認ページで前の答えを引く道具＝同じ引く先。引く先を 2 か所に写さない）。
     Bash の命令を guard_common.parse_shell で読み、読み切れない形（ヒアドキュメントの本文は除いた上で、&&・||・$(…)・
     制御の語・| bash 等）が 1 つでも在れば数えない（知らない形を走った側に倒さない）。その上で走った証を返りで見る:
     check.mjs --run-prior は、引き終えた時だけ出す決まった行（PRIOR_MARK「prior-check: <n> 件」）が返りに在る時
     （page が赤で 0 でない数で終わってもよい）。値の表の命令そのものは、誤りなく返り、出力が空でない時。
  3. どちらも無い repo: 引いたかを機械で見分けられないので照らさない（止めない）。代わりに起動の時（SessionStart）に、
     照らせていない事と値を足す道を知らせる（毎窓の最初の画面で止める形は、値を持つまで全部の窓を 1 回ずつ止めていた）。
壊れた値: 跡の形として読めない値は跡に数えず（数える側に倒さない）、止めた文と起動の時の知らせ（values_keys）で名指す。
  値が全部壊れていれば、跡は在りえない＝止める（黙って通さない）。
上限: 同じ頼みの中で止めるのは ASK_PRIOR_MAX 回まで（引く道具が繋がっていない窓が回り続けない）。越えたら
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
HOOKS = {"pre": "check", "start": "resurface"}
ASK_PRIOR_MAX = 2      # 同じ頼みの中で止める回数の上限
RUN_PRIOR = ("check.mjs", "--run-prior")     # qa-html の検査に前の答えを引かせる口（SKILL の「前の答えを照らす口」）
PRIOR_MARK = re.compile(r"(?m)^prior-check: \d+ 件\s*$")   # check.mjs --run-prior が引き終えた時だけ出す行


def prior_check_cmd(payload):
    got = G.table("docs-kit", payload).get("qa-html")
    cmd = got.get("prior_check_cmd") if isinstance(got, dict) else None
    return cmd.strip() if isinstance(cmd, str) else ""


def _proof_lookup(matchers):
    def proof(b, res):
        if not G.matches_tool(b, matchers):
            return False, ""
        st = G.result_state(res)
        return (True, "") if st == "ok" else (False, "%s の呼び出しの返りが%s" % (b.get("name"), _STATE_WHY[st]))
    return proof


_STATE_WHY = {"none": "無い（走った証が無い）", "no": "拒まれた・止められた・中断した物（走っていない）",
              "exit": "0 でない数で終わった（引けていない）"}
_PLAIN = "1 つの素の命令（&&・||・;の後の exit・$(…)・if 等の無い形）で走らせ直す"


def _proof_cmd(cmd):
    def proof(b, res):
        if G.runs_script(b, *RUN_PRIOR):
            st = G.result_state(res)
            if st in ("ok", "exit") and PRIOR_MARK.search(G.result_text(res)):
                return True, ""
            return False, ("check.mjs --run-prior の返りが%s" % _STATE_WHY[st] if st in ("none", "no")
                           else "check.mjs --run-prior の返りに「prior-check: <n> 件」の行が無い（引き終えていない）")
        if G.runs_command(b, cmd):
            st = G.result_state(res)
            if st != "ok":
                return False, "引く命令の返りが" + _STATE_WHY[st]
            if G.result_text(res).strip() in G.EMPTY_OUTPUT:
                return False, "引く命令の出力が空（引いた結果が返りに無い。file へ向け替えず返りに出す）"
            return True, ""
        if G.runs_script(b, *RUN_PRIOR, loose=True) or G.runs_command(b, cmd, loose=True):
            return False, "引く命令を読み切れない形で書いた（%s）＝%s" % ("・".join(G.bash_unknowns(b)), _PLAIN)
        return False, ""
    return proof


def lookups(vals, payload):
    """(走った証を見る関数の並び, 壊れた形の名指し, 引く先の名)。関数は (道具の呼び出し, 同じ tool_use_id の返り) →
    (跡か, 数えなかった理由)。引く先が無ければ ([], [], "")。"""
    if vals.get("ask_prior_lookup"):
        ok, bad = G.tool_matchers(vals, "ask_prior_lookup")
        return ([_proof_lookup(ok)] if ok else []), bad, "guard.ask_prior_lookup"
    cmd = prior_check_cmd(payload)
    if cmd:
        runs, unk = G.parse_shell(cmd)
        bad = [] if runs and not unk else ["prior_check_cmd が読み切れない形（%s）＝check.mjs --run-prior だけを跡に数える"
                                           % "・".join(unk or ["命令が無い"])]
        return [_proof_cmd(cmd)], bad, "docs-kit.qa-html.prior_check_cmd"
    return [], [], ""


def scan(tpath, proofs):
    """(今の頼みの印, 跡が在るか, 数えなかった理由の並び)。今の頼みの中の道具の呼び出しを、同じ tool_use_id の返りに結んで見る。"""
    turn, pid, calls, results = "", None, {}, {}
    for i, row in enumerate(G.iter_rows(tpath)):
        if G.new_request(row, pid):
            turn, pid, calls, results = str(row.get("uuid") or "row%d" % i), row.get("promptId"), {}, {}
            continue
        for b in G.tool_uses(row):
            if b.get("name") != ASK_TOOL and b.get("id"):
                calls[b["id"]] = b
        for r in G.tool_results(row):
            results[r.get("tool_use_id")] = r
    why = []
    for cid, b in calls.items():
        for proof in proofs:
            ok, reason = proof(b, results.get(cid))
            if ok:
                return turn, True, []
            if reason:
                why.append(reason)
    return turn, False, list(dict.fromkeys(why))


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
    pats = [p for p in (vals.get("ask_prior_exempt") or []) if isinstance(p, str) and p]
    texts = [str(q.get("question") or "") for q in qs if isinstance(q, dict)]
    return bool(pats) and bool(texts) and all(any(re.search(p, t) for p in pats) for t in texts)


HOW = ("聞く前に引く（細目 §4）: 問いの候補ごとに、この会社の決定の記録と問いの表（前に聞いた問いと答えの表）を、問いと同じ言葉で"
       "引く。答え済みの問い・資料で決まる事（AI が決めて進める）・道具の都合（原因の台帳の行にする）は問いから外し、残った問いだけを"
       "出し直す。引いた結果（照らした記録の在り処か、引いて無かった事）は問いの前にチャットで 1 行書く。")
VALUE_HOW = ("値の表の guard.ask_prior_lookup に、決定の記録と問いの表を引く道具の呼び出しの跡の形（{\"tool\": 名の正規表現} か "
             '{"tool": 名, "input": {欄: 正規表現}}）を足す PR を出す。細目は skill `guard:guard-rules`。')


def resurface(data, vals):
    """SessionStart: 値の表を持つのに引く先が無い repo では、この見張りが照らせていない事を知らせる（止めない）。
    値の表そのものが無い repo（土台を試す所など・会社の決定の記録を持たない）は知らせない。"""
    path = G.SV.find(starts=G._starts(data))
    if not path or not os.path.isfile(path) or lookups(vals, data)[2]:
        return ""
    return ("[guard] この repo は値の表に聞く前に引く先（guard.ask_prior_lookup か docs-kit.qa-html.prior_check_cmd）が無いので、"
            "選択肢の画面の前に決定の記録と問いの表を引いたかを照らしていない（止めない）。" + HOW + "引く先を足す: " + VALUE_HOW)


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
    matchers, bad, source = lookups(vals, data)
    if not source:
        return ""                  # 引く先を知らない＝照らせない。起動の時に知らせてある
    try:
        turn, found, why = scan(tpath, matchers)
    except Exception:          # noqa: BLE001  会話ログが読めない＝見張りの故障。窓を止めない
        return ""
    if found:
        return ""
    sid = G.safe_id(data.get("session_id") or os.path.basename(tpath)) or "window"
    if _bump("deny", sid + "-" + (turn or "head")) > ASK_PRIOR_MAX:
        return ""
    shown = json.dumps(vals.get("ask_prior_lookup") if source == "guard.ask_prior_lookup" else prior_check_cmd(data),
                       ensure_ascii=False)[:300]
    lines = [
        "[guard] 選択肢の画面を出す前に、この頼みの中で決定の記録と問いの表を引いた跡が会話ログに無いので止めた"
        "（オーナー同意 2026-11-19・人の操作は止めていない・画面はまだ人に出ていない）。",
        "跡と数える物: 今の頼みの中の道具の呼び出しのうち、%s の跡の形に道具の名と入力の欄が当たり、同じ tool_use_id の返りで"
        "走った証が在る物（今の値: %s）。" % (source, shown),
    ]
    if why:
        lines.append("跡に数えなかった呼び出し: " + "／".join(why[:4]) + "。")
    if bad:
        lines.append("値の表の壊れた形（跡に数えていない）: " + "／".join(bad) + "。直す PR を出す。")
    lines += [
        "直し方: " + HOW,
        "引く道具が繋がっていない等で引けない時: 同じ頼みの中で %d 回止めた後は通す。その時は問いの前にチャットで"
        "「引けなかった（何で）」を書いてから出す。" % ASK_PRIOR_MAX,
        "誤って止めた時（引く要の無い問い。例: 手の作業が済んだかの確かめ）: 値の表の guard.ask_prior_exempt に問いの文に"
        "当てる正規表現を足す（PR とレビューを通す）。引いたのに止まった時は、使った道具の跡の形を足す: " + VALUE_HOW,
    ]
    return "\n".join(lines)
