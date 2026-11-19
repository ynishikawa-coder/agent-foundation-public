"""guard の context_size の Stop: 文脈の目安を越えた後、引き継がずに締める AI だけを差し戻すか（注入の試験）。"""
import json
import subprocess
import sys

import pytest

from test_guard import GUARD, env, write_log  # noqa: F401  （env は fixture）


def use(name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


# ── context_size の Stop（目安を越えて引き継がずに締める AI を差し戻す）──
def over_log(tmp_path, tokens, *after, first="作り物の頼み", name="o.jsonl"):
    return write_log(tmp_path / name, [
        {"type": "user", "message": {"content": first}},
        {"type": "assistant", "message": {"usage": {"input_tokens": 10, "cache_read_input_tokens": tokens - 10},
                                          "content": []}},
        *after])


def stop_hook(env, tpath, active=False, sid="s1"):
    p = subprocess.run([sys.executable, str(GUARD), "stop"],
                       input=json.dumps({"session_id": sid, "transcript_path": tpath, "stop_hook_active": active},
                                        ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout) if p.stdout.strip() else {}
    return out.get("reason", "") if out.get("decision") == "block" else ""


def test_context_stop_目安を越えて引き継がずに締めると差し戻す(env, tmp_path):
    why = stop_hook(env, over_log(tmp_path, 300_000, use("Read", {"file_path": "/x/a"})))
    assert "まだ引き継いでいない" in why and "後継の窓を立てて" in why, why
    assert "guard.context_handoff" in why and "guard.context_stop_max" in why


def test_context_stop_子の窓には返し先へ送って止まる直し方を返す(env, tmp_path):
    why = stop_hook(env, over_log(tmp_path, 400_000, first="あなたは書く窓です（親窓 session_ABC123 の子）。"))
    assert "返し先の窓へ送り、止まる" in why, why


HANDOFFS = [
    ("後継の窓を立てた", use("mcp__claude-code-remote__create_session", {"prompt": "作り物の引き継ぎ"})),
    ("親の窓へ送った", use("mcp__claude-code-remote__send_message", {"message": "作り物の返し"})),
    ("引き継ぎの file を書いた", use("Write", {"file_path": "/x/作業場/引き継ぎ.md",
                                    "content": "## 済んだ事\nA\n## 残り\nB\n## 次の一手\nC\n## 返し先\nオーナー"})),
]


@pytest.mark.parametrize("name,row", HANDOFFS, ids=[c[0] for c in HANDOFFS])
def test_context_stop_引き継いだ窓と目安の手前の窓は差し戻さない(env, tmp_path, name, row):
    assert stop_hook(env, over_log(tmp_path, 300_000, row)) == ""
    assert stop_hook(env, over_log(tmp_path, 299_999, name="u.jsonl")) == ""


def test_context_stop_目安を越える前の引き継ぎらしい呼び出しは数えない(env, tmp_path):
    tpath = write_log(tmp_path / "b.jsonl", [
        {"type": "user", "message": {"content": "作り物の頼み"}},
        use("mcp__claude-code-remote__send_message", {"message": "途中の返し"}),
        {"type": "assistant", "message": {"usage": {"input_tokens": 300_000}, "content": []}}])
    assert stop_hook(env, tpath)


def test_context_stop_まとめ直して縮んだ後は差し戻さない(env, tmp_path):
    tpath = over_log(tmp_path, 300_000, {"type": "assistant", "message": {"usage": {"input_tokens": 20_000}, "content": []}})
    assert stop_hook(env, tpath) == ""


def test_context_stop_差し戻しは同じターンで上限までで新しい締めでは数え直す(env, tmp_path):
    tpath = over_log(tmp_path, 300_000)
    assert stop_hook(env, tpath) and stop_hook(env, tpath, active=True)
    assert stop_hook(env, tpath, active=True) == ""          # 3 回目は通して届ける（回り続けない）
    assert stop_hook(env, tpath, active=False)               # 新しい締めでは数え直す


def test_context_stop_値の表で引き継ぎの形を足せ差し戻しを外せる(env, tmp_path):
    tpath = over_log(tmp_path, 300_000, use("作り物の引き継ぎ道具", {}))
    assert stop_hook(env, tpath)
    table = tmp_path / "values.json"
    env["SKILL_VALUES"] = str(table)
    table.write_text(json.dumps({"guard": {"context_handoff": ["作り物の引き継ぎ道具"]}}, ensure_ascii=False), encoding="utf-8")
    assert stop_hook(env, tpath) == ""
    table.write_text(json.dumps({"guard": {"context_stop_max": 0}}), encoding="utf-8")
    assert stop_hook(env, over_log(tmp_path, 300_000, name="z.jsonl")) == ""


def test_context_stop_助手の中と壊れた会話ログでは黙る(env, tmp_path):
    d = tmp_path / "subagents"
    d.mkdir()
    assert stop_hook(env, over_log(d, 999_999)) == ""
    assert stop_hook(env, str(tmp_path / "無い.jsonl")) == ""
