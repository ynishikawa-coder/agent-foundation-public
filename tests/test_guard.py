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
def test_hooks_json_が3つの出来事で入口を回し_Stop_で差し戻す口を持たない():
    data = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    want = {"PreToolUse": "pre", "PostToolUse": "post", "SessionStart": "start"}
    assert set(data) == set(want)
    for event, arg in want.items():
        cmd = data[event][0]["hooks"][0]["command"]
        assert "${CLAUDE_PLUGIN_ROOT}/scripts/guard.py" in cmd and cmd.endswith(" " + arg)


def test_壊れた入力は_pre_では止め_post_と_start_では何も出さない(env):
    for event in ("pre", "post", "start"):
        p = subprocess.run([sys.executable, str(GUARD), event], input="こわれた", capture_output=True, text=True, env=env)
        assert p.returncode == 0
        if event == "pre":
            assert json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
        else:
            assert p.stdout.strip() == ""


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


def deny_reason(env, payload):
    out = hook(env, "pre", payload)
    return out.get("permissionDecisionReason", "") if out.get("permissionDecision") == "deny" else ""


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
