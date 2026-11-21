"""会話ログ・hook の入力・窓の環境の値の意味を、実物（会話ログの見本・Claude Code 本体の判定）と公式の文書で照らす試験。

前の形: 見張りがそれぞれ値の意味を前提にし（isMeta の無い user 行＝人の行・path の /subagents/＝助手の中・道具の名＝
クラウドの窓・origin.kind の person＝人・promptSource＝別の窓の記録）、試験も作り物の行だけで照らしていた。
実物では、別の窓が立てた窓の最初の行は isMeta の無い user 行（origin.kind が task-notification）で、人の行と数えられた。
今の形: 読み方は guard_common の 1 か所（確かめた物は BASIS）に置き、見張りはそこを呼ぶ。
"""
import json
import sys
from pathlib import Path

import pytest

from test_guard import env, hook, post_tool, write_log  # noqa: F401  env は fixture
from test_session_watch import sw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
import guard_common as G  # noqa: E402
import irreversible as IR  # noqa: E402

REAL = Path(__file__).resolve().parent / "transcript_real" / "cloud_child_seeded.jsonl"


def real_rows():
    return [json.loads(ln) for ln in REAL.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_実物_別の窓が立てた窓の最初の行は人の行でない():
    seed = real_rows()[0]
    assert G.is_prompt_row(seed)
    assert not G.is_owner_row(seed)
    assert G.seeded_by_record(seed)
    assert G.is_child_log(str(REAL))


def test_実物_道具の返りと助手でない返事の行():
    rows = real_rows()
    assert not any(G.is_prompt_row(r) for r in rows[1:])
    assert [G.main_assistant_row(r) for r in rows if r.get("type") == "assistant"] == [True, True]


def test_実物_会話ログだけを読んでもクラウドの窓と分かる():
    log = sw.Log(real_rows())
    assert log.cloud
    assert log.first_seeded and sw.kind_of(log.first_prompt, log.first_seeded) == sw.AI


def test_実物_仕組みの記録の窓の_URL_と環境の_id_の読み替えが合う():
    """cloud-environments の文書: CLAUDE_CODE_REMOTE_SESSION_ID の cse_ を session_ に替える。実物の会話ログでも、仕組みの
    記録（remote_session_change）の URL の id は、窓の環境の id の頭を替えた物と同じだった。"""
    att = real_rows()[1]["attachment"]
    assert att["type"] == "remote_session_change"
    sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
    import pr_text as PT
    assert PT.poster_id({"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_EXAMPLE01"}) == att["url"].rsplit("/", 1)[1]


def test_実物_commit_の_Claude_Session_は仕組みが付けず_AI_が写す行():
    """仕組みの記録は commit を自分で作らない（managedCommit が偽）＝`Claude-Session:` は AI が指示を写して書く行（写し）。"""
    att = real_rows()[1]["attachment"]
    assert att["managedCommit"] is False and "Claude-Session: " in att["commit"]


# Claude Code 本体の人の行の判定（BASIS「人が打った行」）と同じ答えを出すか。
OWNER_CASES = [
    ({}, True),
    ({"origin": {"kind": "human"}}, True),
    ({"origin": {"kind": "task-notification"}}, False),
    ({"origin": {"kind": "peer"}}, False),
    ({"origin": {"kind": "channel"}}, False),
    ({"origin": {"kind": "remote"}}, False),
    ({"origin": {"kind": "person"}}, False),          # 本体では画面の部品の印で、人の行の印でない
    ({"isMeta": True}, False),
    ({"isCompactSummary": True}, False),
    ({"toolUseResult": {}}, False),
]


@pytest.mark.parametrize("extra,want", OWNER_CASES)
def test_人の行の読み方は本体の判定と同じ(extra, want):
    row = {"type": "user", "message": {"content": "作り物の頼み"}, **extra}
    assert G.is_owner_row(row) is want


def test_注入_離席の後の知らせの行で席に戻ったと読まない(tmp_path):
    """前の形: 離席の印より後の知らせ・別の窓からの送りの行を人の行と数え、離席中の戻せない操作の止めが外れた。"""
    log = tmp_path / "t.jsonl"
    rows = [{"type": "user", "timestamp": "2026-11-20T01:00:00Z", "origin": {"kind": "task-notification"},
             "message": {"content": "裏の作業が終わった"}}]
    log.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert IR.owner_returned_since(str(log), "2026-11-20T00:00:00Z") is False
    rows.append({"type": "user", "timestamp": "2026-11-20T02:00:00Z", "message": {"content": "戻った"}})
    log.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert IR.owner_returned_since(str(log), "2026-11-20T00:00:00Z") is True


def test_注入_助手の中は入力の_agent_id_で見分ける(env, tmp_path):
    """公式の hooks の文書: 助手の中の hook の入力に agent_id。path に /subagents/ が無くても黙り、在っても agent_id が
    無ければ本体として見る（前の形: path の字だけで決めた）。"""
    big = [{"type": "assistant", "message": {"usage": {"input_tokens": 999_999}}}]
    main = tmp_path / "main.jsonl"
    main.write_text(json.dumps(big[0]) + "\n", encoding="utf-8")
    assert G.in_subagent({"agent_id": "a1"}) and not G.in_subagent({}) and not G.in_subagent(None)
    assert hook(env, "post", {**post_tool(str(main)), "agent_id": "a1"}) == {}
    assert hook(env, "post", post_tool(str(main)))["additionalContext"]


def test_クラウドの窓は環境の_CLAUDE_CODE_REMOTE_で読む():
    assert G.is_cloud({"CLAUDE_CODE_REMOTE": "true"}) and not G.is_cloud({}) and not G.is_cloud({"CLAUDE_CODE_REMOTE": "1"})


def test_読み方の正本は確かめた物を名指す():
    for key in ("人が打った行", "別の窓・仕組みから来た行", "助手の中の hook", "クラウドの窓", "窓の id", "Stop の入力",
                "文脈の大きさ", "repo の根"):
        assert G.BASIS.get(key), key


def test_見張りは値の意味を自分で決めない():
    """会話ログ・入力の値の意味を見張りの file ごとに書かない（/subagents/ の path・origin の印の表・promptSource）。"""
    bad = []
    for p in list((ROOT / "plugins").rglob("*.py")):
        if p.name == "guard_common.py":
            continue
        text = p.read_text(encoding="utf-8")
        for needle in ('"/subagents/"', "HUMAN_ORIGINS =", 'get("promptSource")', 'get("origin")'):
            if needle in text:
                bad.append((p.name, needle))
    assert bad == []



def test_注入_助手の行が本体の会話ログに混ざっても文脈の大きさに数えない(env, tmp_path):
    """本体の行は isSidechain が偽（実物）。助手の行（isSidechain が真）の usage を今の文脈の大きさと取り違えない。"""
    tpath = write_log(tmp_path / "main.jsonl", [
        {"type": "assistant", "isSidechain": False, "message": {"usage": {"input_tokens": 1000}}},
        {"type": "assistant", "isSidechain": True, "message": {"usage": {"input_tokens": 999_999}}}])
    assert hook(env, "post", post_tool(tpath)) == {}


@pytest.mark.parametrize("kind", ["task-notification", "peer"])
def test_注入_別の窓_知らせから来た頼みでも前の頼みの引いた跡で問いを通さない(env, tmp_path, kind):
    """頼みの区切りは頼みの行（人の行に限らない）。前の形: 人の行だけで区切り、別の窓・知らせから来た次の頼みでも
    前の頼みで引いた跡が残って選択肢の画面が通った（レビューで見つかった形）。"""
    from test_guard_prior_ask import ask_with, lookup_values, owner, use
    lookup_values(env, tmp_path)
    nxt = {**owner("次の作り物の頼み", "u2"), "origin": {"kind": kind}}
    tpath = write_log(tmp_path / "p.jsonl", [owner("作り物の頼み", "u1"), use("作り物の記録を引く道具", {"q": "会議"}), nxt])
    from test_guard import deny_reason
    assert deny_reason(env, ask_with(tpath))


def test_会話の要約の行は新しい頼みにしない(env, tmp_path):
    """要約の行（isCompactSummary）は前の頼みの続き。要約の前に引いた跡で、同じ頼みの問いは通る。"""
    from test_guard_prior_ask import ask_with, lookup_values, owner, use
    lookup_values(env, tmp_path)
    summary = {**owner("これまでの要約", "u2"), "isCompactSummary": True}
    tpath = write_log(tmp_path / "p.jsonl", [owner("作り物の頼み", "u1"), use("作り物の記録を引く道具", {"q": "会議"}), summary])
    from test_guard import deny_reason
    assert deny_reason(env, ask_with(tpath)) == ""
