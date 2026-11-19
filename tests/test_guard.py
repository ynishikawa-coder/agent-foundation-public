"""守りの hook（plugins/guard）が、止めるべき入力で止まり、通すべき入力で通るかを見る。入力は全部作り物。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "guard"
GUARD = PLUGIN / "scripts" / "guard.py"


@pytest.fixture
def env(tmp_path):
    """試験ごとに一時の箱・台帳の置き場・repo の根を分ける（実の印を汚さない）。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    (tmp_path / "scratch").mkdir()
    e = {k: v for k, v in os.environ.items() if not k.startswith(("AF_", "_AF_", "SKILL_VALUES", "CLAUDE_PROJECT_DIR"))}
    e.update({"AF_GUARD_TMP": str(tmp_path / "tmp"), "AF_GUARD_STATE": str(tmp_path / "state"),
              "CLAUDE_PROJECT_DIR": str(proj), "PYTHONDONTWRITEBYTECODE": "1",
              "TMPDIR": str(tmp_path / "scratch")})     # 作業場を tmp_path の下の 1 か所に絞る（repo は作業場の外）
    return e


def hook(env, event, payload):
    p = subprocess.run([sys.executable, env.get("_AF_TEST_GUARD") or str(GUARD), event], input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    out = p.stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else {}


def denied(env, payload):
    return hook(env, "pre", payload).get("permissionDecision") == "deny"


def write_log(path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return str(path)


def ask_result(answered=False, sid="s1", tpath=""):
    q = {"question": "作り物の置き場を A と B のどちらにしますか", "header": "置き場",
         "options": [{"label": "A（推奨）", "description": "作り物の A"}, {"label": "B", "description": "作り物の B"}]}
    resp = {"questions": [q], "answers": {q["question"]: "A（推奨）"} if answered else {}}
    return {"tool_name": "AskUserQuestion", "session_id": sid, "transcript_path": tpath, "tool_response": resp}


def bash(cmd, sid="s1", cwd="", tpath=""):
    return {"tool_name": "Bash", "session_id": sid, "cwd": cwd, "transcript_path": tpath, "tool_input": {"command": cmd}}


# ── hook の配線 ──
def test_hooks_json_が4つの出来事で入口を回す():
    data = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    want = {"PreToolUse": "pre", "PostToolUse": "post", "SessionStart": "start", "Stop": "stop"}
    assert set(data) == set(want)
    for event, arg in want.items():
        cmd = data[event][0]["hooks"][0]["command"]
        assert "${CLAUDE_PLUGIN_ROOT}/scripts/guard.py" in cmd and cmd.endswith(" " + arg)


def test_壊れた入力では何も出さず通す(env):
    for event in ("pre", "post", "start", "stop"):
        p = subprocess.run([sys.executable, str(GUARD), event], input="こわれた", capture_output=True, text=True, env=env)
        assert p.returncode == 0 and p.stdout.strip() == ""


# ── paid_upstream（試験から有料の上流）──
PAID_CASES = [
    ("試験の file に本物の鍵", {"tool_name": "Write", "tool_input": {
        "file_path": "/x/e2e/walk.mjs", "content": "const key = process.env.ANTHROPIC_API_KEY;"}}, True),
    ("関所の印がある", {"tool_name": "Write", "tool_input": {
        "file_path": "/x/e2e/walk.mjs", "content": "// PAID_UPSTREAM_GUARD\nprocess.env.ANTHROPIC_API_KEY"}}, False),
    ("試験でない file", {"tool_name": "Write", "tool_input": {
        "file_path": "/x/src/api/extract.mjs", "content": "process.env.ANTHROPIC_API_KEY"}}, False),
    ("試験だが有料の印なし", {"tool_name": "Write", "tool_input": {
        "file_path": "/x/tests/test_foo.py", "content": "assert 1 == 1"}}, False),
    ("公式のエンドポイントへ直に", {"tool_name": "Edit", "tool_input": {
        "file_path": "/x/__tests__/a.spec.ts", "new_string": 'fetch("https://api.anthropic.com/v1/messages")'}}, True),
    ("MultiEdit の中に潜む", {"tool_name": "MultiEdit", "tool_input": {
        "file_path": "/x/e2e/b.test.js", "edits": [{"new_string": "ok"}, {"new_string": "OPENAI_API_KEY"}]}}, True),
    ("読むだけは止めない", {"tool_name": "Read", "tool_input": {"file_path": "/x/e2e/walk.mjs"}}, False),
    ("python の試験の名", {"tool_name": "Write", "tool_input": {
        "file_path": "/x/pkg/test_extract.py", "content": 'os.environ["GEMINI_API_KEY"]'}}, True),
    ("入力が壊れていても止めない", {"tool_name": "Write", "tool_input": "こわれた"}, False),
]


@pytest.mark.parametrize("name,payload,want", PAID_CASES, ids=[c[0] for c in PAID_CASES])
def test_試験から有料の上流へつなぐ線を止める(env, name, payload, want):
    assert denied(env, payload) is want


def test_有料の上流を止めた文は根治の入口を指す(env):
    """止めた file の直し方だけを並べる古い形（線を書いた原因を見させない）に戻すと赤。"""
    assert "細目 §3「まず構造を疑う」" in deny_reason(env, PAID_CASES[0][1])


def test_有料の印は値の表で足せる(env, tmp_path):
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"guard": {"paid_markers_extra": ["api.example-paid.test"]}}), encoding="utf-8")
    env["SKILL_VALUES"] = str(table)
    payload = {"tool_name": "Write", "tool_input": {"file_path": "/x/tests/test_a.py", "content": "api.example-paid.test"}}
    assert denied(env, payload)


# ── unanswered（未回答の台帳）と irreversible（離席中の戻せない操作）──
DROP = "psql -c 'DROP TABLE t'"


def test_在席中は戻せない操作も止めない(env):
    assert not denied(env, bash(DROP))


def test_答えの無い問いは台帳に積まれ隣に1行鳴り次の窓で出し直させる(env):
    note = hook(env, "post", ask_result()).get("additionalContext", "")
    assert "答えのないまま閉じました（1 件）" in note
    again = hook(env, "start", {"session_id": "s2"}).get("additionalContext", "")
    assert "作り物の置き場を A と B のどちらにしますか" in again and "A（推奨）" in again


def test_出し直させる文は根治の入口を指す(env):
    """答えの無い問いを出し直させるだけの古い形（原因を見させない）に戻すと赤。"""
    hook(env, "post", ask_result())
    again = hook(env, "start", {"session_id": "s2"}).get("additionalContext", "")
    assert "細目 §3「まず構造を疑う」" in again


def test_答えが返れば台帳から降りて冒頭に出ない(env):
    hook(env, "post", ask_result())
    assert hook(env, "post", ask_result(answered=True, sid="s2")) == {}
    assert hook(env, "start", {"session_id": "s3"}) == {}


def test_助手の中の問いは台帳に積まない(env):
    assert hook(env, "post", ask_result(tpath="/x/subagents/a.jsonl")) == {}
    assert hook(env, "start", {"session_id": "s2"}) == {}


@pytest.mark.parametrize("cmd", [DROP, "supabase db reset", "ls | xargs rm -rf", "rm -rf $HOME/x"])
def test_離席中は戻せない操作を止める(env, cmd):
    hook(env, "post", ask_result())
    assert denied(env, bash(cmd))


