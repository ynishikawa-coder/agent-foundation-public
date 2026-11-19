"""PR の文の守り（pr_text）の穴を、誤りの類をわざと入れて拒む試験（原因の台帳の pr_text の行）。

- 判定の見分けを正本の 1 行目の形（verdict_form の LINE1）から読み、崩れた名乗り（太字・「:」の抜け・「greenです」）も判定と見る
- 物差しを回した跡（点 4 の最後の行が、この窓か助手の道具の結果に在る）
- 窓の id の照らしをコメントと issue にも当てる（判定の名乗り・点 3・連絡板の冒頭の欄は除く）
- 公開かは GitHub の visibility から引く（取り出しに頼らない）
- 「整地: 不要」は振る舞いの file を触らない PR だけ
- 連絡板の書き方（冒頭の 1 行・新しい issue を立てない）は連絡板の本文が正本
- Bash の git push で出す commit の説明と名義を公開の検査に通す
- 手元の commit していない正本の書き替えで照らさない
- PR の番号は数だけ・引けなかった時の文に並びの形を出さない
"""
import json
import subprocess
from pathlib import Path

from test_pr_text import (CHECKER, MAIL, PUBLIC_WORD, REVIEWER, STRANGER, WRITER, _fake_gh, _fake_public_repo,
                          cleanup_body, deny_reason, env, gh, verdict_comment, with_transcript)  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent


# ── 判定の見分け ──
def test_崩れた名乗りも判定と見て形を照らす(env):
    _fake_gh(env)
    for line1 in ("**レビューした窓**: %s **判定**: green" % REVIEWER,
                  "レビューした窓 %s 判定: green" % REVIEWER,                     # 名乗りの「:」を外す注入
                  "- レビューした窓: %s 判定: greenです" % REVIEWER):
        body = "%s\n見た先端: 0123456789ab\n" % line1                  # verdict の見出しを置かない（見出しで見分けさせない）
        why = deny_reason(env, gh("add_issue_comment", issue_number=1, body=body))
        assert "[verdict]" in why and "1 行目" in why, line1


def test_窓の_id_の無い判定の語の文は判定と見ない(env):
    _fake_gh(env)
    assert deny_reason(env, gh("add_issue_comment", issue_number=1, body="レビューした窓は判定: green を付けました")) == ""


def test_判定の見分けは_verdict_form_の_LINE1_を読み写さない():
    src = (ROOT / "plugins" / "guard" / "scripts" / "pr_text.py").read_text(encoding="utf-8")
    assert "VERDICT_LINE" not in src and "LINE1" in src


# ── 物差しの跡 ──
def test_物差しを回した跡が無い判定は止める(env, tmp_path):
    _fake_gh(env)
    p = gh("add_issue_comment", issue_number=1, body=verdict_comment())
    assert deny_reason(env, p) == ""
    why = deny_reason(env, with_transcript(env, p, results=("別の出力",)))
    assert "物差しの跡" in why
    sub = tmp_path / "t2"
    (sub / "subagents").mkdir(parents=True)
    (sub / "subagents" / "a.jsonl").write_text(json.dumps({"message": {"content": [
        {"type": "tool_result", "content": "check_all: 緑 (4 本)"}]}}) + "\n", encoding="utf-8")
    (tmp_path / "t2.jsonl").write_text("{}\n", encoding="utf-8")
    assert deny_reason(env, dict(p, transcript_path=str(tmp_path / "t2.jsonl"))) == ""   # 助手が回した跡も数える


# ── 窓の id（コメント・issue）──
def test_コメントと_issue_の窓の_id_も照らし_判定の名乗りと点_3_は数えない(env):
    _fake_gh(env)
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body="続きは %s の窓が持つ" % STRANGER))
    assert "[words]" in why and STRANGER in why
    assert "[words]" in deny_reason(env, gh("issue_write", method="create", title="作り物", body="窓 %s" % STRANGER))
    assert deny_reason(env, gh("add_issue_comment", issue_number=1, body=verdict_comment())) == ""


# ── 整地: 不要 ──
NOT_NEEDED = "## 何をどう変えたか\n誤字だけ。\n\n整地: 不要（振る舞いを変えない誤字の直しだけ）\n"


