"""窓の親の記録と人の頼みの印を、1 つの正本から直に読む注入の試験。

子の窓かの記録は guard_common.seeded_by_record の 1 か所（頼みの行の origin）。PR 本文の `親窓:` の欄は畳んだ（親は get_session の記録）。
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GC_PATH = ROOT / "plugins" / "guard" / "scripts" / "guard_common.py"
CHILD = "作り物を見て（親窓 session_X の子）"


def load_gc():
    spec = importlib.util.spec_from_file_location("gc_for_parent_test", GC_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_注入_頼みの行が人の記録なら子の窓にしない():
    gc = load_gc()
    row = {"type": "user", "message": {"content": CHILD}, "origin": {"kind": "human"}}
    assert gc.seeded_by_record(row) is False
    assert gc.seeded_by_record(None) is False


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
        # 自分の plugin は ${CLAUDE_PLUGIN_ROOT}/…、入った別の plugin は根を <名>/… と置く（どちらも使う側に入っている）。
        head, rest = c.split("/", 1)
        if head == "${CLAUDE_PLUGIN_ROOT}":
            root = plugin
        else:
            assert re.fullmatch(r"<[a-z-]+>", head), "plugin の外の道具を呼んでいる（使う側の repo に無い）: " + c
            root = ROOT / "plugins" / head[1:-1]
            assert (root / ".claude-plugin" / "plugin.json").is_file(), "配らない plugin の道具を呼んでいる: " + c
        assert (root / rest).is_file(), c