@pytest.mark.parametrize("cmd", [
    "ls -la", "git status", "git branch -D old",
    # 他の守り（permissions.deny）が常に止める物は重ねない
    "vercel deploy --prod", "git push --force origin x", "gh release create v9",
])
def test_離席中でも戻せる操作と他が止める操作は通す(env, cmd):
    hook(env, "post", ask_result())
    assert not denied(env, bash(cmd))


def test_離席中はメールを送る道具も止め別の窓は止めない(env):
    hook(env, "post", ask_result())
    assert denied(env, {"tool_name": "mcp__mail-x__send_email", "session_id": "s1", "tool_input": {}})
    assert not denied(env, {"tool_name": "mcp__mail-x__send_email", "session_id": "other", "tool_input": {}})


def test_離席の止めの文は根治の入口を指す(env):
    """同じ問いを出し直させるだけの古い形に戻すと赤。"""
    hook(env, "post", ask_result())
    assert "細目 §3「まず構造を疑う」" in deny_reason(env, bash(DROP))


def test_答えが返ると離席の止めが解ける(env):
    hook(env, "post", ask_result())
    hook(env, "post", ask_result(answered=True))
    assert not denied(env, bash(DROP))


def test_オーナーが打てば離席の止めが解ける(env, tmp_path):
    hook(env, "post", ask_result())
    later = "2999-01-01T00:00:00.000Z"
    tpath = write_log(tmp_path / "t.jsonl", [{"type": "user", "timestamp": later, "message": {"content": "戻りました"}}])
    assert not denied(env, bash(DROP, tpath=tpath))
    assert not denied(env, bash(DROP))     # 窓は閉じた


def test_離席の後に人の行が無ければ止めたまま(env, tmp_path):
    hook(env, "post", ask_result())
    old = "2000-01-01T09:00:00+09:00"
    tpath = write_log(tmp_path / "t.jsonl", [
        {"type": "user", "timestamp": old, "message": {"content": "前の頼み"}},
        {"type": "user", "timestamp": "2999-01-01T00:00:00Z", "toolUseResult": {}, "message": {"content": "返り"}}])
    assert denied(env, bash(DROP, tpath=tpath))


def test_人のいない窓の印があれば離席の止めも台帳も働かない(env):
    env["AF_UNATTENDED"] = "1"
    assert hook(env, "post", ask_result()) == {}
    assert not denied(env, bash(DROP))


def test_戻せない操作は値の表で足せる(env, tmp_path):
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"guard": {"irreversible_bash_extra": [
        {"pattern": r"\bmy-ship\s+--live\b", "why": "本番への出荷（作り物）"}]}}), encoding="utf-8")
    env["SKILL_VALUES"] = str(table)
    hook(env, "post", ask_result())
    assert denied(env, bash("my-ship --live"))


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "build").mkdir(parents=True)
    (r / "build" / "a.txt").write_text("a", encoding="utf-8")
    g = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    g.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})
    for c in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(r), *c], check=True, env=g, capture_output=True)
    return r


def test_git_で全部戻せる削除は離席中でも通す(env, repo):
    hook(env, "post", ask_result())
    assert not denied(env, bash("rm -rf build", cwd=str(repo)))
    assert not denied(env, bash("cd build && rm -rf *.txt", cwd=str(repo)))
    assert not denied(env, bash("rm -rf no-such-dir", cwd=str(repo)))      # 消す物が無い


def test_git_に無い物が混ざる削除は離席中に止める(env, repo):
    hook(env, "post", ask_result())
    (repo / "build" / "new.txt").write_text("未記録", encoding="utf-8")
    assert denied(env, bash("rm -rf build", cwd=str(repo)))
    assert denied(env, bash("cd build && rm -rf *", cwd=str(repo)))
    assert denied(env, bash("rm -rf " + str(repo), cwd=str(repo)))         # repo ごと


def test_rm_より前の命令が消す先を変える形は離席中に止める(env, repo):
    hook(env, "post", ask_result())
    (repo / "keep").write_text("未記録", encoding="utf-8")
    assert denied(env, bash("mv keep gone && rm -rf gone", cwd=str(repo)))
    assert not denied(env, bash("rm -rf build && echo 済み", cwd=str(repo)))   # rm の後ろは見ない


def test_作業場と変更の無い作業部屋の掃除は離席中でも通す(env, repo, tmp_path):
    hook(env, "post", ask_result())
    scratch = tmp_path / "scratch" / "pad"
    (scratch / "out").mkdir(parents=True)
    (scratch / "out" / "x.log").write_text("一時", encoding="utf-8")
    assert not denied(env, bash("cd %s && rm -rf out *.log" % scratch, cwd=str(repo)))
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(wt)], check=True, capture_output=True)
    assert not denied(env, bash("rm -rf " + str(wt), cwd=str(repo)))
    (wt / "未記録.txt").write_text("x", encoding="utf-8")
    assert denied(env, bash("rm -rf " + str(wt), cwd=str(repo)))


# ── context_size（文脈の量）──
def usage_log(tmp_path, tokens, first="作り物の頼み", origin=None):
    head = {"type": "user", "message": {"content": first}}
    if origin:
        head["origin"] = {"kind": origin}       # 頼みの行の記録（人が打ったか・別の窓から来たか）
    return write_log(tmp_path / "ctx.jsonl", [
        head,
        {"type": "assistant", "message": {"usage": {"input_tokens": 10, "cache_read_input_tokens": tokens - 10,
                                                    "cache_creation_input_tokens": 0}, "content": []}}])


def post_tool(tpath, sid="s1"):
    return {"tool_name": "Read", "session_id": sid, "transcript_path": tpath, "tool_response": {}}


def test_文脈が目安の手前なら黙る(env, tmp_path):
    assert hook(env, "post", post_tool(usage_log(tmp_path, 299_999))) == {}


def test_文脈が目安を越えた最初の1回だけ知らせる(env, tmp_path):
    tpath = usage_log(tmp_path, 300_000)
    note = hook(env, "post", post_tool(tpath)).get("additionalContext", "")
    assert "<context-watchdog>" in note and "後継の窓へ替えて" in note
    assert hook(env, "post", post_tool(tpath)) == {}


def test_子の窓には止まる側の知らせを出す(env, tmp_path):
    tpath = usage_log(tmp_path, 400_000, first="あなたは書く窓です（親窓 session_ABC123 の子）。", origin="task-notification")
    assert "引き継ぎを書いて止まって" in hook(env, "post", post_tool(tpath))["additionalContext"]


def test_文脈の目安は値の表で変えられる(env, tmp_path):
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"guard": {"context_limit": 1000}}), encoding="utf-8")
    env["SKILL_VALUES"] = str(table)
    assert "1,000 token" in hook(env, "post", post_tool(usage_log(tmp_path, 1500)))["additionalContext"]


def test_助手の中では文脈を見ない(env, tmp_path):
    d = tmp_path / "subagents"
    d.mkdir()
    tpath = write_log(d / "a.jsonl", [{"type": "assistant", "message": {"usage": {"input_tokens": 999_999}}}])
    assert hook(env, "post", post_tool(tpath)) == {}


