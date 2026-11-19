"""guard の跡の見分け（prior_ask・context_size）: 跡は道具の名と入力の欄で見て、頼みの境は頼みの印で切り、
引く先の無い repo の窓を止めず、値の表の壊れた形は黙って通さず名指すか（注入の試験・入力は全部作り物）。"""
import importlib.util
import json
import sys

import pytest

from test_guard import GUARD, ROOT, ask_pre, deny_reason, env, hook, q, write_log  # noqa: F401  （env は fixture）
from test_guard_context_stop import over_log, stop_hook

SCRIPTS = ROOT / "plugins" / "guard" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True
import guard_common as G  # noqa: E402

LOOKUP_TOOL = "mcp__fake__lookup_records"


def use(name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


def owner(text, uuid, pid=None):
    row = {"type": "user", "uuid": uuid, "message": {"content": text}}
    if pid:
        row["promptId"] = pid
    return row


def ask_with(tpath, sid="s1"):
    p = ask_pre(q("会議を回数で別に数えますか", header="会議の数え方"))
    p.update({"transcript_path": tpath, "session_id": sid})
    return p


def values(env, tmp_path, table):
    path = tmp_path / "values.json"
    path.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    env["SKILL_VALUES"] = str(path)


def lookup(env, tmp_path, specs):
    values(env, tmp_path, {"guard": {"ask_prior_lookup": specs}})


def log(tmp_path, *rows, name="t.jsonl"):
    return write_log(tmp_path / name, [owner("作り物の頼み", "u1", "p1"), *rows])


# ── 1. 跡は道具の名と入力の欄で見る（入力にその字を含むだけの呼び出しを跡に数えない）──
FAKE_TRACES = [
    ("Bash の命令に道具の名の字を書いただけ", use("Bash", {"command": "echo %s" % LOOKUP_TOOL})),
    ("Grep で問いの表の字を探しただけ", use("Grep", {"pattern": "問いの表", "path": "/x/作り物のコード"})),
]


@pytest.mark.parametrize("name,row", FAKE_TRACES, ids=[c[0] for c in FAKE_TRACES])
def test_引いた跡は入力にその字を含むだけの呼び出しで数えない(env, tmp_path, name, row):
    lookup(env, tmp_path, [LOOKUP_TOOL, {"tool": "Grep", "input": {"path": "問いの表"}}])
    why = deny_reason(env, ask_with(log(tmp_path, row)))
    assert "引いた跡が会話ログに無い" in why, why


def test_引いた跡は道具の名と挙げた入力の欄が当たれば数える(env, tmp_path):
    lookup(env, tmp_path, [LOOKUP_TOOL, {"tool": "Grep", "input": {"path": "問いの表"}}])
    assert deny_reason(env, ask_with(log(tmp_path, use("Grep", {"pattern": "会議", "path": "/x/問いの表.md"})))) == ""
    assert deny_reason(env, ask_with(log(tmp_path, use(LOOKUP_TOOL, {"q": "会議"}), name="b.jsonl"))) == ""


def test_引き継ぎの跡は命令の字に送る道具の名を含むだけでは数えない(env, tmp_path):
    tpath = over_log(tmp_path, 300_000, use("Bash", {"command": "grep -rn send_message create_session plugins/"}))
    assert "まだ引き継いでいない" in stop_hook(env, tpath)


def test_組み込みの窓へ送る道具は引き継ぎの跡に数える(env, tmp_path):
    tpath = over_log(tmp_path, 300_000, use("SendMessage", {"to": "作り物の窓", "message": "作り物の引き継ぎ"}))
    assert stop_hook(env, tpath) == ""


# ── 2. 頼みの境は頼みの印で切る（hook の差し戻しの行は新しい頼みでない）──
FEEDBACK = "Stop hook feedback:\n[guard] 作り物の差し戻し"
SAME_REQUEST = [
    ("差し戻しが同じ頼みの印の user 行で残る版", owner(FEEDBACK, "u2", "p1")),
    ("差し戻しが頼みの印の無い user 行で残る版", owner(FEEDBACK, "u2")),
]


@pytest.mark.parametrize("name,row", SAME_REQUEST, ids=[c[0] for c in SAME_REQUEST])
def test_hookの差し戻しの行は頼みの境に数えない(env, tmp_path, name, row):
    lookup(env, tmp_path, [LOOKUP_TOOL])
    tpath = log(tmp_path, use(LOOKUP_TOOL, {"q": "会議"}), row)
    assert deny_reason(env, ask_with(tpath)) == ""


def test_頼みの印が替わった人の行は新しい頼みとして引き直させる(env, tmp_path):
    lookup(env, tmp_path, [LOOKUP_TOOL])
    tpath = log(tmp_path, use(LOOKUP_TOOL, {"q": "会議"}), owner("次の作り物の頼み", "u2", "p2"))
    assert "引いた跡が会話ログに無い" in deny_reason(env, ask_with(tpath))


def test_session_watchの頼みの境もhookの差し戻しの行を数えない():
    spec = importlib.util.spec_from_file_location("sw_trace", ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py")
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    for _, row in SAME_REQUEST:
        assert not G.is_owner_row(row) and not sw.is_owner_text(row)
    assert G.is_owner_row(owner("作り物の頼み", "u1")) and sw.is_owner_text(owner("作り物の頼み", "u1"))


# ── 3. 引く先の無い repo の窓を止めない（起動の時に照らせていない事を知らせる）──
def test_引く先の無いrepoでは画面を止めず起動の時に知らせる(env, tmp_path):
    tpath = log(tmp_path)
    assert deny_reason(env, ask_with(tpath)) == "" and deny_reason(env, ask_with(tpath, sid="s2")) == ""
    assert hook(env, "start", {"session_id": "s1"}) == {}, "値の表そのものが無い repo には知らせない"
    values(env, tmp_path, {"guard": {"context_limit": 300000}})
    assert deny_reason(env, ask_with(tpath, sid="s3")) == ""
    note = hook(env, "start", {"session_id": "s1"}).get("additionalContext", "")
    assert "照らしていない" in note and "guard.ask_prior_lookup" in note, note


def test_確認ページの前の答えを引く命令を引く先に使う(env, tmp_path):
    values(env, tmp_path, {"docs-kit": {"qa-html": {"prior_check_cmd": "python3 tools/作り物の引く道具.py"}}})
    tpath = log(tmp_path, use("Read", {"file_path": "/x/a"}))
    assert deny_reason(env, ask_with(tpath)) and deny_reason(env, ask_with(tpath)), "引く先が在れば上限まで止める"
    for i, cmd in enumerate(["python3 tools/作り物の引く道具.py < q.json", "node /x/qa-html/check.mjs p.html --run-prior"]):
        assert deny_reason(env, ask_with(log(tmp_path, use("Bash", {"command": cmd}), name="r%d.jsonl" % i))) == ""
    assert hook(env, "start", {"session_id": "s1"}).get("additionalContext", "").find("照らしていない") < 0


# ── 4. 値の表の壊れた形は黙って通さず名指す ──
def test_引く先の壊れた形は数えずに止めて名指す(env, tmp_path):
    lookup(env, tmp_path, ["(", LOOKUP_TOOL])
    why = deny_reason(env, ask_with(log(tmp_path)))
    assert "壊れた形" in why and '"("' in why, why
    lookup(env, tmp_path, ["("])
    assert "壊れた形" in deny_reason(env, ask_with(log(tmp_path), sid="s2")), "全部壊れていても通さない"
    lookup(env, tmp_path, ['"q": "会議"'])
    assert "道具の名に当たらない形" in deny_reason(env, ask_with(log(tmp_path), sid="s3")), "入力の JSON に当てる古い形"


def test_引き継ぎの跡の壊れた形は数えずに差し戻して名指す(env, tmp_path):
    values(env, tmp_path, {"guard": {"context_handoff": ["("]}})
    why = stop_hook(env, over_log(tmp_path, 300_000, use("mcp__x__send_message", {"message": "作り物"})))
    assert "壊れた形" in why and '"("' in why, why


def test_起動の時に値の表の読めない値を名指す(env, tmp_path):
    values(env, tmp_path, {"guard": {"ask_prior_lookup": [{"tool": "("}], "context_handoff": "作り物",
                                     "ask_prior_exempt": ["["]}})
    note = hook(env, "start", {"session_id": "s1"}).get("additionalContext", "")
    for want in ("guard.ask_prior_lookup", "guard.context_handoff: 型が違う", "guard.ask_prior_exempt: 正規表現として読めない"):
        assert want in note, (want, note)
    values(env, tmp_path, {"guard": {"irreversible_bash_extra": [{"pattern": "(", "why": "作り物"}]}})
    assert "guard.irreversible_bash_extra" in hook(env, "start", {"session_id": "s1"}).get("additionalContext", "")


def test_外す形の壊れた正規表現1本で見張りごと黙って通らない(env, tmp_path):
    lookup(env, tmp_path, [LOOKUP_TOOL])
    values(env, tmp_path, {"guard": {"ask_prior_lookup": [LOOKUP_TOOL], "ask_prior_exempt": ["[", "終わりましたか"]}})
    assert "引いた跡が会話ログに無い" in deny_reason(env, ask_with(log(tmp_path)))


NOT_REGEX = {"unattended_env", "paid_markers_extra", "ask_topic_stopwords_extra"}


def test_値の表の並びの鍵は全部壊れの名指しの分けに載る():
    lists = {k for k, v in G.DEFAULTS.items() if isinstance(v, list)}
    kinds = [set(G.REGEX_LIST_KEYS), set(G.MATCHER_KEYS), set(G.PATTERN_DICT_KEYS)]
    assert lists - NOT_REGEX == set().union(*kinds)
    assert sum(len(k) for k in kinds) == len(set().union(*kinds)), "1 つの鍵は 1 つの分けだけ"


def test_既定の引き継ぎの跡の形は全部読める():
    ok, bad = G.tool_matchers(G.DEFAULTS, "context_handoff")
    assert not bad and len(ok) == len(G.DEFAULTS["context_handoff"])
