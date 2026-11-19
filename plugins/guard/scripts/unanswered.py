"""未回答の台帳 — 選択肢モーダル（AskUserQuestion）が答えのないまま閉じた問いを消さない。

なぜ在るか: モーダルが無応答で閉じると、その問いはどこにも残らない。推測で先へ進み、オーナーが戻っても
二度と聞かれない。締切を伸ばしても「閉じた問いが消える」は直らない＝ここが直すのは問いの寿命。

3 つの口:
  capture（PostToolUse・AskUserQuestion の返り）
    - 答えの無い問いを台帳へ積み、答えが返った問いは台帳から降ろす（前の窓から持ち越した問いも閉じる）。
    - 1 つも答えが返らなければ「離席の窓」を開き、隣に 1 行鳴らす（ここから先は元に戻せる作業だけ）。
      1 つでも返れば窓を閉じる。窓は irreversible が読む。
  resurface（SessionStart）
    - 台帳に残る問いを、今の窓の流れの中で扱うよう渡す: 答え済み・もう要らない問いは降ろす（drop の口）、
      今の頼みと関わる問いだけを前提を 1〜2 文添えて出し直す（問いの文は言い直してよい・選択肢の中身は変えない）、
      関わらない問いは冒頭で画面に出さず締めの 1 行で知らせる。
  drop（命令: python3 unanswered.py drop <key>... --why <一言>／list）
    - AI が答え済み・もう要らないと見た問いを台帳から降ろす（降ろした控えは dropped_recent に残る）。
    - 台帳の寿命は最後に出てから LEDGER_TTL_HOURS（古い問いが毎回鳴らない。1 時間答えの無い問いは親の窓が知らせる）。
  離席の窓（away）
    - 窓（セッション）ごとの印 1 個。止める側は在席中は stat 1 回で終わる。持ち越した問いは窓を開けない
      ＝1 件の未回答がずっと戻せない操作を塞ぐことは起きない。

同じ問いの見分け: key（文面）の一致・文面の含有、または選択肢の見出しの組が同じで問いの語を共にする（出し直しで
  文面を言い直しても、答えが返れば台帳の元の問いが降りる）。
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
MAX_SHOW = 4           # 冒頭で出し直させる上限（モーダルは 1 回 4 問まで）
LEDGER_TTL_HOURS = 24  # 台帳の寿命（最後に出てから）
_WS = re.compile(r"\s+")


# ── 問いの同一性 ──
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


_REC = re.compile(r"[（(]\s*推奨\s*[)）]")


def label_set(opts):
    """選択肢の見出しの組（推奨の印と空白を除く）。"""
    return frozenset(_REC.sub("", norm(o.get("label"))).strip() for o in opts or []
                     if isinstance(o, dict) and norm(o.get("label")))


def same_by_options(a, b):
    """言い直した問いの見分け: 選択肢の見出しの組が同じ（2 つ以上）で、問いの文の語（2 字の並び）を共にする。
    「終わった／うまくいかない」のような決まった組だけでは同じとみなさない（語を共にしない別の確かめを閉じない）。"""
    la, lb = label_set(a.get("options")), label_set(b.get("options"))
    if len(la) < 2 or la != lb:
        return False
    try:
        import ask_shape
        wa = ask_shape._words({"question": a.get("question")}, G.DEFAULTS)    # 見出しは窓ごとに同じ物が付きやすいので見ない
        return bool(wa & ask_shape._words({"question": b.get("question")}, G.DEFAULTS))
    except Exception:       # noqa: BLE001
        return False


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
    return {"schema": SCHEMA, "pending": [], "answered_recent": [], "dropped_recent": []}


def _fresh(p):
    ts = G.parse_ts(p.get("last_seen_at")) if isinstance(p, dict) else None
    return ts is not None and (G.parse_ts(G.now_utc()) - ts).total_seconds() < LEDGER_TTL_HOURS * 3600


def _parse(raw):
    try:
        d = json.loads(raw) if raw.strip() else _empty()
    except ValueError:
        return _empty()
    if not isinstance(d, dict):
        return _empty()
    for k in ("pending", "answered_recent", "dropped_recent"):
        if not isinstance(d.get(k), list):
            d[k] = []
    d["pending"] = [p for p in d["pending"] if _fresh(p)]      # 寿命を過ぎた問いは読む時に降ろす
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
        if cur is None:     # 言い直して出した問いがまた閉じた＝元の問いに重ねる（同じ事を 2 行で持たない）
            old = next((p for p in by_key.values() if same_by_options(p, it)), None)
            if old is not None:
                del by_key[old.get("key")]
                cur = dict(old, key=k)
                by_key[k] = cur
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
        hit = next(((t, a) for k, t, a, q in pairs
                    if p.get("key") == k or same_question(p.get("question"), t) or same_by_options(p, q)), None)
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
ここから先は戻せる作業だけを推奨案で進めてください。戻せない作業は始めず、答えを待ちます。迷ったら
「今これをやって、後で答えが逆だった時に戻せるか」で切ります。DB の破棄・メールの送信・Notion の物理削除・
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
    stems = " / ".join("「%s」" % i["question"][:48] for i in unanswered[:4])
    return REMINDER.format(n=len(unanswered), stems=stems, ttl=LEDGER_TTL_HOURS, ledger=path or "(置き場を決められず)")


def resurface(data, vals):
    """SessionStart。台帳に残る問いを出し直させる文（無ければ ""）。"""
    if G.unattended_by_env(vals):
        return ""
    path = ledger_path(vals, data)
    items = [p for p in read_ledger(path).get("pending", []) if isinstance(p, dict) and p.get("question")]
    if not items:
        return ""
    lines = ["<unanswered-question-carryover>",
             "前の窓で答えのないまま閉じた問いが %d 件あります。今の窓の流れの中で、1 件ずつ次のどれかにします。" % len(items),
             "- 答え済み（今の頼み・会話・決定の記録で答えが出ている）か、もう要らない問い → 出さずに台帳から降ろす:",
             "    %s" % DROP_CMD,
             "- 今の頼みと関わる問い → 出す前にチャットで前提（何の件で・なぜまだ答えが要るか）を 1〜2 文書き、"
             "AskUserQuestion で出し直す。問いの文は今の流れに合わせて短く言い直してよい（選択肢の見出しは変えない＝"
             "同じ問いと見分ける印。答えが返れば台帳の元の問いも降りる）。",
             "- 今の頼みと関わらない問い → この窓の最初に画面で出さない。返事の締めの「あなたがやること」に 1 行"
             "（何の件の問いが残っているか）で知らせ、オーナーが求めた時に出す。",
             "同じ問いを言い方だけ変えて何度も出さない。", ""]
    for n, it in enumerate(items[:MAX_SHOW], 1):
        lines.append("%d. key: %s（初めて閉じた %s・閉じた回数 %s）" % (
            n, it.get("key", ""), it.get("first_seen_at", "")[:16], it.get("timeouts", 1)))
        lines.append("   question: %s" % it.get("question", ""))
        if it.get("header"):
            lines.append("   header: %s" % it["header"])
        for o in it.get("options") or []:
            lines.append("   - %s : %s" % (o.get("label", ""), (o.get("description") or "")[:160]))
        lines.append("")
    if len(items) > MAX_SHOW:
        lines.append("（ほか %d 件は台帳に残ります。モーダルは 1 回 4 問までなので次の機会に）" % (len(items) - MAX_SHOW))
    lines.append("答えが返れば台帳から自動で降ります。また閉じれば次の窓へ持ち越します。台帳: %s" % path)
    lines.append("降ろす時の key は上の各行の key。")
    lines.append("</unanswered-question-carryover>")
    return "\n".join(lines)


DROP_CMD = 'python3 "%s" drop <key> --why "<答え済み・要らない訳を一言>"' % os.path.abspath(__file__)


def cli(argv):
    """命令の口: drop <key>... [--why 文]／list。台帳は今の dir の repo の物（hook と同じ置き場）。"""
    payload = {"cwd": os.getcwd()}
    vals = G.values(payload)
    path = ledger_path(vals, payload)
    if not argv or argv[0] not in ("drop", "list"):
        sys.stderr.write("使い方: unanswered.py drop <key>... [--why 文] ／ unanswered.py list\n")
        return 2
    if argv[0] == "list":
        for p in read_ledger(path).get("pending", []):
            if isinstance(p, dict):
                print("%s\t%s" % (p.get("key", ""), p.get("question", "")))
        return 0
    args, why = list(argv[1:]), ""
    if "--why" in args:
        i = args.index("--why")
        why = " ".join(args[i + 1:]).strip()
        args = args[:i]
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
    sys.exit(cli(sys.argv[1:]))
