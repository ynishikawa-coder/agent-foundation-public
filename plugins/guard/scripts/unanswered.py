"""未回答の台帳 — 選択肢モーダル（AskUserQuestion）が答えのないまま閉じた問いを消さない。

意図: 閉じた問いを消さず残す（ここが直すのは問いの寿命）。
課題: モーダルが無応答で閉じると、その問いはどこにも残らない。推測で先へ進み、オーナーが戻っても
二度と聞かれない。
原因: 問いの置き場がモーダルの中だけだった（締切を伸ばしても「閉じた問いが消える」は直らない）。

3 つの口:
  capture（PostToolUse・AskUserQuestion の返り）
    - 答えの無い問いを台帳へ積み、答えが返った問いは台帳から降ろす（前の窓から持ち越した問いも閉じる）。
    - 1 つも答えが返らなければ「離席の窓」を開き、隣に 1 行鳴らす（ここから先は元に戻せる作業だけ）。
      1 つでも返れば窓を閉じる。窓は irreversible が読む。
  resurface（SessionStart）
    - 台帳に残る問いを、今の窓の流れの中で扱うよう渡す: 答え済み・もう要らない問いは降ろす（drop の口）、
      今の頼みと関わる問いだけを前提を 1〜2 文と具体例・判断の物差しの 2 行を添えて出し直す（問いの文は言い直してよい・選択肢の中身は変えない）、
      関わらない問いは冒頭で画面に出さず締めの 1 行で知らせる。
  drop（命令: python3 unanswered.py drop <key>... --why <一言>／list）
    - AI が答え済み・もう要らないと見た問いを台帳から降ろす（降ろした控えは dropped_recent に残る）。
    - 台帳に残る問いは全部渡す（頭の N 件で切らない。出し直す問いが 4 を越えたら 4 問ずつ続けて出させる）。
    - 台帳の寿命は最後に出てから LEDGER_TTL_HOURS（古い問いが毎回鳴らない。答えの無い問いを時間で数えて親が知らせ直す仕組みは持たない＝2026-11-22 の決定）。
      寿命を過ぎた問いは黙って消さない: 読む・積む時は残し、次の resurface で文面ごと一度知らせてから降ろす
      （降ろした控えは台帳の expired_recent に残る）。
    - 行の状態（生きている／寿命切れ／文面が無い）の正本は row_state の 1 つ。resurface・人のいない窓・list が同じに読む
      （口ごとに別の filter で決めると、どの口にも載らない行が黙って残る）。
    - 人のいない窓（unattended_env が真）の SessionStart は、寿命切れと文面の無い行を黙って控え（expired_recent・
      notified=false）へ移すだけ。知らせは次の人のいる窓の resurface が、まだ知らせていない控えごと一度出す。
    - 文面（question）の無い行は出し直せない＝欠けた材料。生きていても寿命切れと同じに知らせて降ろす。
  離席の窓（away）
    - 窓（セッション）ごとの印 1 個。止める側は在席中は stat 1 回で終わる。持ち越した問いは窓を開けない
      ＝1 件の未回答がずっと戻せない操作を塞ぐことは起きない。

同じ問いの見分け: key（文面）の一致か文面の含有だけ（字の形で別の問いを結ばない＝知らない時は結ばない）。
  文面を言い直して出した問いに答えが返ったら、AI が元の問いを drop <元の key> で降ろす（出し直しの文で渡す）。
判定の線: 問い 1 つを単位に「その問いの文面が answers のキーに無い」＝答えが無い（afkTimeoutMs は見ない。
  時間切れの印つきでも一部だけ答えが返る返りがある）。
子の窓も問う窓（オーナーへ直に問う）として同じに扱う。値の表の unattended_env が真の窓だけ働かない。
台帳の天井: 台帳は消せば消える（会話ログと違い追記だけではない）。台帳は思い出すための物で、通すための物ではない。
壊れた時は全部黙って通す（答えを引き出すための層で、仕事を止める価値は無い）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import guard_common as G  # noqa: E402

ASK_TOOL = "AskUserQuestion"
SCHEMA = "af-guard/unanswered/v1"
LEDGER_NAME = "unanswered-questions.json"
ANSWERED_KEEP = 20     # 観測用に残す「答えが返った問い」「降ろした問い」の上限（判定には使わない）
CONTAIN_MIN = 16       # 文面の含有で同じ問いとみなす最低の長さ（短い問い同士の取り違えを防ぐ）
ASK_BATCH = 4          # モーダル 1 回に載る問いの数（出し直しはこの数ずつ続けて出させる）
LEDGER_TTL_HOURS = 24  # 台帳の寿命（最後に出てから）
ROOT_CAUSE = ("出し直すだけで済ませず、意図（オーナーの答えを得て進む）とのずれから入り、答えが返らなかった原因（聞く時・問いの形・聞き方）を"
              "細目 §3「まず構造を疑う」で探して直してください。")
_WS = re.compile(r"\s+")


# ── 問いの同一性 ──

# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"post": "capture", "start": "resurface"}

def norm(text):
    return _WS.sub(" ", text).strip() if isinstance(text, str) else ""


def qkey(text):
    return hashlib.sha1(norm(text).encode("utf-8")).hexdigest()[:16]


def same_question(a, b):
    """完全一致、または両方 16 文字以上で一方が他方を含む（出し直しで「（再掲）」を足す等）。"""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return len(na) >= CONTAIN_MIN and len(nb) >= CONTAIN_MIN and (na in nb or nb in na)


def question_payload(q):
    """モーダル 1 問分を、出し直しにそのまま使える形へ落とす。"""
    if not isinstance(q, dict):
        return None
    text = norm(q.get("question"))
    if not text:
        return None
    opts = [{"label": str(o.get("label"))[:120], "description": str(o.get("description") or "")[:400]}
            for o in (q.get("options") or []) if isinstance(o, dict) and o.get("label")]
    return {"key": qkey(text), "question": text, "header": str(q.get("header") or "")[:40],
            "multiSelect": bool(q.get("multiSelect")), "options": opts}


def split_response(tool_response):
    """道具の返りから (答えの無い問い, 答えが返った (key, 文面, 答え)) を取る。読めなければ (None, None)。"""
    if not isinstance(tool_response, dict) or "questions" not in tool_response:
        return None, None
    answers = tool_response.get("answers")
    answers = answers if isinstance(answers, dict) else {}
    by_norm = {norm(k): v for k, v in answers.items()}
    unanswered, pairs = [], []
    for q in tool_response.get("questions") or []:
        p = question_payload(q)
        if not p:
            continue
        if p["question"] in by_norm:
            pairs.append((p["key"], p["question"], str(by_norm[p["question"]] or "")[:200], p))
        else:
            unanswered.append(p)
    return unanswered, pairs


# ── 台帳（窓をまたいで残す）──
def repo_home(root):
    """台帳の鍵にする repo の本体の根。作業部屋（git worktree）から起動しても本体と同じ 1 冊を指すよう、
    git の共通の dir（--git-common-dir）の親を使う。git の外・読めない時は root そのもの。"""
    real = os.path.realpath(root)
    try:
        out = subprocess.run(["git", "-C", real, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             capture_output=True, text=True, timeout=10,
                             env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")})
        common = out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        common = ""
    if common and os.path.basename(common.rstrip(os.sep)) == ".git":
        return os.path.realpath(os.path.dirname(common.rstrip(os.sep)))
    return real


def ledger_path(vals, payload=None):
    """repo ごとに 1 冊（作業部屋も本体と同じ冊）。置き場は値の表の state_dir の下、本体の根の path から作った名の dir。"""
    base = G.state_dir(vals, payload)
    root = G.project_dir(payload)
    if not base or not root:
        return ""
    real = repo_home(root)
    key = "%s-%s" % (G.safe_id(os.path.basename(real), 40) or "repo",
                     hashlib.sha1(real.encode("utf-8")).hexdigest()[:10])
    return os.path.join(base, key, LEDGER_NAME)


def _empty():
    return {"schema": SCHEMA, "pending": [], "answered_recent": [], "dropped_recent": [], "expired_recent": []}


def _fresh(p):
    ts = G.parse_ts(p.get("last_seen_at")) if isinstance(p, dict) else None
    return ts is not None and (G.parse_ts(G.now_utc()) - ts).total_seconds() < LEDGER_TTL_HOURS * 3600


def row_state(p):
    """台帳の 1 行の状態の正本: "live"（出し直す）／"expired"（寿命切れ）／"broken"（文面が無く出し直せない）。
    dict でない行は None（_parse が先に捨てる）。"""
    if not isinstance(p, dict):
        return None
    if not norm(p.get("question")):
        return "broken"
    return "live" if _fresh(p) else "expired"


def _unnotified(e):
    """控え（expired_recent）の行で、まだ人のいる窓で知らせていない物（人のいない窓が移した物）。"""
    return isinstance(e, dict) and e.get("notified") is False


def _trim_expired(recent):
    """控えの上限は知らせ済みの物にだけ当てる（まだ知らせていない物は上限で黙って落とさない）。"""
    done = [e for e in recent if not _unnotified(e)]
    return done[-ANSWERED_KEEP:] + [e for e in recent if _unnotified(e)]


def _parse(raw):
    try:
        d = json.loads(raw) if raw.strip() else _empty()
    except ValueError:
        return _empty()
    if not isinstance(d, dict):
        return _empty()
    for k in ("pending", "answered_recent", "dropped_recent", "expired_recent"):
        if not isinstance(d.get(k), list):
            d[k] = []
    d["pending"] = [p for p in d["pending"] if isinstance(p, dict)]   # 寿命を過ぎた問いも残す（降ろすのは知らせてから）
    d["schema"] = SCHEMA
    return d


def read_ledger(path):
    if not path or not os.path.isfile(path):
        return _empty()
    try:
        with open(path, encoding="utf-8") as f:
            return _parse(f.read())
    except OSError:
        return _empty()


def update_ledger(path, fn):
    """鍵（<台帳>.lock）の中で 読む→fn で直す→書く を 1 回でする（同じ機械の 2 つの窓が同時に積んでも消えない）。
    書けなければ False。fn は台帳の dict を直に直す。"""
    if not path:
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".lock", "a+") as lock:
            try:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            except ImportError:      # 鍵の無い OS では鍵なしで進む
                pass
            data = read_ledger(path)
            fn(data)
            data["updated_at"] = G.now_utc()
            tmp = "%s.%d.tmp" % (path, os.getpid())
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        return True
    except Exception:
        return False


def carry(data, items, session_id):
    """答えの無い問いを積む（在れば中身を最新にし回数を足す）。戻り値＝新しく積んだ件数。"""
    now = G.now_utc()
    by_key = {p.get("key"): p for p in data.get("pending", []) if isinstance(p, dict)}
    added = 0
    for it in items or []:
        k = it.get("key")
        if not k:
            continue
        cur = by_key.get(k)
        if cur is None:
            cur = dict(it, first_seen_session=session_id, first_seen_at=now, timeouts=1)
            by_key[k] = cur
            added += 1
        else:
            keep = {"first_seen_session": cur.get("first_seen_session"), "first_seen_at": cur.get("first_seen_at"),
                    "timeouts": int(cur.get("timeouts") or 1) + 1}
            cur.update(it)
            cur.update(keep)
        cur["last_seen_session"] = session_id
        cur["last_seen_at"] = now
    data["pending"] = [by_key[k] for k in sorted(by_key)]
    return added


def close_answered(data, pairs):
    """答えが返った問いを台帳から降ろす（key の一致か文面の含有）。戻り値＝降ろした件数。"""
    if not pairs:
        return 0
    now = G.now_utc()
    keep, closed = [], 0
    recent = list(data.get("answered_recent") or [])
    for p in data.get("pending", []):
        if not isinstance(p, dict):
            continue
        hit = next(((t, a) for k, t, a, _q in pairs
                    if p.get("key") == k or same_question(p.get("question"), t)), None)
        if hit is None:
            keep.append(p)
            continue
        closed += 1
        recent.append({"key": p.get("key"), "question": p.get("question"), "answer": hit[1], "closed_at": now})
    data["pending"] = keep
    data["answered_recent"] = recent[-ANSWERED_KEEP:]
    return closed


def drop(data, keys, why):
    """AI が答え済み・もう要らないと見た問いを降ろす。戻り値＝降ろした問いの並び。"""
    want = {str(k).strip() for k in keys if str(k).strip()}
    keep, gone = [], []
    for p in data.get("pending", []):
        if isinstance(p, dict) and p.get("key") in want:
            gone.append(p)
        else:
            keep.append(p)
    now = G.now_utc()
    data["pending"] = keep
    data["dropped_recent"] = (list(data.get("dropped_recent") or [])
                              + [{"key": p.get("key"), "question": p.get("question"), "why": why, "dropped_at": now}
                                 for p in gone])[-ANSWERED_KEEP:]
    return gone


def retire(data, keys, notified, notified_marks=(), keyless=0):
    """寿命切れ・文面の無い行を台帳から降ろし、控えを expired_recent へ。戻り値＝降ろした件数。
    keys に在る行と、key の無い文面なしの行を読んだ数（keyless）までだけを、降ろす直前に row_state で照らし直して
    降ろす（読んでから書くまでに積まれた・積み直された行は、知らせずに降ろさない）。notified=False は人のいない窓が黙って移す時。
    notified_marks（(key, expired_at) の並び）は、知らせ終えた控えに印を付ける。"""
    now = G.now_utc()
    keep, gone = [], []
    for p in data.get("pending", []):
        st = row_state(p)
        hit = st in ("expired", "broken") and p.get("key") in keys
        if st == "broken" and not p.get("key") and keyless > 0:
            hit, keyless = True, keyless - 1
        (gone if hit else keep).append(p)
    data["pending"] = keep
    recent = list(data.get("expired_recent") or [])
    marks = set(notified_marks)
    for e in recent:
        if _unnotified(e) and (e.get("key"), e.get("expired_at")) in marks:
            e["notified"] = True
    recent += [{"key": p.get("key"), "question": p.get("question"), "state": row_state(p),
                "expired_at": now, "notified": notified} for p in gone]
    data["expired_recent"] = _trim_expired(recent)
    return len(gone)


# ── 離席の窓（窓＝セッションの中だけで閉じる）──
def away_path(session_id):
    sid = G.safe_id(session_id)
    return os.path.join(G.tmp_dir("away"), sid + ".json") if sid else ""


def open_away(session_id, items):
    p = away_path(session_id)
    if not p or not items:
        return ""
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"since": G.now_utc(), "session_id": session_id,
                       "questions": [i.get("question", "")[:120] for i in items]}, f, ensure_ascii=False)
        return p
    except OSError:
        return ""


def close_away(session_id):
    p = away_path(session_id)
    try:
        os.remove(p)
        return True
    except OSError:
        return False


def read_away(session_id):
    """開いていれば中身、閉じていれば None（在席中はここで終わる＝stat 1 回）。"""
    p = away_path(session_id)
    if not p or not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


# ── hook の口 ──
REMINDER = """<unanswered-question>
選択肢モーダルが答えのないまま閉じました（{n} 件）。オーナーは席を外しているとみなします。
ここから先は、この答えに頼らない作業だけを進めてください。答えに頼る作業（答えで中身が変わる・合意が要る・
戻せない）は推奨で先に進めず、答えを待ちます。DB の破棄・メールの送信・Notion の物理削除・
git で戻せない削除は、答えが返るかオーナーが何か打つまで機械が止めます。
閉じた問い: {stems}
この問いは台帳に積みました。{ttl} 時間の間、次の窓へ持ち越します（次の窓では流れに合う時だけ前提を添えて
出し直し、答え済み・要らなくなった問いは降ろす。台帳: {ledger}）。
</unanswered-question>"""


def capture(data, vals):
    """PostToolUse。隣に出す文（無ければ ""）。"""
    if (data.get("tool_name") or "") != ASK_TOOL or G.unattended_by_env(vals):
        return ""
    tpath = str(data.get("transcript_path") or "")
    if "/subagents/" in tpath.replace(os.sep, "/"):
        return ""     # 助手の中の使い捨ての文脈＝オーナーに出た問いではない
    unanswered, pairs = split_response(data.get("tool_response"))
    if unanswered is None:
        return ""
    session_id = str(data.get("session_id") or "")
    path = ledger_path(vals, data)
    if unanswered or pairs:
        update_ledger(path, lambda d: (close_answered(d, pairs), carry(d, unanswered, session_id)))
    if pairs:
        close_away(session_id)
    elif unanswered:
        open_away(session_id, unanswered)
    if not unanswered:
        return ""
    stems = " / ".join("「%s」" % i["question"][:48] for i in unanswered)
    return REMINDER.format(n=len(unanswered), stems=stems, ttl=LEDGER_TTL_HOURS, ledger=path or "(置き場を決められず)")


def _lines_for(n, it, with_key=True):
    out = []
    if with_key:
        out.append("%d. key: %s（初めて閉じた %s・閉じた回数 %s）" % (
            n, it.get("key", ""), str(it.get("first_seen_at", ""))[:16], it.get("timeouts", 1)))
        out.append("   question: %s" % it.get("question", ""))
    else:
        out.append("%d. question: %s" % (n, it.get("question", "")))
    if it.get("header"):
        out.append("   header: %s" % it["header"])
    for o in it.get("options") or []:
        out.append("   - %s : %s" % (o.get("label", ""), (o.get("description") or "")[:160]))
    out.append("")
    return out


def _quiet_retire(path):
    """人のいない窓: 寿命切れ・文面の無い行を、知らせずに控えへ移す（知らせは次の人のいる窓）。台帳が無ければ作らない。"""
    if not path or not os.path.isfile(path):
        return
    old = [p for p in read_ledger(path).get("pending", []) if row_state(p) not in (None, "live")]
    keys = {p.get("key") for p in old if p.get("key")}
    keyless = sum(1 for p in old if not p.get("key"))
    if old:
        update_ledger(path, lambda d: retire(d, keys, notified=False, keyless=keyless))


def _expired_line(n, it):
    if row_state(it) == "broken" or not norm(it.get("question")):
        return ["%d. （文面が無い行・key: %s。出し直せないので降ろす）" % (n, it.get("key") or "なし"), ""]
    return _lines_for(n, it, with_key=False)


def resurface(data, vals):
    """SessionStart。台帳に残る問いを全部渡し、寿命を過ぎた・文面の無い問いは知らせてから降ろす文（無ければ ""）。
    人のいない窓では知らせず、寿命切れ・文面の無い行を控えへ移すだけ（次の人のいる窓が知らせる）。"""
    path = ledger_path(vals, data)
    if G.unattended_by_env(vals):
        _quiet_retire(path)
        return ""
    ledger = read_ledger(path)
    rows = [p for p in ledger.get("pending", []) if row_state(p)]
    items = [p for p in rows if row_state(p) == "live"]
    gone = [p for p in rows if row_state(p) != "live"]
    moved = [e for e in ledger.get("expired_recent", []) if _unnotified(e)]   # 人のいない窓が移した物
    expired = moved + gone
    if not items and not expired:
        return ""
    # 寿命切れの知らせを前に置く（文の後ろが切られても、降ろす問いは読まれる）
    lines = ["<unanswered-question-carryover>"]
    if expired:
        lines += ["次の %d 件は最後に出てから %d 時間を過ぎたので、台帳から降ろします（文面が無い行は出し直せないので"
                  "一緒に降ろす。この知らせが最後です）。" % (len(expired), LEDGER_TTL_HOURS),
                  "今の頼みと関わってまだ要る問いなら、前提と「具体例:」「判断の物差し:」の 2 行をチャットに書いてから AskUserQuestion で出し直してください"
                  "（出せば台帳に積み直されます）。", ""]
        for n, it in enumerate(expired, 1):
            lines += _expired_line(n, it)
        keys = {p.get("key") for p in gone if p.get("key")}
        keyless = sum(1 for p in gone if not p.get("key"))
        marks = [(e.get("key"), e.get("expired_at")) for e in moved]
        if not update_ledger(path, lambda d: retire(d, keys, notified=True, notified_marks=marks, keyless=keyless)):
            lines.append("（台帳を書けず、降ろせませんでした。次の窓でもう一度知らせます）")
        lines += ["降ろした問いの控え: 台帳 %s の expired_recent" % path]
        if not items:
            lines.append(ROOT_CAUSE)     # 寿命切れだけの時も、答えが返らなかった原因へ向ける
        lines.append("")
    if items:
        lines += ["前の窓で答えのないまま閉じた問いが %d 件あります。今の窓の流れの中で、1 件ずつ次のどれかにします。" % len(items),
                  "- 答え済み（今の頼み・会話・決定の記録で答えが出ている）か、もう要らない問い → 出さずに台帳から降ろす:",
                  "    %s" % DROP_CMD,
                  "- 今の頼みと関わる問い → 出す前にチャットで前提（何の件で・なぜまだ答えが要るか）を 1〜2 文と、行頭が「具体例:」と"
                  "「判断の物差し:」の 2 行（問いが懸かる実物の 1 例・どんな理由で選んでほしいか）を書いてから、"
                  "AskUserQuestion で出し直す。問いの文は今の流れに合わせて短く言い直してよい。言い直した問いに答えが"
                  "返ったら、元の問いを上の drop で降ろす（言い直した問いを機械は元の問いと結ばない）。"
                  "出す問いが %d を越えたら %d 問ずつ続けて出す（どの問いも飛ばさない）。" % (ASK_BATCH, ASK_BATCH),
                  "- 今の頼みと関わらない問い → この窓の最初に画面で出さない。返事の締めの「あなたがやること」に 1 行"
                  "（何の件の問いが残っているか）で知らせ、オーナーが求めた時に出す。",
                  "同じ問いを言い方だけ変えて何度も出さない。下の %d 件を全部、どれかにする。" % len(items),
                  ROOT_CAUSE, ""]
        for n, it in enumerate(items, 1):
            lines += _lines_for(n, it)
        lines.append("答えが返れば台帳から自動で降ります。また閉じれば次の窓へ持ち越します。台帳: %s" % path)
        lines.append("降ろす時の key は上の各行の key。")
    lines.append("</unanswered-question-carryover>")
    return "\n".join(lines)


LIST_MARK = {"live": "",
             "expired": "[寿命切れ・次の窓の冒頭で知らせて降ろす] ",
             "broken": "[文面が無い・次の窓の冒頭で知らせて降ろす] ",
             "moved": "[寿命切れ・人のいない窓が控えへ移した・次の人のいる窓で知らせる] "}
DROP_CMD = 'python3 "%s" drop <key> --why "<答え済み・要らない訳を一言>"' % os.path.abspath(__file__)


def cli(argv):
    """命令の口: drop <key>... [--why 文]／list。台帳は今の dir の repo の物（hook と同じ置き場）。"""
    payload = {"cwd": os.getcwd()}
    vals = G.values(payload)
    path = ledger_path(vals, payload)
    usage = "使い方: unanswered.py drop <key>... --why 文 ／ unanswered.py list\n"
    if not argv or argv[0] not in ("drop", "list") or (argv[0] == "list" and argv[1:]):
        sys.stderr.write(usage)
        return 2
    if argv[0] == "list":
        ledger = read_ledger(path)
        for p in ledger.get("pending", []):
            if row_state(p):
                print("%s\t%s%s" % (p.get("key", ""), LIST_MARK[row_state(p)], p.get("question", "")))
        for e in ledger.get("expired_recent", []):
            if _unnotified(e):
                print("%s\t%s%s" % (e.get("key", ""), LIST_MARK["moved"], e.get("question") or ""))
        return 0
    args, why = list(argv[1:]), ""
    if "--why" in args:
        i = args.index("--why")
        why = " ".join(args[i + 1:]).strip()
        args = args[:i]
    # 知らない印・2 度目の --why は既定で止める（key や訳の文に紛れて黙って通さない）
    bad = [a for a in args + why.split() if a.startswith("--")]   # 訳の側に紛れた印（2 度目の --why も）も止める
    if bad:
        sys.stderr.write("知らない印: %s\n%s" % (" ".join(bad), usage))
        return 2
    if not args or not why:
        sys.stderr.write("drop には key と --why（答え済み・要らない訳）が要る\n")
        return 2
    gone = []
    ok = update_ledger(path, lambda d: gone.extend(drop(d, args, why[:200])))
    if not ok:
        sys.stderr.write("台帳に書けなかった: %s\n" % (path or "(置き場を決められず)"))
        return 1
    missing = sorted(set(args) - {p.get("key") for p in gone})
    for p in gone:
        print("降ろした: %s %s" % (p.get("key"), p.get("question", "")[:60]))
    for k in missing:
        print("台帳に無い key: %s" % k)
    return 0 if gone else 1


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
    import af_place  # noqa: E402  古い版の窓から呼ばれても、入った中でいちばん新しい版で回す（入口の 1 行）
    af_place.run_newest(__file__)
    sys.exit(cli(sys.argv[1:]))
