"""窓の文脈（会話の長さ）の見張り。PostToolUse で目安を越えた最初の 1 回だけ知らせ、Stop で引き継ぐまで AI の締めを差し戻す。

決まり: 文脈の目安は値の表の context_limit（既定 30 万 token）の 1 本。越えたら
  - 人のいる窓: 区切りの良い所で引き継ぎを書き、後継の窓へ替える（後継は返し先を継ぐ）。
  - 返し先が別の窓の子の窓・人のいない窓（値の表の unattended_env が真）: 今の段を終え、引き継ぎを書いて止まる。

測り方: 会話ログの最新の assistant の入力の総量（input + cache_read + cache_creation）＝今の文脈の大きさ。
  知らせた印は窓ごとに 1 個（一時の箱）＝2 回目からは黙る。
黙る時: 助手の中（transcript の path に /subagents/）・会話ログや usage が読めない・もう知らせた。

止めた文の最後には入口（guard.py）が、出し直すだけで済ませず原因を細目 §3「まず構造を疑う」で探す行を付ける。
Stop（締めの差し戻し・オーナー同意 2026-11-19: 文で知らせるだけの所は AI だけ止めて書き直させる形にしてよい）:
  目安を越えた後、越えた行より後に引き継ぎの跡が無いまま AI が締めようとしたら、
  decision=block で AI だけを差し戻し、引き継がせる。人の入力・操作は止めない（返事が届くのが引き継ぎの後になるだけ）。
  上限: 同じターンで context_stop_max 回（既定 2）まで。越えたら通して届ける（窓が回り続けない）。0 で差し戻さない。
  引き継ぎの跡が一度あれば、その窓では二度と差し戻さない。今の文脈が目安の手前（まとめ直して縮んだ後）も差し戻さない。
引き継ぎの跡＝道具が実際に渡した物で数える（入力の JSON の字は探さない＝echo で道具の名を書いた Bash は数えない）:
  ① 他の窓へ文を渡した（guard_common の読み手が、窓を立てる・窓へ送る・人へ送ると読んだ呼び出しで、入力に文が在る）
  ② 引き継ぎの 4 欄（HANDOFF_PARTS）を見出しに持つ文を file に書いた（file の名は問わない＝申し送り.md も数える）
  ③ 値の表 context_handoff の正規表現が「道具の名 + 入力の JSON」に当たる、Bash でない道具の呼び出し（足しの口）
  Bash の命令の字（echo・printf の中身を含む）は跡に数えない（Bash で送った・書いた物は見えない＝射程の天井）。
"""
from __future__ import annotations

import json
import os
import re

import guard_common as G

TAIL_BYTES = 4_000_000   # 最新の assistant の行は末尾にある＝道具のたびに全部を読まない

MSG_HUMAN = (
    "<context-watchdog>\n"
    "この窓の文脈が目安（{limit:,} token）を越えました（知らせはこの 1 回だけ）。"
    "区切りの良い所で引き継ぎを書き、後継の窓へ替えてください（今の作業を途中で投げ出す必要はありません）。"
    "引き継ぐまで、返事を締めるたびに差し戻されます。"
    "後継の窓は返し先を継ぎます（オーナーへ返す窓の後継は、オーナーへ返す窓のまま）。\n"
    "</context-watchdog>"
)
MSG_UNATTENDED = (
    "<context-watchdog>\n"
    "この窓の文脈が目安（{limit:,} token）を越えました（知らせはこの 1 回だけ）。"
    "別の窓へ返す窓か人のいない窓なので、今の段を終えたら引き継ぎを書いて止まってください（次の段へ進まない）。"
    "引き継ぐまで、返事を締めるたびに差し戻されます。\n"
    "</context-watchdog>"
)



# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"post": "check", "stop": "stop"}

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


def unattended(tpath, vals, payload=None):
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
    msg = MSG_UNATTENDED if unattended(tpath, vals, data) else MSG_HUMAN
    return msg.format(limit=limit)


# ── Stop: 目安を越えた後も引き継がずに締める AI を差し戻す ──
# 引き継ぎの 4 欄（差し戻しの文の「直し方」と、file に書いた引き継ぎを読む見出しの正本＝1 か所）
HANDOFF_PARTS = ("済んだ事", "残り", "次の一手", "返し先")
_HEAD_DECOR = r"[#*>\-・|　 ]*(?:[①-⑳]|\d+[.)．）])?[ 　*【「\[]*"


def handoff_heads(text):
    """文の見出し（行の頭の飾りの後に欄の名・その後ろが : か行の終わり）に在る引き継ぎの欄の集合。"""
    found = set()
    for part in HANDOFF_PARTS:
        if re.search(r"(?m)^" + _HEAD_DECOR + re.escape(part) + r"[ 　*】」\]]*(?:[:：]|$)", str(text or "")):
            found.add(part)
    return found


