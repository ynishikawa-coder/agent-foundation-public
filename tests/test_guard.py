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
    e = {k: v for k, v in os.environ.items() if not k.startswith(("AF_", "SKILL_VALUES", "CLAUDE_PROJECT_DIR"))}
    e.update({"AF_GUARD_TMP": str(tmp_path / "tmp"), "AF_GUARD_STATE": str(tmp_path / "state"),
              "CLAUDE_PROJECT_DIR": str(proj), "PYTHONDONTWRITEBYTECODE": "1",
              "TMPDIR": str(tmp_path / "scratch")})     # 作業場を tmp_path の下の 1 か所に絞る（repo は作業場の外）
    return e


def hook(env, event, payload):
    p = subprocess.run([sys.executable, str(GUARD), event], input=json.dumps(payload, ensure_ascii=False),
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
def test_hooks_json_が3つの出来事で入口を回す():
    data = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    want = {"PreToolUse": "pre", "PostToolUse": "post", "SessionStart": "start"}
    assert set(data) == set(want)
    for event, arg in want.items():
        cmd = data[event][0]["hooks"][0]["command"]
        assert "${CLAUDE_PLUGIN_ROOT}/scripts/guard.py" in cmd and cmd.endswith(" " + arg)


def test_壊れた入力では何も出さず通す(env):
    for event in ("pre", "post", "start"):
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
def usage_log(tmp_path, tokens, first="作り物の頼み"):
    return write_log(tmp_path / "ctx.jsonl", [
        {"type": "user", "message": {"content": first}},
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
    tpath = usage_log(tmp_path, 400_000, first="あなたは書く窓です（親窓 session_ABC123 の子）。")
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


def test_寿命を過ぎた問いは冒頭に出ない(env, tmp_path):
    hook(env, "post", ask_result())
    ledger = next((tmp_path / "state").rglob("unanswered-questions.json"))
    data = json.loads(ledger.read_text(encoding="utf-8"))
    for p in data["pending"]:
        p["last_seen_at"] = "2000-01-01T00:00:00.000000Z"
    ledger.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert hook(env, "start", {"session_id": "s2"}) == {}


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
    broken = tmp_path / "plugin"
    import shutil
    shutil.copytree(PLUGIN / "scripts", broken)
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
    env = dict(env, AF_QA_CHECK=str(tmp_path / "無い.mjs"))
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
    env = dict(env, AF_QA_CHECK=str(tmp_path / "無い.mjs"))     # 見たら必ず止まる形にして、見ていない事を確かめる
    assert not denied(env, publish(page, **extra)), name


def test_qa_page_検査が無い時は止まる(env, tmp_path):
    page = tmp_path / "kakunin.html"
    page.write_text(STATE_PAGE, encoding="utf-8")
    env = dict(env, AF_QA_CHECK=str(tmp_path / "無い.mjs"))
    assert "緑を確かめられない" in deny_reason(env, publish(page))


def test_qa_page_値の表で外した_file_は見ない(env, tmp_path):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    (proj / "config").mkdir()
    (proj / "config" / "skill-values.json").write_text(
        json.dumps({"guard": {"qa_page_exempt": [r"/quiz/[^/]+\.html$"]}}), encoding="utf-8")
    (tmp_path / "quiz").mkdir()
    page = tmp_path / "quiz" / "q.html"
    page.write_text(STATE_PAGE, encoding="utf-8")
    env = dict(env, AF_QA_CHECK=str(tmp_path / "無い.mjs"))
    assert not denied(env, publish(page))


def test_qa_page_入れた_plugin_の形でも検査を見つける(tmp_path):
    sys.path.insert(0, str(PLUGIN / "scripts"))
    try:
        import qa_page
    finally:
        sys.path.pop(0)
    rel = Path("skills") / "qa-html" / "check.mjs"
    for ver in ("aaa", "bbb"):
        (tmp_path / "market" / "docs-kit" / ver / rel).parent.mkdir(parents=True)
        (tmp_path / "market" / "docs-kit" / ver / rel).write_text("//", encoding="utf-8")
    guard_root = tmp_path / "market" / "guard" / "aaa"
    guard_root.mkdir(parents=True)
    old = os.environ.pop("AF_QA_CHECK", None)
    try:
        assert qa_page.find_check(str(guard_root)) == str(tmp_path / "market" / "docs-kit" / "aaa" / rel)
        other = tmp_path / "market" / "guard" / "ccc"         # 同じ版の docs-kit が無い時は新しい物
        other.mkdir()
        os.utime(tmp_path / "market" / "docs-kit" / "aaa" / rel, (1, 1))
        assert qa_page.find_check(str(other)) == str(tmp_path / "market" / "docs-kit" / "bbb" / rel)
    finally:
        if old is not None:
            os.environ["AF_QA_CHECK"] = old


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
                               labels=("終わった（推奨）", "うまくいかない", "分からない")))),
    ("日付と分数", ask_pre(q("11 月の締めを 2026/11/19 にしますか", desc="1/2 ずつ 2 回に分ける"))),
    ("URL は数えない", ask_pre(q("作り物の資料の読み方は合っていますか", desc="資料 https://example.com/a/b/c.md の 3 行目"))),
    ("語の取れない問いを混ぜても", ask_pre(q("会議を回数で別に数えますか", header="会議"), q("どちらにしますか", header="どれ"))),
    ("A4 や 1 画面 4 問", ask_pre(q("A4 の紙 1 枚に 4 問まで載せますか"))),
]


