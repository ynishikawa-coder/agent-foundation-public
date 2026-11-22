"""守りの hook の pr_text（GitHub へ出す前の PR の題・本文・コメントを照らす）が約束どおり効くかを見る。

判定の形・整地の欄・窓の id・公開の repo に置かない物を、作り物の入力で入口（guard.py pre）から当てる。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "plugins" / "guard" / "scripts" / "guard.py"


@pytest.fixture
def env(tmp_path):
    """試験ごとに一時の箱・台帳の置き場・repo の根を分ける（実の印を汚さない）。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    (tmp_path / "scratch").mkdir()
    e = {k: v for k, v in os.environ.items() if not k.startswith(("AF_", "SKILL_VALUES", "CLAUDE_PROJECT_DIR"))}
    e.update({"AF_GUARD_TMP": str(tmp_path / "tmp"), "AF_GUARD_STATE": str(tmp_path / "state"),
              "CLAUDE_PROJECT_DIR": str(proj), "PYTHONDONTWRITEBYTECODE": "1",
              "TMPDIR": str(tmp_path / "scratch"),
              # 判定を出す窓の本物の id の記録（harness が窓の環境に置く cse_<x>）。試験はレビューの窓に固定する
              "CLAUDE_CODE_REMOTE_SESSION_ID": "cse_" + REVIEWER[len("session_"):]})
    return _fake_gh(e)                       # どの試験も実の GitHub へ出ない（整地の雛形も作り物の gh から引く）