def is_handoff(block, patterns):
    """1 つの道具の呼び出しが引き継ぎか。道具が実際に渡した物（類と入力の欄）で読み、Bash の命令の字は見ない。"""
    name = str(block.get("name") or "")
    ti = block.get("input") if isinstance(block.get("input"), dict) else {}
    if name == "Bash":
        return False
    call = G.read_call(name, ti)
    if call.window and call.texts and not call.reads:
        return True                                    # ① 窓を立てる・窓へ送る
    if call.sends:
        return True                                    # ① 人・窓へ文を送る
    if not call.reads and any(handoff_heads(t) >= set(HANDOFF_PARTS) for _, t in call.texts):
        return True                                    # ② 4 欄を見出しに持つ文を書く（file の名は問わない）
    if patterns:
        try:
            body = json.dumps(ti, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            body = str(ti)
        sig = "%s %s" % (name, body)
        if any(re.search(p, sig) for p in patterns):
            return True                                # ③ 値の表の足し
    return False


def _tool_uses(row):
    msg = row.get("message")
    c = msg.get("content") if isinstance(msg, dict) else None
    return [b for b in c if isinstance(b, dict) and b.get("type") == "tool_use"] if isinstance(c, list) else []


def handoff_state(tpath, limit, patterns):
    """(目安を越えたか, 越えた後に引き継ぎの跡が在るか)。越えた行そのものの道具の呼び出しも越えた後に数える。"""
    over = False
    for row in G.iter_rows(tpath):
        if row.get("type") != "assistant":
            continue
        if not over:
            u = (row.get("message") or {}).get("usage") or {}
            if isinstance(u, dict):
                tot = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
                over = tot >= limit
        if over and any(is_handoff(b, patterns) for b in _tool_uses(row)):
            return True, True
    return over, False


def _stop_count(sid, reset):
    """この窓の今のターンで差し戻した回数を 1 つ進めて返す（stop_hook_active が偽＝新しい締めなら 0 から）。
    印を残せなければ大きい数（＝差し戻さない。回り続けるより通す方を選ぶ）。"""
    path = os.path.join(G.tmp_dir("ctx"), sid + ".stop")
    n = 0
    if not reset:
        try:
            n = int(open(path).read().strip() or 0)
        except (OSError, ValueError):
            n = 0
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(str(n + 1))
    except OSError:
        return 1 << 30
    return n + 1


def stop(data, vals):
    """差し戻すなら理由、通すなら ""。"""
    tpath = str(data.get("transcript_path") or "")
    if not tpath or not os.path.isfile(tpath) or "/subagents/" in tpath.replace(os.sep, "/"):
        return ""
    cap = int(vals.get("context_stop_max") or 0)
    if cap <= 0:
        return ""
    limit = vals.get("context_limit") or G.DEFAULTS["context_limit"]
    patterns = [p for p in (vals.get("context_handoff") or []) if isinstance(p, str) and p]
    try:
        if measure(tpath) < limit:     # 目安の手前（まとめ直して縮んだ後も）＝差し戻さない
            return ""
        over, handed = handoff_state(tpath, limit, patterns)
    except Exception:          # noqa: BLE001  会話ログが読めない＝見張りの故障。窓を止めない
        return ""
    if not over or handed:
        return ""
    sid = G.safe_id(data.get("session_id") or os.path.basename(tpath))
    if not sid or _stop_count(sid, reset=not data.get("stop_hook_active")) > cap:
        return ""
    if unattended(tpath, vals, data):
        how = ("別の窓へ返す窓か人のいない窓なので、今の段を終え、引き継ぎ（%s）を書いて"
               "返し先の窓へ送り、止まる（次の段へ進まない）。" % "・".join(HANDOFF_PARTS))
    else:
        how = ("区切りの良い所で引き継ぎ（%s）を書き、後継の窓を立ててそれを渡す（後継は"
               "返し先を継ぐ）。この返事では、後継の窓へ替えた事と、続きをどの窓で見ればよいかをオーナーに書く。" % "・".join(HANDOFF_PARTS))
    return "\n".join([
        "[guard] この窓の文脈が目安（%s token）を越えた後、まだ引き継いでいないので、締めを差し戻した（オーナー同意 "
        "2026-11-19・止めたのは AI の締めだけ・人の操作は止めていない）。" % format(limit, ","),
        "直し方: " + how,
        "引き継ぎの跡と数える物: 目安を越えた後の道具の呼び出しのうち、他の窓を立てる・窓や人へ文を送る物、%s を見出しに"
        "持つ文を file に書く物（file の名は問わない）、値の表 guard.context_handoff に当たる Bash でない物（今の値: %s）。"
        "Bash の命令の字は数えない。一度あれば、この窓ではもう差し戻さない。" % ("・".join(HANDOFF_PARTS), "・".join(patterns[:6]) or "無し"),
        "上限: 同じターンで %d 回まで差し戻し、越えたら通して届ける。" % cap,
        "誤って差し戻された時（別の道で引き継いだ等）: その道の呼び出しに当たる形を値の表の guard.context_handoff に足す。"
        "差し戻しそのものを外すのは guard.context_stop_max を 0 に（どちらも PR とレビューを通す）。細目は skill `guard:guard-rules`。",
    ])