@pytest.mark.parametrize("name,payload", ASK_GOOD, ids=[c[0] for c in ASK_GOOD])
def test_ask_shape_読みやすい問いは通す(env, name, payload):
    assert deny_reason(env, payload) == ""


def test_ask_shape_判定の値は値の表で変えられ誤って止まる形は外せる(env, tmp_path):
    long_q = ask_pre(q("作り物の置き場を、前の窓で話した二つの案のうち、あとで動かしやすい方に寄せて、今週のうちに決めて"
                       "しまってよいですか、それとも来週の打ち合わせまで待ちますか"))
    assert "[long]" in deny_reason(env, long_q)
    table = tmp_path / "values.json"
    env["SKILL_VALUES"] = str(table)
    table.write_text(json.dumps({"guard": {"ask_question_max_chars": 120}}), encoding="utf-8")
    assert deny_reason(env, long_q) == ""
    table.write_text(json.dumps({"guard": {"ask_term_allow": ["^ISO\\d+$"]}}), encoding="utf-8")
    assert deny_reason(env, ask_pre(q("ISO9001 の書き方に合わせますか"))) == ""
    assert "E02" in deny_reason(env, ask_pre(q("E02 を入れますか")))
    table.write_text(json.dumps({"guard": {"ask_shape_exempt": ["^作り物の例外"]}}), encoding="utf-8")
    assert deny_reason(env, ask_pre(q("作り物の例外 E02 を入れますか"))) == ""
    table.write_text(json.dumps({"guard": {"ask_inner_terms_extra": ["例の関所"]}}), encoding="utf-8")
    assert "例の関所" in deny_reason(env, ask_pre(q("例の関所を外しますか")))


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


# ── pr_text（GitHub へ出す前の PR の文）──
CHECKER = ROOT / "plugins" / "checker" / "scripts"
CLEANUP_TPL = ROOT / "plugins" / "dev-flow" / "skills" / "preimpl-cleanup" / "整地受領証.template.md"
WRITER = "session_01AAAAAAAAAAAAAAAAAAAAAAAA"
REVIEWER = "session_01BBBBBBBBBBBBBBBBBBBBBBBB"
STRANGER = "session_01CCCCCCCCCCCCCCCCCCCCCCCC"


def gh(tool, owner="fake-owner", repo="fake-private", **ti):
    return {"tool_name": "mcp__github__" + tool, "session_id": "s1",
            "tool_input": {"owner": owner, "repo": repo, **ti}}