def _age_ledger(tmp_path, keys=None):
    ledger = next((tmp_path / "state").rglob("unanswered-questions.json"))
    data = json.loads(ledger.read_text(encoding="utf-8"))
    for p in data["pending"]:
        if keys is None or p["key"] in keys:
            p["last_seen_at"] = "2000-01-01T00:00:00.000000Z"
    ledger.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def test_寿命を過ぎた問いは黙って消さず_一度知らせてから降ろす(env, tmp_path):
    hook(env, "post", ask_result())
    _age_ledger(tmp_path)
    note = hook(env, "start", {"session_id": "s2"}).get("additionalContext", "")
    assert "時間を過ぎたので、台帳から降ろします" in note and "作り物の置き場を A と B のどちらにしますか" in note
    assert "前の窓で答えのないまま閉じた問い" not in note          # 出し直しの頼みには入れない
    assert "答えが返らなかった原因" in note                          # 寿命切れだけでも根治の入口を指す
    assert hook(env, "start", {"session_id": "s3"}) == {}           # 知らせたのは一度だけ
    ledger = next((tmp_path / "state").rglob("unanswered-questions.json"))
    assert [e["question"] for e in json.loads(ledger.read_text(encoding="utf-8"))["expired_recent"]] == \
        ["作り物の置き場を A と B のどちらにしますか"]


def test_寿命を過ぎた問いも次の問いを積む時には消えない(env, tmp_path):
    hook(env, "post", ask_result())
    _age_ledger(tmp_path)
    hook(env, "post", many_questions(1, sid="s2", start=9))        # 別の問いを積む＝台帳を書き直す
    note = hook(env, "start", {"session_id": "s3"})["additionalContext"]
    assert "作り物の置き場を A と B のどちらにしますか" in note and "作り物の問い 9 番" in note
    assert note.index("台帳から降ろします") < note.index("前の窓で答えのないまま閉じた問い")   # 切られても先に読まれる


def test_人のいない窓だけが続いても寿命切れは台帳に残らず_次の人のいる窓で一度知らせる(env, tmp_path):
    hook(env, "post", ask_result())
    _age_ledger(tmp_path)
    env["AF_UNATTENDED"] = "1"
    assert hook(env, "start", {"session_id": "n1"}) == {}            # 人のいない窓は知らせない
    ledger = next((tmp_path / "state").rglob("unanswered-questions.json"))
    data = json.loads(ledger.read_text(encoding="utf-8"))
    assert data["pending"] == []                                      # 台帳には残らない
    assert [e["notified"] for e in data["expired_recent"]] == [False]
    assert "人のいない窓が控えへ移した" in run_cli(env, "list").stdout   # 一覧にも印つきで出る
    del env["AF_UNATTENDED"]
    note = hook(env, "start", {"session_id": "s2"}).get("additionalContext", "")
    assert "台帳から降ろします" in note and "作り物の置き場を A と B のどちらにしますか" in note
    assert hook(env, "start", {"session_id": "s3"}) == {}           # 知らせたのは一度だけ


def test_人のいない窓は台帳が無ければ作らない(env, tmp_path):
    env["AF_UNATTENDED"] = "1"
    assert hook(env, "start", {"session_id": "n1"}) == {}
    assert not list(tmp_path.rglob("unanswered-questions.json"))


def test_まだ知らせていない控えは上限で黙って落ちない(env, tmp_path):
    hook(env, "post", ask_result())
    ledger = next((tmp_path / "state").rglob("unanswered-questions.json"))
    data = json.loads(ledger.read_text(encoding="utf-8"))
    data["expired_recent"] = [{"key": "k%d" % i, "question": "作り物の古い問い %d" % i, "notified": True,
                               "expired_at": "2000-01-01T00:00:00.000000Z"} for i in range(25)]
    ledger.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _age_ledger(tmp_path)
    env["AF_UNATTENDED"] = "1"
    hook(env, "start", {"session_id": "n1"})
    recent = json.loads(ledger.read_text(encoding="utf-8"))["expired_recent"]
    assert [e["question"] for e in recent if e.get("notified") is False] == ["作り物の置き場を A と B のどちらにしますか"]


def test_文面の無い行も黙って残さず_知らせて降ろす(env, tmp_path):
    hook(env, "post", ask_result())
    ledger = next((tmp_path / "state").rglob("unanswered-questions.json"))
    data = json.loads(ledger.read_text(encoding="utf-8"))
    data["pending"].append({"key": "nokeytext", "last_seen_at": data["pending"][0]["last_seen_at"]})
    data["pending"].append({"last_seen_at": "2000-01-01T00:00:00.000000Z"})          # key も文面も無い
    ledger.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert "[文面が無い" in run_cli(env, "list").stdout
    note = hook(env, "start", {"session_id": "s2"})["additionalContext"]
    assert "文面が無い行・key: nokeytext" in note and "文面が無い行・key: なし" in note
    assert "作り物の置き場を A と B のどちらにしますか" in note       # 生きている問いはそのまま出し直しへ
    left = json.loads(ledger.read_text(encoding="utf-8"))["pending"]
    assert [p["question"] for p in left] == ["作り物の置き場を A と B のどちらにしますか"]


def test_一覧は寿命切れに印を付ける(env, tmp_path):
    hook(env, "post", ask_result())
    assert "[寿命切れ" not in run_cli(env, "list").stdout
    _age_ledger(tmp_path)
    out = run_cli(env, "list").stdout
    assert "[寿命切れ・次の窓の冒頭で知らせて降ろす] 作り物の置き場" in out


def many_questions(n, sid="s1", start=1):
    qs = [{"question": "作り物の問い %d 番はどちらにしますか" % i, "header": "問い%d" % i,
           "options": [{"label": "甲", "description": "作り物"}, {"label": "乙", "description": "作り物"}]}
          for i in range(start, start + n)]
    return {"tool_name": "AskUserQuestion", "session_id": sid, "transcript_path": "",
            "tool_response": {"questions": qs, "answers": {}}}


def test_出し直しは頭の4件で切らず_5件目まで全部渡す(env):
    hook(env, "post", many_questions(4))
    hook(env, "post", many_questions(1, sid="s1b", start=5))        # 4＋1＝5 件（モーダル 1 回の数を 1 つ越える）
    note = hook(env, "start", {"session_id": "s2"})["additionalContext"]
    assert "5 件" in note and "4 問ずつ続けて出す" in note and "下の 5 件を全部" in note
    for i in range(1, 6):
        assert "作り物の問い %d 番はどちらにしますか" % i in note
    assert "次の機会に" not in note


def test_閉じた問いが5つでも隣の1行に全部の文面が載る(env):
    note = hook(env, "post", many_questions(5))["additionalContext"]
    assert "（5 件）" in note and "作り物の問い 5 番" in note


def test_離席の止めは閉じた問いが多い時ほか何件と置き場を出す(env):
    hook(env, "post", many_questions(4))
    why = deny_reason(env, bash(DROP))
    assert "4 件" in why and "ほか 1 件" in why and "unanswered-questions.json" in why


def test_子の窓の問いも台帳に積み離席の止めが働く(env, tmp_path):
    tpath = write_log(tmp_path / "c.jsonl", [{"type": "user", "message": {"content": "あなたは書く窓です（親窓 session_P1 の子）。"}}])
    assert "答えのないまま閉じました" in hook(env, "post", ask_result(tpath=tpath))["additionalContext"]
    assert denied(env, bash(DROP))


def test_作業部屋で積んだ問いも本体の窓の冒頭に出る(env, repo, tmp_path):
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(wt)], check=True, capture_output=True)
    env["CLAUDE_PROJECT_DIR"] = str(wt)
    hook(env, "post", ask_result())
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    assert "作り物の置き場を A と B のどちらにしますか" in hook(env, "start", {"session_id": "s2"})["additionalContext"]