def deny_reason(env, payload):
    p = subprocess.run([sys.executable, str(GUARD), "pre"], input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else {}
    return out.get("permissionDecisionReason", "") if out.get("permissionDecision") == "deny" else ""


CHECKER = ROOT / "plugins" / "checker" / "scripts"
CLEANUP_TPL = ROOT / "plugins" / "dev-flow" / "skills" / "preimpl-cleanup" / "整地受領証.template.md"
WRITER = "session_01AAAAAAAAAAAAAAAAAAAAAAAA"
REVIEWER = "session_01BBBBBBBBBBBBBBBBBBBBBBBB"
STRANGER = "session_01CCCCCCCCCCCCCCCCCCCCCCCC"


def gh(tool, owner="fake-owner", repo="fake-private", **ti):
    return {"tool_name": "mcp__github__" + tool, "session_id": "s1",
            "tool_input": {"owner": owner, "repo": repo, **ti}}


FAKE_HEAD = "0123456789ab" + "c" * 28


def _fake_gh(env, head=FAKE_HEAD, writer=WRITER, fail=False, commits=None, total=None, templates=None,
             pr_head_repo="fake-owner/fake-private"):
    """作り物の gh を PATH の頭に置く。実の GitHub へは出ない。呼ばれた引数は 1 回 1 行で gh.log に残す（`gh_calls`）。
    PR を引く呼び出しには先端と本文の `書いた窓:`（写し）を、commit を引く呼び出しには各 commit の説明（`Claude-Session:` の
    記録。既定は書いた窓の 1 本・1 本ごとに JSON の 1 行）を返す。commits の None の要素は記録の無い commit。
    total は PR の commit の数（既定は返す commit の数。GitHub が commit の一覧を 250 本で切る時の作り物に、返す数より大きくする）。
    templates は整地の雛形を引く呼び出し（contents）への答え: [(引数に含む字, 返す file か None＝HTTP 404)] を上から当てる
    （既定は全部へ土台の雛形）。PR の head を引く呼び出しには pr_head_repo と先端を返す。"""
    bindir = Path(env["CLAUDE_PROJECT_DIR"]).parent / "fakebin"
    bindir.mkdir(exist_ok=True)
    gh_path = bindir / "gh"
    body = "書いた窓: %s\\n" % writer if writer else "作り物の本文\\n"
    commits = [WRITER] if commits is None else commits
    msgs = "".join(json.dumps("作り物の commit\n\n" + ("Claude-Session: https://claude.ai/code/%s\n" % c if c else ""),
                              ensure_ascii=False).replace("\\", "\\\\") + "\\n" for c in commits)
    total = len(commits) if total is None else total
    templates = [("", CLEANUP_TPL)] if templates is None else templates
    tpl = "".join('    *"%s"*) %s ;;\n' % (key, ("cat '%s'" % path) if path else "echo 'gh: Not Found (HTTP 404)' >&2; exit 1")
                  for key, path in templates)
    log = bindir / "gh.log"
    gh_path.write_text("#!/bin/sh\nprintf '%%s\\n' \"$*\" >> '%s'\n" % log + ("echo 'not found' >&2; exit 1\n" if fail else
                       'case "$*" in *"/contents/"*)\n  case "$*" in\n%s    *) echo \'gh: Not Found (HTTP 404)\' >&2; exit 1 ;;\n  esac ;;\n'
                       '  *"head.repo"*) printf \'%%s\\n%%s\' \'%s\' \'%s\' ;;\n'
                       '  *"/commits"*) printf \'%s\' ;;\n  *) printf \'%%s\\n%%s\\n%%s\' \'%s\' \'%s\' \'%s\' ;;\nesac\n'
                       % (tpl, pr_head_repo, head, msgs, head, total, body)), encoding="utf-8")
    gh_path.chmod(0o755)
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    return env


def gh_calls(env):
    log = Path(env["CLAUDE_PROJECT_DIR"]).parent / "fakebin" / "gh.log"
    return log.read_text(encoding="utf-8").split("\n") if log.exists() else []


def verdict_comment(judged="green", head="0123456789ab", fail=None, stop=False, line1=None):
    """review-pr の見る点の表から組んだ判定のコメント（点を写さず、表を直に読む）。"""
    sys.path.insert(0, str(CHECKER))
    import verdict_form  # noqa: E402
    points = verdict_form.load_points()
    rows = []
    for no, name in sorted(points.items()):
        val = "書いた窓 %s ≠ この窓" % WRITER if no == 3 else ("fail" if no == fail else "pass")
        if val == "pass" and name == verdict_form.PICTURE:                         # 全体の絵の pass は照らした版を書く形だけ
            val = "pass（差なし・版 2026-11-19.1）"
        rows.append("- %d %s: %s" % (no, name, val))
    first = line1 or "レビューした窓: %s 判定: %s" % (REVIEWER, judged)
    fix = [verdict_form.ROOT_CAUSE] if judged == "red" else []
    lines = [first] + (["見た先端: " + head] if head else []) + ["", "## verdict", judged] + fix + ["", "## 点"] + rows
    cards, steps = verdict_form.load_cards()                                    # 札と段も正本（SKILL.md）から道具で読む
    later = [c for c in cards if c != verdict_form.STOP_CARD][0]
    lines += ["", "## 所見", "- [%s｜%s] 作り物の欠け" % (verdict_form.STOP_CARD, steps[0]) if stop else "- [%s｜%s] 作り物の残り" % (later, steps[0])]
    return "\n".join(lines) + "\n"


def cleanup_body(extra=""):
    return ("書いた窓: %s\njob: 20261119-fake\n触る path: a.py\n検査: check_all: 緑 (1 本)\n\n"
            "## 何をどう変えたか\n作り物の直し。\n\n## 整地（根治の段）\n\n## 1. 意図\n作り物の意図。\n\n## 2. 課題\n作り物の課題。\n\n"
            "## 3. 原因と同じ原因の他の問題\n**原因**: 作り物。\n\n## 4. 解決（足す物・畳む物・注入の試験と残る穴）\n**足す物**: 作り物。\n\n"
            "## 5. 未来\n作り物の未来。\n%s" % (WRITER, extra))


PR_BAD = [
    ("判定の先端の行が無い", gh("add_issue_comment", issue_number=1, body=verdict_comment(head="")), "[verdict]", "見た先端"),
    ("止めるが在るのに green", gh("add_issue_comment", issue_number=1, body=verdict_comment(stop=True)), "[verdict]", "判定は red"),
    ("点に fail が在るのに green", gh("pull_request_review_write", pullNumber=1, method="create", event="COMMENT",
                                     body=verdict_comment(fail=8)), "[verdict]", "判定は red"),
    ("名乗りが session id でない", gh("add_issue_comment", issue_number=1,
                                    body=verdict_comment(line1="レビューした窓: %s の中の助手 判定: green" % REVIEWER)),
     "[verdict]", "1 行目"),
    ("1 行目の名乗りが無く節だけ在る判定", gh("add_issue_comment", issue_number=1,
                                          body="判定: green\n\n## verdict\ngreen\n\n## 所見\n- [直った｜実装] 作り物\n"),
     "[verdict]", "1 行目"),
    ("前置きの後の名乗りの行", gh("add_issue_comment", issue_number=1,
                                  body="再レビューです。\nレビューした窓: %s 判定: green\n見た先端: 0123456789ab\n" % REVIEWER),
     "[verdict]", "1 行目"),
    ("### Verdict の見出し", gh("add_issue_comment", issue_number=1,
                                body="再レビューです。\n\n### Verdict\ngreen\n"), "[verdict]", "1 行目"),
    ("整地の欄が無い", gh("create_pull_request", title="作り物", head="b", base="main",
                         body="job: x\n\n## 何をどう変えたか\n作り物。\n"), "[cleanup]", "1. 意図"),
    ("整地の見出しが古い名", gh("create_pull_request", title="作り物", head="b", base="main",
                              body=cleanup_body().replace("## 3. 原因と同じ原因の他の問題", "## 3. 同じ原因から起きている他の問題")),
     "[cleanup]", "3. 原因と同じ原因の他の問題"),
    ("整地が古い 4 段の見出し", gh("create_pull_request", title="作り物", head="b", base="main",
                                body=cleanup_body().replace("## 1. 意図\n作り物の意図。\n\n## 2. 課題\n作り物の課題。", "## 1. 問題\n作り物の問題。")),
     "[cleanup]", "1. 意図"),
    ("雛形の〔…〕が残る", gh("update_pull_request", pullNumber=1,
                            body=cleanup_body("\n〔直した後、1 欄の意図が果たされ、同じ課題と 3 欄の他の問題が起きない姿〕\n")), "[cleanup]", "〔…〕"),
    ("不要の訳が無い", gh("create_pull_request", title="作り物", head="b", base="main", body="## 何をどう変えたか\n誤字。\n整地: 不要\n"),
     "[cleanup]", "1. 意図"),
    ("不要の訳が雛形のまま", gh("create_pull_request", title="作り物", head="b", base="main",
                              body="## 何をどう変えたか\n誤字。\n整地: 不要（<なぜ要らないか>）\n"), "[cleanup]", "1. 意図"),
    ("見出しが注記の中だけ", gh("create_pull_request", title="作り物", head="b", base="main",
                              body="## 何をどう変えたか\n作り物。\n<!--\n## 1. 意図\n## 2. 課題\n## 3. 原因と同じ原因の他の問題\n## 4. 解決\n## 5. 未来\n"
                                   "整地: 不要（作り物）\n-->\n"), "[cleanup]", "1. 意図"),
    ("本文に窓の id がそのまま", gh("create_pull_request", title="作り物", head="b", base="main",
                                  body=cleanup_body("\n- 残り — 直す窓 %s\n" % STRANGER)), "[words]", STRANGER),
    ("題に窓の id", gh("update_pull_request", pullNumber=1, title="作り物 %s の続き" % STRANGER), "[words]", "PR の題"),
]


@pytest.mark.parametrize("name,payload,code,want", PR_BAD, ids=[c[0] for c in PR_BAD])
def test_pr_text_崩れた判定と欄の欠けた本文と窓の_id_は出す前に止め直し方を返す(env, name, payload, code, want):
    _fake_gh(env)
    why = deny_reason(env, payload)
    assert code in why and want in why, why
    assert "直し方" in why and "文はまだ GitHub に出ていない" in why and "誤って止めた時" in why


PR_GOOD = [
    ("形の合う判定", gh("add_issue_comment", issue_number=1, body=verdict_comment())),
    ("止めるの在る red", gh("add_issue_comment", issue_number=1, body=verdict_comment(judged="red", stop=True))),
    ("判定でない普通のコメント", gh("add_issue_comment", issue_number=1, body="作り物の確かめを足しました。判定は後で別の窓が付けます。")),
    ("文中に判定の語を含む普通のコメント", gh("add_issue_comment", issue_number=1, body="前回の判定: green を受けて main へ入れます。")),
    ("レビューした窓は…で始まる普通の文", gh("add_issue_comment", issue_number=1, body="レビューした窓は red を付けました。直します。")),
    ("前の判定を引いた返事", gh("add_issue_comment", issue_number=1,
                              body="> レビューした窓: %s 判定: red\n\n直しました。見直しを頼みます。" % REVIEWER)),
    ("2 行目に判定の語を含む返事", gh("add_issue_comment", issue_number=1, body="直しました。\n判定: red の理由は直りました。\n見直しを頼みます。")),
    ("整地の欄の揃った本文", gh("create_pull_request", title="作り物", head="b", base="main", body=cleanup_body())),
    ("見出しが ### でも", gh("create_pull_request", title="作り物", head="b", base="main",
                           body=cleanup_body().replace("\n## 1.", "\n### 1.").replace("\n## 5.", "\n### 5."))),
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
    _fake_gh(env)
    assert deny_reason(env, payload) == ""


def test_pr_text_道具の名は_MCP_の_server_の名を問わず末尾で見る(env):
    p = gh("create_pull_request", title="作り物", head="b", base="main", body="## 何をどう変えたか\n作り物。\n")
    p["tool_name"] = "mcp__0a1b2c3d__create_pull_request"
    assert "[cleanup]" in deny_reason(env, p)
    p["tool_name"] = "mcp__github__create_pull_request_review"
    assert deny_reason(env, p) == ""


def _template(tmp_path, name, old="## 5. 未来", new="## 5. 作り物の新しい欄"):
    tpl = tmp_path / name
    tpl.write_text(CLEANUP_TPL.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    return tpl


def _contents_calls(env):
    return [c for c in gh_calls(env) if "/contents/" in c]


def test_pr_text_整地の見出しは出す先の_repo_の_PR_の枝の雛形を直に読む(env, tmp_path):
    """雛形は PR を出す先の repo の head の枝から引く。窓の作業の木（CLAUDE_PROJECT_DIR）に置いた別の雛形は読まない
    （窓に入った土台の版の古い型で、先の repo の今の型の本文を止めない・古い型の本文を通さない）。"""
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    stale = proj / "plugins" / "dev-flow" / "skills" / "preimpl-cleanup" / "整地受領証.template.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("## 1. 問題\n## 2. 原因\n## 3. 解決\n## 4. 未来\n", encoding="utf-8")   # 窓の作業の木の古い 4 段
    _fake_gh(env, templates=[("ref=b", _template(tmp_path, "枝.md"))])
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=cleanup_body()))
    assert "5. 作り物の新しい欄" in why and "1. 問題" not in why, why
    assert any("repos/fake-owner/fake-private/contents/" in c and "ref=b" in c for c in _contents_calls(env))
    # 同じ枝の雛形どおりの本文は通る（作業の木の古い 4 段では照らさない）
    ok = cleanup_body().replace("## 5. 未来", "## 5. 作り物の新しい欄")
    assert deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=ok)) == ""