def verdict_comment(judged="green", head="0123456789ab", fail=None, stop=False, line1=None):
    """review-pr の見る点の表から組んだ判定のコメント（点を写さず、表を直に読む）。"""
    sys.path.insert(0, str(CHECKER))
    import verdict_form  # noqa: E402
    points = verdict_form.load_points()
    rows = []
    for no, name in sorted(points.items()):
        val = "書いた窓 %s ≠ この窓" % WRITER if no == 3 else ("fail" if no == fail else "pass")
        rows.append("- %d %s: %s" % (no, name, val))
    first = line1 or "レビューした窓: %s 判定: %s" % (REVIEWER, judged)
    fix = [verdict_form.ROOT_CAUSE] if judged == "red" else []
    lines = [first] + (["見た先端: " + head] if head else []) + ["", "## verdict", judged] + fix + ["", "## 点"] + rows
    lines += ["", "## 所見", "- [止める｜実装] 作り物の欠け" if stop else "- [後の便｜実装] 作り物の後の便"]
    return "\n".join(lines) + "\n"


def cleanup_body(extra=""):
    return ("親窓: %s\n書いた窓: %s\njob: 20261119-fake\n触る path: a.py\n検査: check_all: 緑 (1 本)\n\n"
            "## 何をどう変えたか\n作り物の直し。\n\n## 整地（根治の 4 段）\n\n## 1. 問題\n作り物の問題。\n\n"
            "## 2. 原因と同じ原因の他の問題\n**原因**: 作り物。\n\n## 3. 解決（足す物・畳む物・注入の試験と残る穴）\n**足す物**: 作り物。\n\n"
            "## 4. 未来\n作り物の未来。\n%s" % (STRANGER, WRITER, extra))


PR_BAD = [
    ("判定の先端の行が無い", gh("add_issue_comment", issue_number=1, body=verdict_comment(head="")), "[verdict]", "見た先端"),
    ("止めるが在るのに green", gh("add_issue_comment", issue_number=1, body=verdict_comment(stop=True)), "[verdict]", "判定は red"),
    ("点に fail が在るのに green", gh("pull_request_review_write", pullNumber=1, method="create", event="COMMENT",
                                     body=verdict_comment(fail=8)), "[verdict]", "判定は red"),
    ("名乗りが session id でない", gh("add_issue_comment", issue_number=1,
                                    body=verdict_comment(line1="レビューした窓: %s の中の助手 判定: green" % REVIEWER)),
     "[verdict]", "1 行目"),
    ("整地の欄が無い", gh("create_pull_request", title="作り物", head="b", base="main",
                         body="親窓: x\n\n## 何をどう変えたか\n作り物。\n"), "[cleanup]", "1. 問題"),
    ("整地の見出しが古い名", gh("create_pull_request", title="作り物", head="b", base="main",
                              body=cleanup_body().replace("## 2. 原因と同じ原因の他の問題", "## 2. 同じ原因から起きている他の問題")),
     "[cleanup]", "2. 原因と同じ原因の他の問題"),
    ("雛形の〔…〕が残る", gh("update_pull_request", pullNumber=1,
                            body=cleanup_body("\n〔直した後、同じ問題と 2 欄の他の問題が起きない姿〕\n")), "[cleanup]", "〔…〕"),
    ("不要の訳が無い", gh("create_pull_request", title="作り物", head="b", base="main", body="## 何をどう変えたか\n誤字。\n整地: 不要\n"),
     "[cleanup]", "1. 問題"),
    ("不要の訳が雛形のまま", gh("create_pull_request", title="作り物", head="b", base="main",
                              body="## 何をどう変えたか\n誤字。\n整地: 不要（<なぜ要らないか>）\n"), "[cleanup]", "1. 問題"),
    ("見出しが注記の中だけ", gh("create_pull_request", title="作り物", head="b", base="main",
                              body="## 何をどう変えたか\n作り物。\n<!--\n## 1. 問題\n## 2. 原因と同じ原因の他の問題\n## 3. 解決\n## 4. 未来\n"
                                   "整地: 不要（作り物）\n-->\n"), "[cleanup]", "1. 問題"),
    ("本文に窓の id がそのまま", gh("create_pull_request", title="作り物", head="b", base="main",
                                  body=cleanup_body("\n- 残り — 直す窓 %s\n" % STRANGER)), "[words]", STRANGER),
    ("題に窓の id", gh("update_pull_request", pullNumber=1, title="作り物 %s の続き" % STRANGER), "[words]", "PR の題"),
]