def test_時刻は字でなく時刻で比べる(env, tmp_path):
    """離席の印は UTC（Z）、人の行は +09:00。字で比べると逆になる 2 例。"""
    away = tmp_path / "tmp" / "away"
    away.mkdir(parents=True)
    (away / "s1.json").write_text(json.dumps({"since": "2026-11-11T09:50:00.000000Z", "questions": ["作り物"]}),
                                  encoding="utf-8")
    before = write_log(tmp_path / "b.jsonl", [{"type": "user", "timestamp": "2026-11-11T18:00:00+09:00",
                                               "message": {"content": "離席の前の行"}}])
    assert denied(env, bash(DROP, tpath=before))      # 字では T18 > T09 だが、時刻では前
    after = write_log(tmp_path / "a.jsonl", [{"type": "user", "timestamp": "2026-11-11T19:00:00+09:00",
                                              "message": {"content": "戻りました"}}])
    assert not denied(env, bash(DROP, tpath=after))   # 時刻で後＝戻った


def test_1つの見張りが_import_で壊れても他の見張りは走る(env, tmp_path):
    import shutil
    shutil.copytree(PLUGIN, tmp_path / "plugin")   # 入れた時と同じく lib/ の symlink は実体で写る
    broken = tmp_path / "plugin" / "scripts"
    (broken / "irreversible.py").write_text("raise ImportError('作り物の故障')\n", encoding="utf-8")
    payload = {"tool_name": "Write", "tool_input": {"file_path": "/x/tests/test_a.py", "content": "OPENAI_API_KEY"}}
    p = subprocess.run([sys.executable, str(broken / "guard.py"), "pre"], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    assert json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


# ── qa_page（問いのページを Artifact で出す前の qa-html の検査）──
import importlib.util  # noqa: E402
import shutil  # noqa: E402

needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node が無い（qa-html の検査は node で動く）")
DOCS_KIT_DATA = ROOT / "tests" / "docs_kit"

# 独自の道具で作った問いのページ（作り物）: 型を写さず、<script id="state"> に問いの並び qs を持ち、JS で radio を組む
STATE_PAGE = """<!doctype html><html><body><div id="app"></div>
<script id="state" type="application/json">{"title":"確認","qs":[{"id":"q1","text":"週の起算日はどれですか","options":["日曜","月曜"]}]}</script>
<script>const s=JSON.parse(document.getElementById('state').textContent);
document.getElementById('app').innerHTML=s.qs.map(q=>q.options.map(o=>`<label><input type="radio" name="${q.id}">${o}</label>`).join('')).join('');</script>
</body></html>"""


def filled_qa_page(dest="artifact"):
    """docs-kit の試験の作り物（型を埋めた緑の 1 枚）を借りる。"""
    spec = importlib.util.spec_from_file_location("af_test_docs_kit", ROOT / "tests" / "test_docs_kit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.filled_template(dest)


def without_check(env, tmp_path, ver="v1", docs_kit_ver=None):
    """guard を入れた plugin の形（cache/<市場>/guard/<版>）に写して回す env。docs-kit は docs_kit_ver の版にだけ置く（None なら置かない）。
    hook の入口は _AF_TEST_GUARD（試験の中だけの差し替え・hook の本体は読まない）。"""
    market = tmp_path / "cache" / "market"
    root = market / "guard" / ver
    if not root.exists():
        shutil.copytree(PLUGIN, root)
    if docs_kit_ver:
        shutil.copytree(ROOT / "plugins" / "docs-kit", market / "docs-kit" / docs_kit_ver, dirs_exist_ok=True)
    # 入れた形の市場の取り出し（<plugins>/marketplaces/<市場>）＝outbound が鍵の形の正本 public-guard/guard.py を読む所
    pg = tmp_path / "marketplaces" / "market" / "public-guard"
    if not pg.exists():
        shutil.copytree(ROOT / "public-guard", pg)
    clone_at(pg.parent, ver)  # 市場の取り出しは git で、入った版（cache の dir の名）が歴史に在る
    return dict(env, _AF_TEST_GUARD=str(root / "scripts" / "guard.py"))


def clone_at(clone, ver):
    """作り物の市場の取り出しを git にし、今の中身を版 ver（tag）として持たせる（guard は入った版の中身だけを読む）。"""
    g = lambda *a: subprocess.run(["git", "-C", str(clone), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a],
                                  capture_output=True, text=True)
    if not (clone / ".git").exists():
        g("init", "-q")
        g("add", "-A")
        g("commit", "-qm", "版")
    g("tag", "-f", ver)


def publish(path, cwd="", **extra):
    return {"tool_name": "Artifact", "cwd": cwd, "tool_input": {"file_path": str(path), **extra}}


def deny_reason(env, payload):
    return hook(env, "pre", payload).get("permissionDecisionReason", "")


@needs_node
def test_qa_page_型を写さない独自の問いのページは止まる(env, tmp_path):
    page = tmp_path / "kakunin.html"
    page.write_text(STATE_PAGE, encoding="utf-8")
    why = deny_reason(env, publish("kakunin.html", cwd=str(tmp_path)))
    assert "qa-html の検査を通っていない" in why and "<script> の JSON に questions／qs" in why
    assert "型の qa:css の印が無い" in why
    assert "細目 §3「まず構造を疑う」" in why and "もう一度 publish する" not in why, "止めた文が出し直しだけを促す古い形に戻った"


@needs_node
@pytest.mark.parametrize("dest", ["artifact", "copy"])
def test_qa_page_型どおりの緑のページは通る(env, tmp_path, dest):
    page = tmp_path / "確認.html"
    page.write_text(filled_qa_page(dest), encoding="utf-8")
    assert not denied(env, publish(page))


@needs_node
def test_qa_page_問いのデータは検査の緑と赤で分かれる(env):
    assert not denied(env, publish(DOCS_KIT_DATA / "good.json"))
    assert denied(env, publish(DOCS_KIT_DATA / "bad.json"))


@needs_node
def test_qa_page_型の印があれば中身が崩れていても止まる(env, tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_qa_page("artifact").replace("__unknown__", "unknown"), encoding="utf-8")
    assert "確認ページの型の印" in deny_reason(env, publish(page))


@pytest.mark.parametrize("body", [
    '<form><input type="radio" name="a" value="x"></form>',
    '<input type="radio" name="a"><script>sendPrompt("答え")</script>',
    '<input type="radio" name="a"><script>fetch("/a", {method: "POST", body: "x"})</script>',
    '<input type="radio" name="a"><script>window.claude.db.set("a", 1)</script>',
])
def test_qa_page_radioと答えを外へ出す仕組みが揃えば問いのページと見る(env, tmp_path, body):
    page = tmp_path / "poll.html"
    page.write_text(body, encoding="utf-8")
    env = without_check(env, tmp_path)
    assert "見つからず" in deny_reason(env, publish(page))


@pytest.mark.parametrize("name, body, extra", [
    ("表だけのページ", "<table><tr><td>1</td></tr></table><script>fetch('/x')</script>", {}),
    ("radio だけで送る仕組みが無い", '<input type="radio" name="a">', {}),
    ("radio で表示を切り替え fetch で読むだけ", '<label><input type="radio" name="span" value="w">週</label>'
     '<script>fetch("data.json").then(r=>r.json());window.claude.loadData("x")</script>', {}),
    ("qa-html を説明するページ", '<p>型は document に qa:submit を投げ、data-dest="artifact" と書く。</p>'
     '<input type="radio" name="v"><script>fetch("x.json")</script>', {}),
    ("JSON だが問いの並びでない", '{"rows": [{"options": [1, 2]}]}', {}),
    ("asset の上げ", '<form><input type="radio" name="a"></form>', {"asset": True, "url": "https://example.invalid/a"}),
    ("publish でない", '<form><input type="radio" name="a"></form>', {"action": "read"}),
])
def test_qa_page_問いのページでない物と_publish_でない物は見ない(env, tmp_path, name, body, extra):
    page = tmp_path / ("p.json" if body.startswith("{") else "p.html")
    page.write_text(body, encoding="utf-8")
    env = without_check(env, tmp_path)     # 見たら必ず止まる形にして、見ていない事を確かめる
    assert not denied(env, publish(page, **extra)), name


def test_qa_page_検査が無い時は止まる(env, tmp_path):
    page = tmp_path / "kakunin.html"
    page.write_text(STATE_PAGE, encoding="utf-8")
    env = without_check(env, tmp_path)
    assert "緑を確かめられない" in deny_reason(env, publish(page))


def test_qa_page_値の表で外した_file_は見ない(env, tmp_path):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    (proj / "config").mkdir()
    (proj / "config" / "skill-values.json").write_text(
        json.dumps({"guard": {"qa_page_exempt": [r"^(?:.*/)?quiz/[^/]+\.html$"]}}), encoding="utf-8")
    (tmp_path / "quiz").mkdir()
    page = tmp_path / "quiz" / "q.html"
    page.write_text(STATE_PAGE, encoding="utf-8")
    env = without_check(env, tmp_path)
    assert not denied(env, publish(page))


def _qa_page_mod():
    sys.path.insert(0, str(PLUGIN / "scripts"))
    try:
        import qa_page
    finally:
        sys.path.pop(0)
    return qa_page


def test_qa_page_入れた_plugin_の形では同じ版の検査だけを見つける(tmp_path):
    qa_page = _qa_page_mod()
    rel = Path("skills") / "qa-html" / "check.mjs"
    for ver in ("aaa", "bbb"):
        (tmp_path / "market" / "docs-kit" / ver / rel).parent.mkdir(parents=True)
        (tmp_path / "market" / "docs-kit" / ver / rel).write_text("//", encoding="utf-8")
    guard_root = tmp_path / "market" / "guard" / "aaa"
    guard_root.mkdir(parents=True)
    assert qa_page.find_check(str(guard_root)) == str(tmp_path / "market" / "docs-kit" / "aaa" / rel)
    # 注入: 同じ版の docs-kit が無く、別の版（新しい物）だけがある → 見つけない（前は新しい物で照らしていた）
    other = tmp_path / "market" / "guard" / "ccc"
    other.mkdir()
    assert qa_page.find_check(str(other)) == ""


def test_qa_page_赤が多い時ほか何件と全部の出し方を出す(env, tmp_path):
    fake = tmp_path / "fake_check.mjs"
    fake.write_text('console.log(JSON.stringify({ok: false, red: Array.from({length: 13}, (_, i) => "作り物の赤 " + (i + 1))}));'
                    "process.exit(1);\n", encoding="utf-8")
    page = tmp_path / "kakunin.html"
    page.write_text(STATE_PAGE, encoding="utf-8")
    if not shutil.which("node"):
        pytest.skip("node が無い（作り物の検査は node で動く）")
    env = without_check(env, tmp_path, ver="v1", docs_kit_ver="v1")
    real = tmp_path / "cache" / "market" / "docs-kit" / "v1" / "skills" / "qa-html" / "check.mjs"
    shutil.copyfile(fake, real)                                        # 同じ版の検査の在り処に作り物を置く
    why = deny_reason(env, publish(page))
    assert "検査の赤 13 件" in why and "作り物の赤 12" in why and "ほか 1 件" in why and str(real) in why


def test_qa_page_51個目に在る問いの並びも見分ける(tmp_path):
    sys.path.insert(0, str(PLUGIN / "scripts"))
    try:
        import qa_page
    finally:
        sys.path.pop(0)
    rows = [{"x": i} for i in range(50)] + [{"questions": [{"q": "作り物", "options": ["甲", "乙"]}]}]
    assert qa_page._has_question_list({"pages": rows})


# ── pick_one（選択肢の画面で作業・論点・原因を 1 つだけ選ばせる問い）──
def picked(env, payload):
    """pick_one が止めたか（同じ pre で ask_shape も走るので、pick_one の理由の印で見分ける）。"""
    out = hook(env, "pre", payload)
    return out.get("permissionDecision") == "deny" and "ask_pick_one_exempt" in out.get("permissionDecisionReason", "")


def ask(question, labels=("作り物の A（推奨）", "作り物の B", "分からない"), multi=False, sid="s1"):
    q = {"question": question, "header": "作り物", "multiSelect": multi,
         "options": [{"label": l, "description": "作り物"} for l in labels]}
    return {"tool_name": "AskUserQuestion", "session_id": sid, "tool_input": {"questions": [q]}}


@pytest.mark.parametrize("question", [
    "作り物の論点が 3 つあります。どれを進めますか",
    "どの論点を先に詰めますか",
    "何から始めますか",
    "どれを優先しますか",
    "まずどちらに取り掛かりますか",
    "作り物の崩れの原因はどれだと思いますか",
    "どれが一番の原因に近いですか",
    "何を先にやりますか",
    "原因は何だと思いますか",
    "次にどの作業を進めますか",
    "どれを進めたいですか",
    # 3 回目のレビューで挙がった「すべき」の形
    "どれを優先すべきですか",
    "どれから優先すべきでしょうか",
    "どれを先にやるべきですか",
    "どれに着手すべきですか",
    "どれに対応すべきですか",
])
def test_pick_one_作業や論点や原因を1つだけ選ばせる問いを止める(env, question):
    out = hook(env, "pre", ask(question))
    assert out.get("permissionDecision") == "deny"
    assert "全部" in out["permissionDecisionReason"] and "ask_pick_one_exempt" in out["permissionDecisionReason"]
    # 推奨の印は作り方の分かれ道だけ（細目 §4）。止めた文がやり方の問いに印を勧めると、答えを寄せる問いを作り直させる。
    assert "（推奨）」" not in out["permissionDecisionReason"] and "細目 §4「推奨の印」" in out["permissionDecisionReason"]


@pytest.mark.parametrize("question", [
    "作り物の置き場を A と B のどちらにしますか",
    "この言葉はどちらの意味ですか",
    "表とコードが食い違っています。どちらが正しいですか",
    "作り物の PR を main へ入れてよいですか",
    "作業は済みましたか",
    "どの会社の話ですか",
    "どの資料が根拠ですか",                 # 「根」は「根拠」に当たらない
    "どちらが根拠として正しいですか",
    "この修正の優先度は高いですか",         # 「優先度」は事実の問い
    "優先度はどのくらいですか",
    "何をやりたいですか",                   # 「何を」＋やる は意図の問い（順の語が無い）
    "このPRで何を扱いますか",
    # 2 回目のレビューで挙がった形（過去・受け身・「が」を挟む・意味・事実の問い）
    "どの設定が優先されますか",
    "どの資料を先に読みましたか",
    "どちらを先に作りましたか",
    "先にどの会社の話か教えてください",
    "まずどちらの意味か確かめたいです。どちらの意味ですか",
    "原因はどの資料に書いてありますか",
    "障害の要因として何が書かれていましたか",
    "どの原因の話ですか",
    "どちらが根本原因として正しいですか",   # AI の見立てが合っているかを問う形（直し方 3）
    "どの環境から始めましたか",
])
def test_pick_one_意図や事実を問う問いは通す(env, question):
    assert not picked(env, ask(question))


def test_pick_one_全部を選べる問いと全部やる道が在る問いは通す(env):
    assert not picked(env, ask("どれを進めますか", multi=True))
    assert not picked(env, ask("作り物の論点をどう進めますか。どれを進めますか",
                               labels=("全部この窓で順に", "それぞれ別の窓で同時に", "分からない")))


def test_pick_one_問いが複数でも1つでも当たれば止め当たった問いを名指す(env):
    p = ask("この言葉はどちらの意味ですか")
    p["tool_input"]["questions"].append(ask("どれから着手しますか")["tool_input"]["questions"][0])
    out = hook(env, "pre", p)
    assert out.get("permissionDecision") == "deny"
    reason = out["permissionDecisionReason"]
    assert "どれから着手しますか" in reason and "どちらの意味" not in reason


def test_pick_one_誤って止まる形は値の表で外せる(env, tmp_path):
    vals = tmp_path / "proj" / "config"
    vals.mkdir(parents=True)
    (vals / "skill-values.json").write_text(json.dumps({"guard": {"ask_pick_one_exempt": ["^作り物の試しの順"]}},
                                                       ensure_ascii=False), encoding="utf-8")
    assert not picked(env, ask("作り物の試しの順として、どれを先に詰めますか"))
    assert picked(env, ask("どれを先に詰めますか"))


def test_pick_one_選択肢の画面でない道具と壊れた入力は見ない(env):
    assert not denied(env, bash("echo どれを進めますか"))
    assert not denied(env, {"tool_name": "AskUserQuestion", "tool_input": {"questions": "こわれた"}})


# ── ask_shape（選択肢の画面の問いの形）──
def ask_pre(*qs):
    return {"tool_name": "AskUserQuestion", "session_id": "s1", "tool_input": {"questions": list(qs)}}


def q(text, header="作り物", labels=("A（推奨）", "B"), desc=""):
    return {"question": text, "header": header, "multiSelect": False,
            "options": [{"label": lb, "description": desc or "作り物の %s を選ぶ" % lb} for lb in labels]}


def deny_reason(env, payload):
    out = hook(env, "pre", payload)
    return out.get("permissionDecisionReason", "") if out.get("permissionDecision") == "deny" else ""


ASK_BAD = [
    ("題が長い", ask_pre(q("新しく入れた値『日々の不足（月の決まった時間から使った時間を引いて頭打ちにした時間）』を、会議を回数で別に"
                          "数える作り物の会社にも同じく当てて、不足の時間として表から引く形にしてよいでしょうか")), "[long]"),
    ("題が 2 文", ask_pre(q("会議の数え方を作り物の表で調べました。回数で別に数えますか？")), "[long]"),
    ("問いの番号", ask_pre(q("Q202611-67 の答えはどちらですか")), "Q202611-67"),
    ("短い番号", ask_pre(q("E02 の直しを入れますか")), "E02"),
    ("# の番号", ask_pre(q("#616 の変更を入れますか")), "#616"),
    ("版の番号", ask_pre(q("v0.21.0 の値を使いますか")), "v0.21.0"),
    ("file 名", ask_pre(q("設問の作り方.md の線に合わせますか")), "設問の作り方.md"),
    ("path が説明に", ask_pre(q("置き場をどちらにしますか", desc="plugins/guard/scripts に置く")), "plugins/guard/scripts"),
    ("識別子", ask_pre(q("直し_0020 をそのまま使いますか")), "直し_0020"),
    ("コードの字", ask_pre(q("`unattended_env` を真にしますか")), "unattended_env"),
    ("窓の id", ask_pre(q("作り物の窓 session_01AbCdEf へ回しますか")), "session_01AbCdEf"),
    ("選択肢の見出しに番号", ask_pre(q("どちらの決め方にしますか", labels=("E05 の形（推奨）", "前の形"))), "E05"),
    ("話題が混ざる", ask_pre(q("記録の古い行を片付けますか", header="片付け"), q("予定表の例は決まりどおりですか", header="予定表"),
                            q("検査の線を厳しめにしますか", header="厳しさ")), "[topic]"),
]


@pytest.mark.parametrize("name,payload,want", ASK_BAD, ids=[c[0] for c in ASK_BAD])
def test_ask_shape_読みにくい問いは画面を出す前に止め何でどう直すかを返す(env, name, payload, want):
    why = deny_reason(env, payload)
    assert want in why, why
    assert "直し方" in why and "画面はまだ人に出ていない" in why
    assert "直して出し直す。" not in why and why.strip().splitlines()[-1].endswith("細目 §3「まず構造を疑う」で探して直す"), \
        "止めた文が出し直しだけを促す古い形に戻った"


ASK_GOOD = [
    ("短い1文", ask_pre(q("会議の日は、回数で別に数えますか？", header="会議の数え方"))),
    ("どちらにしますか", ask_pre(q("作り物の置き場を A と B のどちらにしますか"))),
    ("同じ話題の2問", ask_pre(q("会議を回数で別に数えますか", header="会議の数え方"),
                           q("会議の端数は切り上げますか", header="会議の端数"))),
    ("済んだかの確かめ", ask_pre(q("設定の保存は終わりましたか？", header="手の確かめ",
                               labels=("終わった", "うまくいかない", "分からない")))),
    ("日付と分数", ask_pre(q("11 月の締めを 2026/11/19 にしますか", desc="1/2 ずつ 2 回に分ける"))),
    ("URL は数えない", ask_pre(q("作り物の資料の読み方は合っていますか", desc="資料 https://example.com/a/b/c.md の 3 行目"))),
    ("語の取れない問いを混ぜても", ask_pre(q("会議を回数で別に数えますか", header="会議"), q("どちらにしますか", header="どれ"))),
    ("A4 や 1 画面 4 問", ask_pre(q("A4 の紙 1 枚に 4 問まで載せますか"))),
]


@pytest.mark.parametrize("name,payload", ASK_GOOD, ids=[c[0] for c in ASK_GOOD])
def test_ask_shape_読みやすい問いは通す(env, name, payload):
    assert deny_reason(env, payload) == ""


# 推奨の印の付け方（誤りの類をわざと入れて止まるか・正しい形は通るか）
ASK_REC_BAD = [
    ("印が2つ", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A（推奨）", "B（推奨）", "分からない"))), "2 つの選択肢"),
    ("印が2つ目", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B (推奨)", "分からない"))), "1 つ目でない"),
    ("英語の印が後ろ", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "分からない", "B (Recommended)"))), "1 つ目でない"),
    ("分からないに印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("分からない（推奨）", "A", "B"))), "「分からない」の選択肢"),
    ("末の推奨が2つ", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A 推奨", "B・推奨"))), "2 つの選択肢"),
    ("【】の印が後ろ", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B【おすすめ】"))), "1 つ目でない"),
    ("区切りの無い末の印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B推奨"))), "1 つ目でない"),
    ("★の末の印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B ★推奨"))), "1 つ目でない"),
    ("括弧の中に続きのある印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B（推奨: 早い）"))), "1 つ目でない"),
    ("推奨案の印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B（推奨案）"))), "1 つ目でない"),
    ("末のお勧め", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B オススメ"))), "1 つ目でない"),
    ("★の括弧の印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B（★推奨）"))), "1 つ目でない"),
    ("第二推奨", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A（推奨）", "B（第二推奨）"))), "2 つの選択肢"),
    ("《》の印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B《推奨》"))), "1 つ目でない"),
    ("<>の印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B <推奨>"))), "1 つ目でない"),
    ("よく分からないに印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("よく分からない（推奨）", "A"))), "「分からない」の選択肢"),
    ("分かりませんに印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("分かりません（推奨）", "A"))), "「分からない」の選択肢"),
    ("Unknownに印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("Unknown (Recommended)", "A"))), "「分からない」の選択肢"),
    ("推奨の語を含む見出し", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A（推奨）", "推奨どおり B にする", "分からない"))), "印の形"),
    ("推奨なし", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A（推奨）", "B（推奨なし）", "分からない"))), "印の形"),
    ("非推奨", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A（推奨）", "B は非推奨", "分からない"))), "印の形"),
    ("推奨しません", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A（推奨）", "B（推奨しません）"))), "印の形"),
    ("1つ目でも崩れた形", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A（推奨: 早い）", "B", "分からない"))), "印の形"),
    ("やや推奨", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B（やや推奨）"))), "1 つ目でない"),
    ("Strongly", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B (Strongly recommended)"))), "1 つ目でない"),
    ("末の句点", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B 推奨。"))), "1 つ目でない"),
    ("I don't know に印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("I don't know (Recommended)", "A"))), "「分からない」の選択肢"),
    ("知らないに印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("知らない（推奨）", "A"))), "「分からない」の選択肢"),
    ("お薦めが後ろ", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B（お薦め）"))), "1 つ目でない"),
    ("suggested が後ろ", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B (suggested)"))), "1 つ目でない"),
    ("recommend", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B (recommend)"))), "1 つ目でない"),
]


@pytest.mark.parametrize("name,payload,want", ASK_REC_BAD, ids=[c[0] for c in ASK_REC_BAD])
def test_ask_shape_推奨の印の付け方が崩れた問いは画面を出す前に止める(env, name, payload, want):
    why = deny_reason(env, payload)
    assert "[rec]" in why and want in why, why
    assert "作り方の分かれ道" in why and "画面はまだ人に出ていない" in why


ASK_REC_GOOD = [
    ("1つ目に1つ", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A（推奨）", "B", "分からない")))),
    ("英語の印が1つ目", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A (Recommended)", "B", "分からない")))),
    ("印が無い", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A", "B", "分からない")))),
    ("説明の中の推奨は印でない", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A（推奨）", "B", "分からない"),
                                    desc="推奨の理由: あとで動かしやすい"))),
    ("全角の印", ask_pre(q("作り物の置き場をどちらにしますか", labels=("A （推奨）", "B", "分からない")))),
    ("unknowns を洗う", ask_pre(q("作り物の置き場をどちらにしますか", labels=("unknowns を洗う (Recommended)", "B", "分からない")))),
    ("見出しの途中の不明", ask_pre(q("作り物の置き場をどちらにしますか", labels=("不明点を先に洗う（推奨）", "B", "分からない")))),
]


@pytest.mark.parametrize("name,payload", ASK_REC_GOOD, ids=[c[0] for c in ASK_REC_GOOD])
def test_ask_shape_推奨の印が1つ目に1つだけなら通す(env, name, payload):
    assert deny_reason(env, payload) == ""


def test_ask_shape_判定の値は値の表で変えられ誤って止まる形は外せる(env, tmp_path):
    long_q = ask_pre(q("作り物の置き場を、前の窓で話した二つの案のうち、あとで動かしやすい方に寄せて、今週のうちに決めて"
                       "しまってよいですか、それとも来週の打ち合わせまで待ちますか"))
    assert "[long]" in deny_reason(env, long_q)
    table = tmp_path / "values.json"
    env["SKILL_VALUES"] = str(table)
    table.write_text(json.dumps({"guard": {"ask_question_max_chars": 120}}), encoding="utf-8")
    assert deny_reason(env, long_q) == ""
    assert "B202" in deny_reason(env, ask_pre(q("B202 の部屋で会いますか")))
    table.write_text(json.dumps({"guard": {"ask_term_allow": ["^B\\d+$"]}}), encoding="utf-8")
    assert deny_reason(env, ask_pre(q("B202 の部屋で会いますか"))) == ""
    assert "E02" in deny_reason(env, ask_pre(q("E02 を入れますか")))
    table.write_text(json.dumps({"guard": {"ask_shape_exempt": ["^作り物の例外"]}}), encoding="utf-8")
    assert deny_reason(env, ask_pre(q("作り物の例外 E02 を入れますか"))) == ""
    table.write_text(json.dumps({"guard": {"ask_inner_terms_extra": ["例の関所"]}}), encoding="utf-8")
    assert "例の関所" in deny_reason(env, ask_pre(q("例の関所を外しますか")))


# ── 推奨の印を付けない形の問い（済んだか・意図）に印が付いたら、画面の後に知らせる（止めない）──
def ask_post(text, labels=("終わった（推奨）", "うまくいかない", "分からない")):
    qq = q(text, header="作り物", labels=labels)
    return {"tool_name": "AskUserQuestion", "session_id": "s1", "tool_input": {"questions": [qq]},
            "tool_response": {"questions": [qq], "answers": {qq["question"]: labels[0]}}}


def notice_text(env, payload):
    return hook(env, "post", payload).get("additionalContext", "")


REC_NOTICE = [
    ("済んだか", ask_post("設定の保存は終わりましたか？"), "済んだかの確認"),
    ("済んだか 2", ask_post("作り物の画面で送りましたか"), "済んだかの確認"),
    ("意図", ask_post("この並びにしたのはなぜですか", labels=("見やすさ（推奨）", "前の形のまま", "分からない")), "意図・考え"),
    ("済んでいますか", ask_post("作り物の手続きはもう済んでいますか"), "済んだかの確認"),
    ("完了していますか", ask_post("作り物の登録は完了していますか"), "済んだかの確認"),
    ("終わってますか", ask_post("作り物の送信は終わってますか"), "済んだかの確認"),
    ("反映されましたか", ask_post("作り物の設定は反映されましたか"), "済んだかの確認"),
    ("考え", ask_post("作り物の色の好みはどちらですか", labels=("青 (Recommended)", "緑", "分からない")), "意図・考え"),
]


@pytest.mark.parametrize("name,payload,want", REC_NOTICE, ids=[c[0] for c in REC_NOTICE])
def test_ask_shape_済んだかや意図の問いの推奨の印は画面の後に知らせ止めない(env, name, payload, want):
    txt = notice_text(env, payload)
    assert want in txt and "止めていない" in txt, txt
    pre = dict(payload)
    pre.pop("tool_response")
    assert deny_reason(env, pre) == ""      # 画面の前には止めない（知らせるだけ）


REC_QUIET = [
    ("分かれ道の印", ask_post("作り物の置き場をどちらにしますか", labels=("A（推奨）", "B", "分からない"))),
    ("意図した動きの分かれ道", ask_post("意図した動きに近い直し方はどちらですか", labels=("A（推奨）", "B", "分からない"))),
    ("好みに合う置き場の分かれ道", ask_post("作り物の置き場を A と B のどちらにしますか", labels=("A（推奨）", "B", "分からない"))),
    ("印の無い済んだか", ask_post("設定の保存は終わりましたか？", labels=("終わった", "うまくいかない", "分からない"))),
    ("選択肢の画面の外", {"tool_name": "Bash", "tool_input": {"command": "echo 終わりましたか（推奨）"}}),
]


@pytest.mark.parametrize("name,payload", REC_QUIET, ids=[c[0] for c in REC_QUIET])
def test_ask_shape_分かれ道の印や印の無い問いは知らせない(env, name, payload):
    assert "推奨の印が付いた問い" not in notice_text(env, payload)


def test_ask_shape_推奨の印の知らせの形は値の表で替え外せる(env, tmp_path):
    table = tmp_path / "values.json"
    env["SKILL_VALUES"] = str(table)
    done = ask_post("設定の保存は終わりましたか？")
    table.write_text(json.dumps({"guard": {"ask_rec_notice_exempt": ["^設定の保存"]}}), encoding="utf-8")
    assert "推奨の印が付いた問い" not in notice_text(env, done)
    table.write_text(json.dumps({"guard": {"ask_rec_notice_kinds": {"作り物の形": ["置き場"]}}}), encoding="utf-8")
    txt = notice_text(env, ask_post("作り物の置き場をどちらにしますか", labels=("A（推奨）", "B", "分からない")))
    assert "作り物の形" in txt
    assert "推奨の印が付いた問い" not in notice_text(env, done)   # 形を替えたら既定の形は使わない
    table.write_text(json.dumps({"guard": {"ask_rec_notice_kinds": {"壊れた形": ["(終わり"], "済んだか": ["終わりましたか"]}}}),
                     encoding="utf-8")
    txt = notice_text(env, done)
    assert "壊れていて" in txt and "(終わり" in txt and "済んだか に見える" in txt, txt   # 壊れた形があっても他の形は照らす


def test_ask_shape_選択肢の画面の外は見ない(env):
    assert deny_reason(env, {"tool_name": "Bash", "tool_input": {"command": "echo Q202611-67 v0.21.0"}}) == ""


# ── unanswered の出し直し（流れの中で扱う・降ろせる・言い直しても閉じる）──
UNANSWERED = Path(__file__).resolve().parent.parent / "plugins" / "guard" / "scripts" / "unanswered.py"


def run_cli(env, *args):
    return subprocess.run([sys.executable, str(UNANSWERED), *args], capture_output=True, text=True, env=env,
                          cwd=env["CLAUDE_PROJECT_DIR"], timeout=60)


def test_持ち越した問いは前提を添えて出すか降ろすかを選ばせ文面そのままを求めない(env):
    hook(env, "post", ask_result())
    again = hook(env, "start", {"session_id": "s2"}).get("additionalContext", "")
    assert "そのまま" not in again and "作り直さない" not in again
    assert "前提" in again and "drop <key>" in again and "関わらない問い" in again
    assert "key: " in again


def test_答え済みの問いはAIが台帳から降ろせ次の窓に出ない(env):
    hook(env, "post", ask_result())
    listed = run_cli(env, "list")
    assert listed.returncode == 0, listed.stderr
    key = listed.stdout.split("\t")[0]
    assert run_cli(env, "drop", key).returncode == 2           # 訳の無い降ろしは受けない
    p = run_cli(env, "drop", key, "--why", "この窓の頼みで答えが出ていた")
    assert p.returncode == 0 and "降ろした" in p.stdout, p.stdout + p.stderr
    assert hook(env, "start", {"session_id": "s3"}) == {}
    assert run_cli(env, "drop", "nokey", "--why", "x").returncode == 1


def test_降ろしの口は知らない印で止まる(env):
    hook(env, "post", ask_result())
    key = run_cli(env, "list").stdout.split("\t")[0]
    for args in (("drop", key, "--force", "--why", "x"), ("drop", key, "--why", "x", "--why", "y"),
                 ("drop", key, "--why", "x", "--force"), ("list", "--all")):
        p = run_cli(env, *args)
        assert p.returncode == 2, args
    assert key in run_cli(env, "list").stdout                         # 止まった間に降ろしていない


def _ask_post(question, labels, answered, sid):
    qq = {"question": question, "header": "置き場",
          "options": [{"label": lb, "description": "作り物"} for lb in labels]}
    return {"tool_name": "AskUserQuestion", "session_id": sid, "transcript_path": "",
            "tool_response": {"questions": [qq], "answers": {question: labels[0]} if answered else {}}}


def test_言い直した問いに答えが返っても元の問いは機械では結ばずAIが降ろす(env):
    labels = ["A に置く（推奨）", "B に置く", "分からない"]
    hook(env, "post", _ask_post("作り物の置き場を A と B のどちらにしますか", labels, False, "s1"))
    hook(env, "post", _ask_post("前の窓の続きです。作り物の置き場はどちらにしますか", labels, True, "s2"))
    again = hook(env, "start", {"session_id": "s3"}).get("additionalContext", "")
    assert "作り物の置き場を A と B のどちらにしますか" in again and "言い直した問いに答えが" in again
    key = run_cli(env, "list").stdout.split("\t")[0]
    assert run_cli(env, "drop", key, "--why", "言い直した問いに答えが返った").returncode == 0
    assert hook(env, "start", {"session_id": "s4"}) == {}


@pytest.mark.parametrize("left,right,labels", [
    ("設定の保存は終わりましたか", "鍵の登録は済みましたか", ["終わった（推奨）", "うまくいかない", "分からない"]),
    ("請求書を先方へ送ってよいですか？", "古い請求書の控えを消してよいですか？", ["はい（推奨）", "いいえ", "分からない"]),
    ("資料の共有の範囲をどちらにしますか", "資料を社外へ送る時期をどちらにしますか", ["今週（推奨）", "来週", "分からない"]),
    ("資料の置き場はどこにしますか", "議事録の置き場はどこにしますか", ["共有の棚（推奨）", "個人の棚", "分からない"]),
    ("請求書は郵送とメールのどちらで送りますか", "見積書は郵送とメールのどちらで送りますか", ["メール（推奨）", "郵送", "分からない"]),
    ("A社への請求書の送り方はどちらにしますか", "B社への請求書の送り方はどちらにしますか", ["メール（推奨）", "郵送", "分からない"]),
])
def test_同じ選択肢で物だけ違う問いを閉じず重ねもしない(env, left, right, labels):
    hook(env, "post", _ask_post(left, labels, False, "s1"))
    hook(env, "post", _ask_post(right, labels, True, "s2"))
    again = hook(env, "start", {"session_id": "s3"}).get("additionalContext", "")
    assert left in again
    hook(env, "post", _ask_post(right, labels, False, "s4"))
    again = hook(env, "start", {"session_id": "s5"}).get("additionalContext", "")
    assert "2 件あります" in again and left in again and right in again


def test_読んでから書くまでに積まれた_key_の無い行は知らせずに降ろさない():
    import importlib.util
    spec = importlib.util.spec_from_file_location("unanswered_t", UNANSWERED)
    uq = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(uq)
    data = {"pending": [{"last_seen_at": "2000-01-01T00:00:00.000000Z"}, {"last_seen_at": "2000-01-01T00:00:00.000000Z"}],
            "expired_recent": []}
    assert uq.retire(data, set(), notified=True, keyless=1) == 1     # 読んで知らせたのは 1 行だけ
    assert len(data["pending"]) == 1 and len(data["expired_recent"]) == 1


def test_推奨の印の崩れと1つだけ選ばせる問いが両方当たれば理由を両方つないで返す(env):
    """ask_shape の rec と pick_one は同じ pre で走る。片方の理由が他方を消すと、AI が片方だけ直して 2 度止まる。"""
    why = deny_reason(env, ask_pre(q("どれを進めますか", header="進め方", labels=("作り物の A", "作り物の B（推奨）", "分からない"))))
    assert "[rec]" in why and "1 つ目でない" in why, why
    assert "ask_pick_one_exempt" in why and "細目 §4「推奨の印」" in why, why
    assert why.strip().splitlines()[-1].endswith("細目 §3「まず構造を疑う」で探して直す"), why
