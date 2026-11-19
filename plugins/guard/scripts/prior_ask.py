"""PreToolUse — 選択肢の画面（AskUserQuestion）を出す前に、この頼みの中で決定の記録と問いの表を引いた跡があるかを照らす。
跡が無ければ AI の呼び出しだけを止め、引いてから出し直させる。

なぜ在るか: 細目 §4 の「聞く前に決定の記録と問いの表を引く」は文で知らせるだけで、確認ページ（qa-html の prior_check_cmd）の
外では照らす物が無かった。そのため答え済みの事を何度も聞く形がオーナーに届いていた（オーナー同意 2026-11-19: 文で知らせる
だけの所は AI だけ止めて書き直させる形にしてよい・オーナーの操作は止めない）。止まるのは AI の呼び出しだけ（画面はまだ人に
出ていない）。

跡とは: 会話ログ（transcript_path）の、今の頼みの中の道具の呼び出しのうち、引く先の跡の形に名と入力の欄が当たり、
  かつ走った証が在る物。走ったかは頼んだ字で決めず、同じ tool_use_id の返り（tool_result）の在る印で見る
  （guard_common.tool_use_ran）: 返りが無い・拒まれた・hook に止められた・中断した・Bash で is_error の欄が無い・
  背景に回した呼び出しは数えない。
  （形は guard_common の trace_matchers。新しい形は入力を JSON の字に直して当てない＝その字を入力に含むだけの呼び出しは
  跡でない。文字列の古い形は壊れる 1 段目として今までどおり字に当て、起動の時に古い形と名指す）。
  頼みの境は guard_common.new_request（人の行で、頼みの印 promptId が今の頼みと違う物。hook の差し戻しの行は境でない）。
Bash の呼び出しは、引く命令 1 つだけの時に限る（single_command）: 前に `cd <字>` を 1 つ置くのは可。管・;・&・&&・||・
  出力の向け替え・run_in_background・bash -c と eval の中・読み切れない形（guard_common.parse_shell の unknowns）が在れば
  数えない＝返りが「呼び出し全体」の物で、引く命令 1 つの物と言えないから。shell の読みは parse_shell（1 本の読み口・
  PR #77 と同じ中身）に任せ、数えるかの厳しさはここが持つ。
引く先（どこから読むか・上から順に最初に在る物）:
  1. 値の表 guard.ask_prior_lookup（会社ごとに違うので、名は値の表から読む＝ここに決め打ちしない）。Bash の跡は上の 1 つの
     命令の形で、0 で終えた時だけ。Bash の外の道具は誤りでない返りの時。
  2. 値の表 docs-kit.qa-html.prior_check_cmd（確認ページで前の答えを引く道具＝同じ引く先。引く先を 2 か所に写さない）。
     check.mjs --run-prior は、返りの最後の空でない行が引き終えた時だけ出す決まった行（PRIOR_MARK「prior-check: <n> 件」）の
     時（page が赤で 0 でない数で終わってもよい）。値の表の命令そのものは、引数まで同じ命令が 0 で終え、出力が空でない時。
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
PRIOR_MARK = re.compile(r"prior-check: \d+ 件")   # check.mjs --run-prior が引き終えた時だけ出す最後の行（最後の空でない行の全体に当てる）
EMPTY_OUTPUT = {"", "(No content)", "(Bash completed with no output)", "(no output)"}
STDIN_REDIRS = ("<", "<<", "<<-", "<<<")     # 入力の向け替え（返りの字を変えない）
CD_SEPS = ("&&", ";", "\n")                  # 前の cd <字> と命令の間に置ける区切り
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")   # 命令の前に置ける物は VAR=値 だけ（env・sudo・command 等の前置きは数えない）


def prior_check_cmd(payload):
    got = G.table("docs-kit", payload).get("qa-html")
    cmd = got.get("prior_check_cmd") if isinstance(got, dict) else None
    return cmd.strip() if isinstance(cmd, str) else ""


def _seg_words(toks):
    """_lex の語と区切りの並びを、区切り（; && || | & 改行 等）ごとの (語の並び, その後の区切り) に分ける。入力の向け替え
    （< <<< と、ヒアドキュメントの <<・<<-）の先の語は命令の語に入れない。出力の向け替え・括弧は区切りとして残す（数えない）。"""
    segs, words, k = [], [], 0
    while k < len(toks):
        kind, val = toks[k]
        if kind == "w":
            words.append(val)
        elif val in STDIN_REDIRS:
            k += 1                                  # 先の語（file・区切りの語）
        else:
            segs.append((words, val))
            words = []
        k += 1
    segs.append((words, ""))
    return segs


def single_command(block):
    """Bash の呼び出し 1 つが、素の命令 1 つだけ（前に `cd <字>` を && か ; か改行で 1 つ置くのは可・命令の前は VAR=値 だけ）か。
    (argv, 数えない理由)。argv は guard_common.parse_shell の読み（1 本の読み口）で、上の段の語の並びと同じ物に限る
    （bash -c・eval の中へ降りた読みは数えない）。管・;・&・&&・||・出力の向け替え・背景（run_in_background）・
    読み切れない形が在れば (None, 理由)＝返りの字に他の命令の出力が混ざる・命令が終わっていない形を数えない。"""
    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
    if block.get("name") != "Bash" or not isinstance(inp.get("command"), str):
        return None, ""
    if G.truthy(inp.get("run_in_background")):
        return None, "背景に回した（run_in_background）"
    cmd = inp["command"].strip()
    cmds, unknowns = G.parse_shell(cmd)
    if unknowns:
        return None, "読み切れない形（%s）" % "・".join(unknowns[:3])
    segs = [(w, op) for w, op in _seg_words(G._lex(cmd, [])) if w or op not in ("\n", "")]
    if len(segs) == 2 and segs[0][1] in CD_SEPS and [str(x) for x in segs[0][0][:1]] == ["cd"] \
            and len(segs[0][0]) == 2 and not segs[0][0][1].dyn:
        segs = segs[1:]
        cmds = cmds[1:] if cmds and cmds[0][:1] == ["cd"] else cmds
    if len(segs) != 1 or segs[0][1] not in ("", "\n"):
        ops = [op for _, op in segs if op not in ("", "\n")] or ["改行"]
        return None, "命令 1 つだけの形でない（区切り・出力の向け替え: %s）" % " ".join(dict.fromkeys(ops))
    top = segs[0][0]
    if len(cmds) != 1 or not cmds[0] or [str(x) for x in top[-len(cmds[0]):]] != cmds[0]:
        return None, "bash -c・eval の中の命令（上の段の命令 1 つでない）"
    pre = top[:len(top) - len(cmds[0])]
    if any(x.dyn or not ASSIGN.match(x) for x in pre):
        return None, "前置き（%s）を付けた（command -v 等で走らない形を数えない）" % " ".join(str(x) for x in pre)[:60]
    return cmds[0], ""


def _last_line(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _proof_lookup(matchers):
    def proof(b, rows):
        if not any(m(b) for m in matchers):
            return False, ""
        if b.get("name") == "Bash":
            argv, why = single_command(b)
            if argv is None:
                return False, "引く Bash の呼び出しを数えない: %s＝%s" % (why, _PLAIN)
        ran, _, why = G.tool_use_ran(rows, b.get("id"))
        if not ran or why:
            return False, "%s の呼び出しの返り: %s" % (b.get("name"), why or "走った証が無い")
        return True, ""
    return proof


_PLAIN = "引く命令 1 つだけを、管・;・&・&&・||・出力の向け替え・背景・$(…)・bash -c 無しで走らせ直す（前の cd <字> は可）"


def _is_run_prior(argv):
    rest = argv
    if os.path.basename(argv[0]) in ("node", "nodejs"):
        args = [j for j, a in enumerate(argv[1:], 1) if not a.startswith("-")]
        if not args:
            return False
        rest = argv[args[0]:]
    return os.path.basename(rest[0]) == RUN_PRIOR[0] and RUN_PRIOR[1] in rest[1:]


def _proof_cmd(cmd):
    want = G.parse_shell(cmd)[0]

    def proof(b, rows):
        if b.get("name") != "Bash":
            return False, ""
        text = str((b.get("input") or {}).get("command") or "") if isinstance(b.get("input"), dict) else ""
        argv, why = single_command(b)
        if argv is None:
            near = RUN_PRIOR[0] in text or any(w and w[0] in text for w in want)
            return False, ("引く命令の呼び出しを数えない: %s＝%s" % (why, _PLAIN)) if near and why else ""
        if _is_run_prior(argv):
            ran, out, why = G.tool_use_ran(rows, b.get("id"))
            if not ran:
                return False, "check.mjs --run-prior の返り: " + why
            if not PRIOR_MARK.fullmatch(_last_line(out)):
                return False, "check.mjs --run-prior の返りの最後の行が「prior-check: <n> 件」でない（引き終えていない）"
            return True, ""
        if len(want) == 1 and argv == want[0]:
            ran, out, why = G.tool_use_ran(rows, b.get("id"))
            if not ran or why:
                return False, "引く命令の返り: " + (why or "走った証が無い")
            if out.strip() in EMPTY_OUTPUT:
                return False, "引く命令の出力が空（引いた結果が返りに無い。file へ向け替えず返りに出す）"
            return True, ""
        if want and argv[:1] == want[0][:1] and argv[:len(want[0])] == want[0]:
            return False, "引く命令の引数が値の表の命令と違う（%s）＝値の表の命令そのものを走らせる" % " ".join(argv)[:80]
        return False, ""
    return proof


def lookups(vals, payload):
    """(走った証を見る関数の並び, 壊れた形の名指し, 引く先の名)。関数は (道具の呼び出し, 今の頼みの会話ログの行) →
    (跡か, 数えなかった理由)。引く先が無ければ ([], [], "")。"""
    if vals.get("ask_prior_lookup"):
        ok, bad = G.trace_matchers(vals, "ask_prior_lookup")
        return ([_proof_lookup(ok)] if ok else []), bad, "guard.ask_prior_lookup"
    cmd = prior_check_cmd(payload)
    if cmd:
        runs, unk = G.parse_shell(cmd)
        bad = [] if len(runs) == 1 and not unk else [
            "prior_check_cmd が素の命令 1 つでない（%s）＝check.mjs --run-prior だけを跡に数える"
            % "・".join(unk or (["命令が無い"] if not runs else ["命令が %d 個" % len(runs)]))]
        return [_proof_cmd(cmd)], bad, "docs-kit.qa-html.prior_check_cmd"
    return [], [], ""


def scan(tpath, proofs):
    """(今の頼みの印, 跡が在るか, 数えなかった理由の並び)。今の頼みの中の道具の呼び出しを、同じ tool_use_id の返りに結んで見る
    （guard_common.tool_use_ran）。"""
    turn, pid, rows = "", None, []
    for i, row in enumerate(G.iter_rows(tpath)):
        if G.new_request(row, pid):
            turn, pid, rows = str(row.get("uuid") or "row%d" % i), row.get("promptId"), []
            continue
        rows.append(row)
    why = []
    for row in rows:
        for b in G.tool_uses(row):
            if b.get("name") == ASK_TOOL or not b.get("id"):
                continue
            for proof in proofs:
                ok, reason = proof(b, rows)
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