def test_整地不要は振る舞いの_file_を触る_PR_では止める(env):
    p = gh("create_pull_request", title="誤字", head="b", base="main", body=NOT_NEEDED)
    _fake_gh(env, files=("README.md",))
    assert deny_reason(env, p) == ""
    for f in ("plugins/guard/scripts/x.py", "plugins/x/skills/y/SKILL.md", "plugins/core/細目.md", "plugins/x/hooks/hooks.json"):
        _fake_gh(env, files=("README.md", f))
        why = deny_reason(env, p)
        assert "[cleanup]" in why and f in why, f
    _fake_gh(env, fail=True)
    assert "差分の file）を引けない" in deny_reason(env, gh("update_pull_request", pullNumber=1, body=NOT_NEEDED))


# ── 連絡板 ──
BOARD = "## 書き方\n- 冒頭の 1 行は必ず `窓: <session id> アカウント: <Javis|UTC>`。\n"


def board_repo():
    import re
    text = (ROOT / "plugins" / "core" / "細目.md").read_text(encoding="utf-8")
    return re.search(r"またぐ連絡[^\n]*?`([^`/]+)/([^`]+)`", text).groups()


def test_連絡板のコメントは本文の書き方の冒頭の行で書き_新しい_issue_を立てない(env):
    owner, repo = board_repo()
    _fake_gh(env, board=BOARD)
    ok = "窓: session_01AAAA アカウント: Javis\n作り物の連絡"
    assert deny_reason(env, gh("add_issue_comment", owner=owner, repo=repo, issue_number=2, body=ok)) == ""
    why = deny_reason(env, gh("add_issue_comment", owner=owner, repo=repo, issue_number=2, body="作り物の連絡"))
    assert "[board]" in why and "冒頭の 1 行" in why
    why = deny_reason(env, gh("issue_write", owner=owner, repo=repo, method="create", title="作り物", body=ok))
    assert "[board]" in why and "新しい issue" in why
    _fake_gh(env)                                     # 連絡板でない issue は形を見ない
    assert deny_reason(env, gh("add_issue_comment", owner=owner, repo=repo, issue_number=3, body="作り物の連絡")) == ""


# ── git push の commit の説明と名義 ──
def _repo_with_commit(proj, msg):
    _fake_public_repo(proj, PUBLIC_WORD)
    subprocess.run(["git", "-C", str(proj), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(proj), "-c", "user.name=作り物", "-c", "user.email=noreply@example.com",
                    "commit", "-qm", msg], check=True)


def test_公開の_repo_への_git_push_は_commit_の説明を出す前に照らす(env):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_gh(env, private={"fake-public": "false"})
    _repo_with_commit(proj, "%s の直し" % PUBLIC_WORD)
    bash = {"tool_name": "Bash", "session_id": "s1", "cwd": str(proj), "tool_input": {"command": "git push -u origin b"}}
    why = deny_reason(env, bash)
    assert "[public]" in why and "commit の説明と名義" in why and PUBLIC_WORD not in why
    why = deny_reason(env, dict(bash, cwd="/", tool_input={"command": "cd %s && git push origin b" % proj}))
    assert "[public]" in why
    _fake_gh(env)                                     # 非公開の repo へは照らさない
    assert deny_reason(env, bash) == ""
    assert deny_reason(env, dict(bash, tool_input={"command": "git status"})) == ""


# ── 手元の書き替え・番号・文 ──
def test_commit_していない手元の正本の書き替えでは照らさない(env):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    weak = proj / "plugins" / "checker" / "scripts"
    weak.mkdir(parents=True)
    (weak / "verdict_form.py").write_text((CHECKER / "verdict_form.py").read_text(encoding="utf-8")
                                          .replace("def check(text", "def _check(text") +
                                          "\ndef check(*a, **k):\n    return [], 0\n", encoding="utf-8")
    _fake_gh(env)
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body=verdict_comment(head="")))
    assert "[verdict]" in why and "見た先端" in why        # 緩めた手元の道具でなく、入れた正本で照らした


def test_PR_の番号は数だけ_引けない時の文に並びの形を出さない(env):
    _fake_gh(env)
    why = deny_reason(env, gh("add_issue_comment", issue_number="1/../../x", body=verdict_comment()))
    assert "数でない" in why
    _fake_gh(env, fail=True)
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body=verdict_comment()))
    assert "判定の材料" in why and "['" not in why