@pytest.mark.parametrize("name,payload,code,want", PR_BAD, ids=[c[0] for c in PR_BAD])
def test_pr_text_崩れた判定と欄の欠けた本文と窓の_id_は出す前に止め直し方を返す(env, name, payload, code, want):
    why = deny_reason(env, payload)
    assert code in why and want in why, why
    assert "直し方" in why and "文はまだ GitHub に出ていない" in why and "誤って止めた時" in why


PR_GOOD = [
    ("形の合う判定", gh("add_issue_comment", issue_number=1, body=verdict_comment())),
    ("止めるの在る red", gh("add_issue_comment", issue_number=1, body=verdict_comment(judged="red", stop=True))),
    ("判定でない普通のコメント", gh("add_issue_comment", issue_number=1, body="作り物の確かめを足しました。判定は後で別の窓が付けます。")),
    ("整地の 4 欄の揃った本文", gh("create_pull_request", title="作り物", head="b", base="main", body=cleanup_body())),
    ("見出しが ### でも", gh("create_pull_request", title="作り物", head="b", base="main",
                           body=cleanup_body().replace("\n## 1.", "\n### 1.").replace("\n## 4.", "\n### 4."))),
    ("整地の要らない PR は訳つきの 1 行", gh("create_pull_request", title="誤字", head="b", base="main",
                                          body="## 何をどう変えたか\n誤字だけ。\n\n整地: 不要（振る舞いを変えない誤字の直しだけ）\n")),
    ("題だけの書き替え", gh("update_pull_request", pullNumber=1, title="作り物の題")),
    ("窓の id が決まった欄・URL・コードの中だけ", gh("create_pull_request", title="作り物", head="b", base="main",
                                               body=cleanup_body("\n直す窓（https://claude.ai/code/%s）\n`%s`\n```\n%s\n```\n"
                                                                 "session_watch.py の点検\n" % (STRANGER, STRANGER, STRANGER)))),
    ("見ない道具", gh("create_branch", branch="b", from_branch="main")),
]


@pytest.mark.parametrize("name,payload", PR_GOOD, ids=[c[0] for c in PR_GOOD])
def test_pr_text_形の合う判定と本文と普通のコメントは通す(env, name, payload):
    assert deny_reason(env, payload) == ""


def test_pr_text_道具の名は_MCP_の_server_の名を問わず末尾で見る(env):
    p = gh("create_pull_request", title="作り物", head="b", base="main", body="## 何をどう変えたか\n作り物。\n")
    p["tool_name"] = "mcp__0a1b2c3d__create_pull_request"
    assert "[cleanup]" in deny_reason(env, p)
    p["tool_name"] = "mcp__github__create_pull_request_review"
    assert deny_reason(env, p) == ""


def test_pr_text_整地の見出しは雛形を直に読む(env, tmp_path):
    """雛形の見出しを替えると、照らす見出しも替わる（ここに見出しを写していない）。"""
    tpl = tmp_path / "整地受領証.template.md"
    tpl.write_text(CLEANUP_TPL.read_text(encoding="utf-8").replace("## 4. 未来", "## 4. 作り物の新しい欄"), encoding="utf-8")
    env["AF_CLEANUP_TEMPLATE"] = str(tpl)
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=cleanup_body()))
    assert "4. 作り物の新しい欄" in why
    env["AF_CLEANUP_TEMPLATE"] = str(tmp_path / "無い.md")
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=cleanup_body()))
    assert "整地の雛形" in why and "見つからず" in why


def test_pr_text_判定の形は道具を直に呼び無ければ止める(env, tmp_path):
    env["AF_VERDICT_FORM"] = str(tmp_path / "無い.py")
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body=verdict_comment()))
    assert "[verdict]" in why and "見つからず" in why
    broken = tmp_path / "verdict_form.py"
    broken.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    env["AF_VERDICT_FORM"] = str(broken)
    assert "壊れた" in deny_reason(env, gh("add_issue_comment", issue_number=1, body=verdict_comment()))