def test_pr_text_書き替えは_PR_の_head_を_GitHub_から引いてその版の雛形で照らす(env, tmp_path):
    sha = "ab" * 20
    _fake_gh(env, head=sha, pr_head_repo="someone/fake-private", templates=[("ref=" + sha, _template(tmp_path, "head.md"))])
    why = deny_reason(env, gh("update_pull_request", pullNumber=7, body=cleanup_body()))
    assert "5. 作り物の新しい欄" in why, why
    assert any("repos/someone/fake-private/contents/" in c and "ref=" + sha in c for c in _contents_calls(env))


def test_pr_text_fork_の枝は_fork_の_repo_から読む(env, tmp_path):
    _fake_gh(env, templates=[("repos/someone/fake-private/", _template(tmp_path, "fork.md"))])
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="someone:b", base="main", body=cleanup_body()))
    assert "5. 作り物の新しい欄" in why, why


def test_pr_text_雛形を持たない_repo_は土台の既定の枝の雛形で照らす(env, tmp_path):
    found = "ynishikawa-coder/agent-foundation-public"
    _fake_gh(env, templates=[("repos/fake-owner/", None), ("repos/%s/" % found, _template(tmp_path, "土台.md"))])
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=cleanup_body()))
    assert "5. 作り物の新しい欄" in why, why
    calls = [c for c in _contents_calls(env) if found in c]
    assert calls and all("ref=" not in c for c in calls)                       # 既定の枝（窓が入れる main の先端）


