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


# ── outbound（人や他の窓へ渡る道具の入力: 鍵・番号だけの頼み・窓の題と手の窓の 4 欄）──
# 鍵の形は字をつないで作る（この file 自身が公開の検査に当たらないため）。値は作り物。
FAKE_KEYS = {
    "GitHub のトークン": "gh" + "p_" + "A1b2C3d4" * 5,
    "Anthropic の鍵": "sk-" + "ant-" + "x" * 30,
    "AWS の鍵 ID": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    "Slack のトークン": "xo" + "xb-" + "1234567890-abc",
}
SEND = "mcp__claude-code-remote__send_message"
CREATE = "mcp__claude-code-remote__create_session"
SET_TITLE = "mcp__claude-code-remote__set_session_title"


def tool(name, **ti):
    return {"tool_name": name, "session_id": "s1", "cwd": "", "tool_input": ti}


@pytest.mark.parametrize("label", sorted(FAKE_KEYS))
@pytest.mark.parametrize("payload", [
    lambda k: tool(SEND, session_id="session_x", message="作り物の鍵はこれ: %s を使って" % k),
    lambda k: tool("SendMessage", to="worker", message="鍵 %s" % k),
    lambda k: tool(CREATE, title="🤖 作り物の作業", prompt="この鍵で入って %s" % k),
    lambda k: tool("mcp__github__create_pull_request", title="作り物", body="手順\n\n```\nTOKEN=%s\n```" % k),
    lambda k: tool("mcp__notion__notion-update-page", page_id="x", content_updates=[{"old_str": "a", "new_str": k}]),
])
def test_outbound_外へ渡す道具の入力に鍵の形があれば出す前に止め鍵の字は返さない(env, label, payload):
    key = FAKE_KEYS[label]
    why = deny_reason(env, payload(key))
    assert "鍵・認証情報の形" in why and label in why
    assert key not in why                       # 止めた文にも鍵を出さない


def test_outbound_Artifact_で出す_file_と_files_の中の鍵も止める(env, tmp_path):
    key = FAKE_KEYS["GitHub のトークン"]
    (tmp_path / "r.html").write_text("<p>報告</p><!-- %s -->" % key, encoding="utf-8")
    (tmp_path / "ok.html").write_text("<p>報告</p>", encoding="utf-8")
    (tmp_path / "d.json").write_text(json.dumps({"k": key}), encoding="utf-8")
    assert "鍵・認証情報の形" in deny_reason(env, publish("r.html", cwd=str(tmp_path)))
    assert "鍵・認証情報の形" in deny_reason(env, publish("ok.html", cwd=str(tmp_path), files={"data/d.json": "d.json"}))
    assert not denied(env, publish("ok.html", cwd=str(tmp_path)))


@pytest.mark.parametrize("payload", [
    tool(SEND, session_id="session_x", message="PR #31 の CHANGELOG の衝突は main を merge して直した。先端 1a21016e8983。"),
    tool("mcp__github__create_pull_request", title="作り物", body="鍵は環境の秘密に入れた（値は書かない）。sk-ant- で始まる形を止める。"),
    tool("mcp__notion__notion-fetch", id="https://example.invalid/page"),
    tool("Bash", command="echo " + FAKE_KEYS["GitHub のトークン"]),     # 外へ渡す道具でない（返事・Bash は別の守り）
])
def test_outbound_鍵の無い入力と外へ渡さない道具は通す(env, payload):
    assert not denied(env, payload)


def test_outbound_作り物の見本は値の表で外せ_鍵の正本が無ければ止まる(env, tmp_path):
    key = FAKE_KEYS["AWS の鍵 ID"]
    p = tool(SEND, session_id="session_x", message="見本の鍵 %s の形" % key)
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    (proj / "config").mkdir()
    (proj / "config" / "skill-values.json").write_text(
        json.dumps({"guard": {"outbound_secret_allow": ["^" + key + "$"]}}), encoding="utf-8")
    assert not denied(env, p)
    gone = dict(env, AF_PUBLIC_GUARD=str(tmp_path / "無い.py"))
    assert "照らせない" in deny_reason(gone, tool(SEND, session_id="session_x", message="ふつうの文"))