def test_pr_text_誤って止まる_repo_は値の表で外せる(env, tmp_path):
    table = tmp_path / "values.json"
    env["SKILL_VALUES"] = str(table)
    table.write_text(json.dumps({"guard": {"pr_cleanup_exempt_repos": ["^fake-owner/fake-private$"],
                                           "pr_words_exempt_repos": ["^fake-owner/"]}}), encoding="utf-8")
    body = "## 何をどう変えたか\n直す窓 %s\n" % STRANGER
    assert deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=body)) == ""
    assert "[cleanup]" in deny_reason(env, gh("create_pull_request", repo="other", title="作り物", head="b", base="main", body=body))
    # 判定の形は外す口を持たない
    assert "[verdict]" in deny_reason(env, gh("add_issue_comment", issue_number=1, body=verdict_comment(head="")))


def _fake_public_repo(proj, deny_word):
    """作り物の公開の repo の取り出し（origin が owner/repo・workflow が action public-guard を呼ぶ）。"""
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    subprocess.run(["git", "-C", str(proj), "remote", "add", "origin", "https://github.com/fake-owner/fake-public.git"], check=True)
    wf = proj / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "public-guard.yml").write_text(
        "jobs:\n  public-guard:\n    steps:\n      - uses: fake/agent-foundation-public/public-guard@v0.0.1\n"
        "        with:\n          deny-words-file: data/deny.txt\n", encoding="utf-8")
    (proj / "data").mkdir()
    (proj / "data" / "deny.txt").write_text(deny_word + "\n", encoding="utf-8")


PUBLIC_WORD = "作り物" + "ノ禁句"
MAIL = "someone" + "@" + "gmail.com"


def test_pr_text_公開の_repo_へは置かない物の在る文を出す前に止める(env, tmp_path):
    _fake_public_repo(Path(env["CLAUDE_PROJECT_DIR"]), PUBLIC_WORD)
    pub = dict(repo="fake-public")
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, **pub))
    assert "[public]" in why and "コメント: メールアドレス" in why and MAIL not in why.split("直し方")[0].replace("コメント: メールアドレス", "")
    why = deny_reason(env, gh("update_pull_request", pullNumber=1, title="%s の直し" % PUBLIC_WORD, **pub))
    assert "[public]" in why and "PR の題: 置かない語" in why and PUBLIC_WORD not in why
    why = deny_reason(env, gh("issue_write", method="create", title="作り物", body="連絡は %s へ" % MAIL, **pub))
    assert "issue の本文: メールアドレス" in why
    assert deny_reason(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめを足しました", **pub)) == ""
    why = deny_reason(env, gh("merge_pull_request", pullNumber=1, merge_method="squash",
                              commit_title="作り物", commit_message="連絡は %s へ" % MAIL, **pub))
    assert "commit の説明: メールアドレス" in why
    why = deny_reason(env, gh("push_files", branch="b", files=[], message="%s の直し" % PUBLIC_WORD, **pub))
    assert "commit の説明: 置かない語" in why
    assert deny_reason(env, gh("push_files", branch="b", files=[], message="作り物の直し", **pub)) == ""
    # 同じ文でも公開でない repo（取り出しが別の repo）は照らさない
    assert deny_reason(env, gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL)) == ""


def test_pr_text_公開の_repo_で検査が見つからない時も止める(env, tmp_path):
    _fake_public_repo(Path(env["CLAUDE_PROJECT_DIR"]), PUBLIC_WORD)
    env["AF_PUBLIC_GUARD"] = str(tmp_path / "無い.py")
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめ", repo="fake-public"))
    assert "[public]" in why and "見つからず" in why


def test_pr_text_手元に取り出しの無い公開の_repo_は値の表で足せる(env, tmp_path):
    table = tmp_path / "values.json"
    env["SKILL_VALUES"] = str(table)
    p = gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, repo="far-public")
    assert deny_reason(env, p) == ""
    table.write_text(json.dumps({"guard": {"public_repos_extra": ["^fake-owner/far-public$"]}}), encoding="utf-8")
    assert "[public]" in deny_reason(env, p)