@pytest.mark.parametrize("case", ["土台の枝に雛形が無い", "GitHub から引けない", "gh が無い"])
def test_pr_text_雛形を引けなければ窓の版で照らさず止める(env, tmp_path, case):
    found = dict(owner="ynishikawa-coder", repo="agent-foundation-public")
    payload = gh("create_pull_request", title="作り物", head="b", base="main", body=cleanup_body(), **found)
    if case == "土台の枝に雛形が無い":
        _fake_gh(env, templates=[("", None)])
    elif case == "GitHub から引けない":
        _fake_gh(env, fail=True)
    else:
        env["PATH"] = str(Path(env["CLAUDE_PROJECT_DIR"]).parent / "空")
    why = deny_reason(env, payload)
    assert "[cleanup]" in why and "引けず" in why, why


def test_pr_text_試験の口の雛形の_path_が無ければ止める(env, tmp_path):
    env["AF_CLEANUP_TEMPLATE"] = str(tmp_path / "無い.md")
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=cleanup_body()))
    assert "[cleanup]" in why and "無い.md" in why


LAYOUT_BAD = [
    ("段の順を入れ替えた", cleanup_body().replace("## 1. 意図\n作り物の意図。\n\n## 2. 課題\n作り物の課題。",
                                              "## 2. 課題\n作り物の課題。\n\n## 1. 意図\n作り物の意図。"), "順が雛形と違う"),
    ("同じ見出しが 2 つ", cleanup_body("\n## 3. 原因と同じ原因の他の問題\n作り物の重ね。\n"), "順が雛形と違う"),
    ("整地の節の外に置いた", cleanup_body().replace("## 整地（根治の段）\n", "## 整地（根治の段）\n\n## 何をした\n作り物。\n"), "整地の節の外"),
    ("一部だけ節の外", cleanup_body().replace("## 5. 未来", "## 畳んだ古い物\nなし。\n\n## 5. 未来"), "5. 未来"),
    ("整地の見出しが無い", cleanup_body().replace("## 整地（根治の段）\n", ""), "整地（根治の段）` の見出しが無い"),
    ("節の見出しより浅い段の見出しで節が切れる", cleanup_body().replace("## 整地（根治の段）", "### 整地（根治の段）")
     .replace("## 4. 解決", "## 別の話\n作り物。\n\n## 4. 解決"), "整地の節の外"),
]