@pytest.mark.parametrize("msg", [
    "#3 やって",
    "E02 の件、お願いします。",
    "了解しました。\nQ202611-67 の対応を進めて",
    "PR #31 merge して",
    "#616 と #617 も",
])
@pytest.mark.parametrize("name", [SEND, "SendMessage", CREATE])
def test_outbound_番号だけで中身の名の無い頼みは送る前に止める(env, msg, name):
    p = tool(name, message=msg, prompt=msg, title="🤖 作り物の作業")
    why = deny_reason(env, p)
    assert "番号だけで中身の名の無い文" in why and "直し方" in why


@pytest.mark.parametrize("msg", [
    "#3（請求書の送り先を顧客ごとに変える直し）を進めて",
    "PR #31 の CHANGELOG の衝突を直して",
    "E02・E03 の件（請求書の宛先の誤り）を直して",
    "session_011P2AMEYhnqWec1SQkBtQxp へ返す",
    "2026-11-19 に合流した。v0.4.15 で入った。",
    "請求書の送り先を顧客ごとに変える直しを進めて",
    "https://github.com/example/repo/pull/3 を見て",
])
def test_outbound_番号に名や中身が添えてあれば通す(env, msg):
    assert not denied(env, tool(SEND, session_id="session_x", message=msg))


def test_outbound_番号だけの頼みは値の表で外せる(env):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    (proj / "config").mkdir()
    (proj / "config" / "skill-values.json").write_text(
        json.dumps({"guard": {"number_request_exempt": ["^#3 やって$"]}}), encoding="utf-8")
    assert not denied(env, tool(SEND, message="#3 やって"))
    assert denied(env, tool(SEND, message="E02 の件"))


@pytest.mark.parametrize("payload, want", [
    (tool(SET_TITLE, session_id="s", title="作り物の作業"), "種類"),
    (tool(SET_TITLE, session_id="s", title="⏳🤖 作り物の作業"), "種類"),
    (tool(SET_TITLE, session_id="s", title="🤖❓"), "作業名が無い"),
    (tool(SET_TITLE, session_id="s", title="🙋✅ 作り物の相談"), "✅ は付けない"),
    (tool(CREATE, title="🤖 手: 作り物の設定", prompt="目的 手順 済んだ目印 済んだ後"), "手の窓の題は"),
    (tool(CREATE, title="🙋⏳ 手:", prompt="目的 手順 済んだ目印 済んだ後"), "何を頼むかが無い"),
    (tool(CREATE, title="🙋⏳ 手: 作り物の設定", prompt="目的: 作り物の鍵を入れる\n手順: 画面で貼る"), "済んだ目印・済んだ後"),
])
def test_outbound_題の形と手の窓の4欄が崩れていれば出す前に止める(env, payload, want):
    why = deny_reason(env, payload)
    assert "決まりの形でない" in why and want in why


@pytest.mark.parametrize("payload", [
    tool(SET_TITLE, session_id="s", title="🤖 書く: 作り物の作業"),
    tool(SET_TITLE, session_id="s", title="🙋❓ 作り物の相談"),
    tool(SET_TITLE, session_id="s", title="🤖✅ 作り物の作業"),
    tool(CREATE, title="🤖⏳ 作り物のレビュー", prompt="作り物の PR を見る"),
    tool(CREATE, prompt="題の無い窓立て"),
    tool(CREATE, title="🙋⏳ 手: 作り物の設定",
         prompt="①目的: 作り物 ②手順: 貼る ③済んだ目印: 出る ④済んだ後: 返す"),
])
def test_outbound_決まりの形の題と4欄の揃った手の窓は通す(env, payload):
    assert not denied(env, payload)


def test_outbound_題の形の見分けは_session_watch_の正本を直に呼ぶ(env, tmp_path):
    """正本の title_shape を外すと照らさなくなる＝写しを持っていない。"""
    fake = tmp_path / "session_watch.py"
    fake.write_text("import re\nHAND_TITLE=re.compile('^手')\nHAND_PARTS=()\n"
                    "def title_shape(t): return ['作り物の正本が止めた']\n"
                    "def split_title(t): return (None, None, t)\n", encoding="utf-8")
    why = deny_reason(dict(env, AF_SESSION_WATCH=str(fake)), tool(SET_TITLE, session_id="s", title="🤖 作り物"))
    assert "作り物の正本が止めた" in why


