"""窓の親の記録と人の頼みの印を、1 つの正本から直に読む注入の試験（台帳の 3 行: 最初の知らせ・本文の親窓の欄・人の印の写し）。

前の形:
  - 最初の知らせ（session-watch の remind_title）は、会話ログに頼みの行がまだ無い時に頼みの文しか読めず、子の窓と決めなかった。
  - PR 本文の頭の `親窓:` の欄は手で書いた写しで、どの道具も窓の親の記録と照らさず、窓の id の照らしからも外していた。
  - 人の頼みの印（origin.kind の human・person）を guard の guard_common と session-watch の session_watch の 2 か所に写していた。
今の形: 子の窓かの記録は guard_common.seeded_by_record の 1 か所（頼みの行の origin）。session_watch はそれを隣の正本として
直に読む。行がまだ無い最初の知らせでは子の窓と決めず、文が別の窓を指す時だけ get_session の parent_session_id で決めさせる
（窓の環境の `CLAUDE_CODE_CHILD_SESSION` は hook の子プロセス全部に付く印で見分けにならない＝test_child_session_mark.py）。`親窓:` の欄は畳んだ（親は get_session の記録）。
"""
import importlib.util
import json
from pathlib import Path

import pytest

from test_pr_text import STRANGER, WRITER, cleanup_body, deny_reason, env, gh  # noqa: F401  env は fixture
from test_session_watch import CLOUD, sw

ROOT = Path(__file__).resolve().parent.parent
GC_PATH = ROOT / "plugins" / "guard" / "scripts" / "guard_common.py"
CHILD = "作り物を見て（親窓 session_X の子）"
CHILD_ENV = dict(CLOUD, CLAUDE_CODE_CHILD_SESSION="1")


def load_gc():
    spec = importlib.util.spec_from_file_location("gc_for_parent_test", GC_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def empty_log(tmp_path):
    log = tmp_path / "empty.jsonl"
    log.write_text("", encoding="utf-8")
    return str(log)


# ── 1. 最初の知らせ: 会話ログに行が無い時は文だけで子の窓と決めず、サーバの記録で決めさせる ──
def test_ログに行が無く文が別の窓を指せば_parent_session_id_で決めさせる(tmp_path):
    text = sw.remind({"prompt": CHILD, "transcript_path": empty_log(tmp_path)}, CHILD_ENV)
    assert text and "parent_session_id" in text and "付け直す" in text, text


def test_ログに行が無く返し先がオーナーなら_オーナー相手の窓(tmp_path):
    text = sw.remind({"prompt": "作り物を見て（返し先=オーナー）", "transcript_path": empty_log(tmp_path)}, CHILD_ENV)
    assert text and "付け直す" not in text and "🙋（最初の頼みの返し先から）" in text, text


def test_注入_頼みの行が人の記録なら子の窓にしない():
    gc = load_gc()
    row = {"type": "user", "message": {"content": CHILD}, "origin": {"kind": "human"}}
    assert gc.seeded_by_record(row) is False
    assert gc.seeded_by_record(None) is False


# ── 3. 人の頼みの印は guard_common の 1 か所だけ ──
def test_注入_session_watch_に人の印の写しを置かない():
    assert not hasattr(sw, "HUMAN_ORIGINS"), "人の印の表を session_watch に写している（正本は guard_common）"


def test_注入_正本の人の印を変えると_session_watch_の判定も変わる(monkeypatch):
    G = sw.neighbor("guard_common")
    assert G is not None
    row = {"type": "user", "message": {"content": CHILD}, "origin": {"kind": "task-notification"}}
    assert sw.Log([row]).first_seeded is True
    monkeypatch.setattr(G, "HUMAN_ORIGINS", G.HUMAN_ORIGINS + ("task-notification",))
    assert sw.Log([row]).first_seeded is False


# ── 2. PR 本文の `親窓:` の欄は畳んだ（照らせない写しを置かない）──
def test_PR_の型に親窓の欄を置かない():
    t = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert not any(ln.startswith("親窓") for ln in t.splitlines())


def test_使う側の型に残る親窓の欄は古い形として名指す():
    """壊れる（1 段目）: 土台の型から畳み、使う側の型に残る欄は古い形の一覧で起動の hook が名指す（古い本文はまだ通す）。"""
    import re
    olds = json.loads((ROOT / "plugins" / "core" / "古い形.json").read_text(encoding="utf-8"))["olds"]
    row = next(o for o in olds if o["id"] == "pr-parent-field")
    assert ".github/pull_request_template.md" in row["files"]
    assert re.search(row["pattern"], "親窓: <session id>", re.M)


# ── #93 のレビューの台帳: review-pr が指す道具は plugin の中に在る（使う側の repo に土台の scripts/ は無い）──
def test_注入_review_pr_が呼ぶ道具は全部_plugin_の中に在る():
    import re
    plugin = ROOT / "plugins" / "checker"
    s = (plugin / "skills" / "review-pr" / "SKILL.md").read_text(encoding="utf-8")
    calls = re.findall(r"python3\s+\"?([^\s\"`]+\.py)", s)
    assert calls, "review-pr の SKILL.md に道具の呼び出しが無い"
    for c in calls:
        assert c.startswith("${CLAUDE_PLUGIN_ROOT}/"), "plugin の外の道具を呼んでいる（使う側の repo に無い）: " + c
        assert (plugin / c.split("/", 1)[1]).is_file(), c


def test_注入_PR_の_commit_を全部引けなければ判定を通さない(env):
    """GitHub の PR の commit の一覧は 250 本で切れる。切れた先の commit を書いた窓が組から落ち、別の目として通っていた。"""
    from test_pr_text import REVIEWER, _fake_gh, verdict_comment
    _fake_gh(env, commits=[WRITER], total=300)
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body=verdict_comment()))
    assert "全部は引けない" in why, why
    _fake_gh(env, commits=[WRITER])
    assert deny_reason(env, gh("add_issue_comment", issue_number=1, body=verdict_comment())) == ""


def test_注入_親窓の欄は古い形の行が在る間は通し_畳んだら数える(env):
    """壊れる 2 段（CONTRIBUTING.md §8）を古い形の一覧の行 1 つで決める: pr-parent-field の行が在る間（1 段目）は、使う側の
    古い本文の頭の塊の `親窓: <窓の id>` を通す。行を消した 2 段目からは窓の id として数える。手で試験を書き替えずに切り替わる。"""
    olds = json.loads((ROOT / "plugins" / "core" / "古い形.json").read_text(encoding="utf-8"))["olds"]
    stage1 = any(o["id"] == "pr-parent-field" for o in olds)
    tail = cleanup_body().split("\n\n", 1)[1]
    body = "親窓: %s\n書いた窓: %s\njob: 20261120-fake\n検査: 緑\n\n" % (STRANGER, WRITER) + tail
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=body))
    if stage1:
        assert why == "", "1 段目なのに古い本文の親窓の欄を止めた: " + why
    else:
        assert "[words]" in why and STRANGER in why, why