@pytest.mark.parametrize("name,body,want", LAYOUT_BAD, ids=[c[0] for c in LAYOUT_BAD])
def test_pr_text_整地の見出しの順と置き場が雛形と違えば止める(env, name, body, want):
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=body))
    assert "[cleanup]" in why and want in why, why


def test_pr_text_整地の節の後に続く節が在っても通る(env):
    body = cleanup_body("\n## 畳んだ古い物\nなし。\n\n## 検証\n作り物。\n\n## 残り（原因の台帳の行）\nなし\n")
    assert deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=body)) == ""
    nested = body.replace("\n## 1.", "\n### 1.").replace("\n## 2.", "\n### 2.").replace("\n## 3.", "\n### 3.") \
        .replace("\n## 4.", "\n### 4.").replace("\n## 5.", "\n### 5.")
    assert deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=nested)) == ""


def test_pr_text_判定の形は道具を直に呼び無ければ止める(env, tmp_path):
    _fake_gh(env)
    env["AF_VERDICT_FORM"] = str(tmp_path / "無い.py")
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body=verdict_comment()))
    assert "[verdict]" in why and "見つからず" in why
    broken = tmp_path / "verdict_form.py"
    broken.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    env["AF_VERDICT_FORM"] = str(broken)
    assert "壊れた" in deny_reason(env, gh("add_issue_comment", issue_number=1, body=verdict_comment()))


def test_pr_text_誤って止まる_repo_は値の表で外せる(env, tmp_path):
    _fake_gh(env)
    table = tmp_path / "values.json"
    env["SKILL_VALUES"] = str(table)
    table.write_text(json.dumps({"guard": {"pr_cleanup_exempt_repos": ["^fake-owner/fake-private$"],
                                           "pr_words_exempt_repos": ["^fake-owner/.*$"]}}), encoding="utf-8")
    body = "## 何をどう変えたか\n直す窓 %s\n" % STRANGER
    assert deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=body)) == ""
    assert "[cleanup]" in deny_reason(env, gh("create_pull_request", repo="other", title="作り物", head="b", base="main", body=body))
    # 判定の形は外す口を持たない
    assert "[verdict]" in deny_reason(env, gh("add_issue_comment", issue_number=1, body=verdict_comment(head="")))