def test_outbound_正本の在り処は_repo_の形と入れた_plugin_の形の両方で見つかる(tmp_path):
    sys.path.insert(0, str(PLUGIN / "scripts"))
    try:
        import guard_common as G
    finally:
        sys.path.pop(0)
    assert G.foundation_file(os.path.join("public-guard", "guard.py")) == str(ROOT / "public-guard" / "guard.py")
    assert G.sibling_plugin_file("session-watch", os.path.join("scripts", "session_watch.py")) == \
        str(ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py")
    plugins = tmp_path / "plugins"
    guard_root = plugins / "cache" / "market" / "guard" / "aaa"
    guard_root.mkdir(parents=True)
    pg = plugins / "marketplaces" / "market" / "public-guard" / "guard.py"
    pg.parent.mkdir(parents=True)
    pg.write_text("#", encoding="utf-8")
    sw = plugins / "cache" / "market" / "session-watch" / "aaa" / "scripts" / "session_watch.py"
    sw.parent.mkdir(parents=True)
    sw.write_text("#", encoding="utf-8")
    assert G.foundation_file(os.path.join("public-guard", "guard.py"), str(guard_root)) == str(pg)
    assert G.sibling_plugin_file("session-watch", os.path.join("scripts", "session_watch.py"), str(guard_root)) == str(sw)


# ── 見る口の外: Artifact の files の問いのページ・Bash で試験へ書く有料の上流 ──
def test_qa_page_files_で足した問いのページも見る(env, tmp_path):
    (tmp_path / "index.html").write_text("<p>表紙</p>", encoding="utf-8")
    (tmp_path / "kakunin.html").write_text(STATE_PAGE, encoding="utf-8")
    env = dict(env, AF_QA_CHECK=str(tmp_path / "無い.mjs"))
    for files in ({"q.html": "kakunin.html"}, {"q.html": {"from": "kakunin.html"}}, [{"path": "kakunin.html"}]):
        assert "緑を確かめられない" in deny_reason(env, publish("index.html", cwd=str(tmp_path), files=files)), files
    assert "緑を確かめられない" not in deny_reason(env, publish("index.html", cwd=str(tmp_path),
                                                                files={"a.html": {"artifact": "https://example.invalid/a", "path": "a.html"}}))
    assert not denied(env, publish("index.html", cwd=str(tmp_path), files={"a.html": None}))


@pytest.mark.parametrize("cmd", [
    "cat > tests/test_llm.py <<'EOF'\nimport os\nKEY = os.environ['" + "OPENAI" + "_API_KEY']\nEOF",
    "echo 'URL = \"https://api." + "anthropic.com/v1\"' >> tests/conftest.py",
    "printf 'x' | tee -a e2e/run.spec.ts && echo " + "GEMINI" + "_API_KEY",
    "sed -i 's/FAKE/" + "ANTHROPIC" + "_API_KEY/' tests/test_a.py",
])
def test_paid_upstream_Bash_で試験へ書く有料の上流も止める(env, cmd):
    assert "有料の上流" in deny_reason(env, bash(cmd))


@pytest.mark.parametrize("cmd", [
    "grep -rn " + "OPENAI" + "_API_KEY tests/",
    "cat > src/client.py <<'EOF'\nKEY = '" + "OPENAI" + "_API_KEY'\nEOF",
    "cat > tests/test_llm.py <<'EOF'\n# PAID_UPSTREAM_GUARD\nKEY = '" + "OPENAI" + "_API_KEY'\nEOF",
    "pytest tests/ 2>&1 > /tmp/out.txt && echo " + "OPENAI" + "_API_KEY",
])
def test_paid_upstream_Bash_の読みと試験の外への書き込みと関所つきは通す(env, cmd):
    assert not denied(env, bash(cmd))