def _fake_public_repo(proj, deny_word, url="https://github.com/fake-owner/fake-public.git"):
    """作り物の公開の repo の取り出し（origin が owner/repo・workflow が action public-guard を呼ぶ）。"""
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    subprocess.run(["git", "-C", str(proj), "remote", "add", "origin", url], check=True)
    wf = proj / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "public-guard.yml").write_text(
        "on: [pull_request]\njobs:\n  public-guard:\n    steps:\n"
        "      - uses: ynishikawa-coder/agent-foundation-public/public-guard@main\n"
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
    del env["AF_PUBLIC_GUARD"]
    (Path(env["CLAUDE_PROJECT_DIR"]) / "data" / "deny.txt").unlink()
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめ", repo="fake-public"))
    assert "[public]" in why and "置かない語の表" in why and "無く" in why


def test_pr_text_手元に取り出しの無い公開の_repo_は値の表で足せる(env, tmp_path):
    table = tmp_path / "values.json"
    env["SKILL_VALUES"] = str(table)
    p = gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, repo="far-public")
    assert deny_reason(env, p) == ""
    table.write_text(json.dumps({"guard": {"public_repos_extra": ["^fake-owner/far-public$"]}}), encoding="utf-8")
    assert "[public]" in deny_reason(env, p)


def test_pr_text_照らしの途中で壊れたら黙って通さず止める(env, tmp_path):
    """一時の置き場に書けない等で照らしが壊れても、見る道具なら止める（入口が例外を通す側に倒すため）。"""
    blocker = tmp_path / "置き場でない"
    blocker.write_text("file なので dir を作れない", encoding="utf-8")
    env["AF_GUARD_TMP"] = str(blocker)
    _fake_public_repo(Path(env["CLAUDE_PROJECT_DIR"]), PUBLIC_WORD)
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめ", repo="fake-public"))
    assert "[broken]" in why and "照らせない文は出さない" in why
    assert deny_reason(env, gh("create_branch", branch="b", from_branch="main")) == ""


def test_pr_text_判定の材料は_PR_から引き_引けなければ止め_先端と書いた窓を照らす(env):
    """書いた窓と先端は GitHub の PR から引いて verdict_form.py に渡す（欠けたまま通さない・判定の文の言い分を信じない）。"""
    p = gh("add_issue_comment", issue_number=1, body=verdict_comment())
    _fake_gh(env)
    assert deny_reason(env, p) == ""
    _fake_gh(env, head="fedcba9876543210" + "0" * 24)             # 見た後に push があった
    assert "[verdict]" in deny_reason(env, p) and "先端" in deny_reason(env, p)
    _fake_gh(env, writer=REVIEWER)                                 # 書いた窓が自分の PR に判定を付けた
    assert "[verdict]" in deny_reason(env, p)
    _fake_gh(env, writer="")                                       # PR 本文に書いた窓が無い（写しが無くても記録で照らす）
    assert deny_reason(env, p) == ""
    _fake_gh(env, commits=[None])                                  # commit に書き手の記録が無い（本文の写しだけでは決めない）
    assert "判定の材料" in deny_reason(env, p) and "Claude-Session" in deny_reason(env, p)
    _fake_gh(env, fail=True)                                       # PR を引けない
    assert "判定の材料" in deny_reason(env, p)
    env["PATH"] = str(Path(env["CLAUDE_PROJECT_DIR"]).parent / "空")   # gh が無い
    why = deny_reason(env, p)
    assert "判定の材料" in why and "gh" in why
    assert deny_reason(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめを足しました")) == ""


def test_pr_text_の値の鍵は値の表の知らない鍵の見張りが知っている():
    """値の表に pr_text の鍵を書いても、知らない鍵の見張り（values_keys）が止めない（鍵の正本は値の表の 1 本の口の鍵の一覧 skill-values/schema.json）。"""
    sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
    import values_keys  # noqa: E402
    table = {"guard": {"pr_cleanup_exempt_repos": ["^作り物/repo$"], "pr_words_exempt_repos": [],
                       "public_repos_extra": ["^作り物/公開$"]}}
    assert values_keys.unknown(table) == []
    got = values_keys.unknown({"guard": {"pr_作り物の知らない鍵": []}})
    assert len(got) == 1 and got[0].startswith("guard.pr_作り物の知らない鍵 は知らない鍵")


def test_pr_text_の照らす物は_plugin_の説明と一覧に欠けずに書いてある():
    """入れる前に読む説明（plugin.json）と一覧（plugins/README.md）から、照らす 4 つの物が落ちると赤（merge で縮んだ事がある）。"""
    desc = json.loads((ROOT / "plugins" / "guard" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["description"]
    assert "GitHub へ出す前の PR の文（判定の形・整地の欄・窓の id・公開の repo に置かない物）" in desc
    readme = [ln for ln in (ROOT / "plugins" / "README.md").read_text(encoding="utf-8").splitlines() if ln.startswith("- **guard**")]
    assert len(readme) == 1 and "GitHub へ出す前の PR の文" in readme[0]
