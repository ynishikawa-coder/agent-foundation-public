"""古い形（plugins/core/古い形.json）が、目録の名・出所・対象の目録を「含むか」でなく 1 つの語の一致で見るか（注入の試験）。

似た名の目録（agent-foundation-x）・fork の出所・他の目録への update/remove を入れて、土台の目録と取り違えない事を見る。
直す前（`agent-foundation` の部分一致・`marketplace update` が file のどこかに在るか）では「取り違えない」側が赤になる。
"""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("kaku_exact", ROOT / "plugins" / "core" / "scripts" / "kaku.py")
kaku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kaku)

F = "ynishikawa-coder/agent-foundation-public"
ADD = "claude plugin marketplace add %s --scope user || true\n" % F
UPDATE = "claude plugin marketplace update agent-foundation || true\n"
REMOVE = "claude plugin marketplace remove agent-foundation >/dev/null 2>&1 || true\n"
ENTRY = 'python3 "$af/scripts/setup_plugins.py" || true\n'


def hit(row_id, text):
    row = next(r for r in kaku.olds_table() if r["id"] == row_id)
    return bool(row["re"].search(text))


@pytest.mark.parametrize("text,want", [
    ("claude plugin install core@agent-foundation --scope user\n", True),
    ("claude plugin install core@agent-foundation-x --scope user\n", False),      # 似た名の目録
    ("claude plugin install core@agent-foundation_x\n", False),
    ("claude plugin marketplace add %s --scope user\n" % F, True),                 # 入口を呼ばない setup
    ("claude plugin marketplace add someone/agent-foundation-tools --scope user\n", False),  # 名を含む別の repo
    ("claude plugin marketplace add other/%s-fork --scope user\n" % F, False),
])
def test_plugin_name_copy_は土台の目録だけを見る(text, want):
    assert hit("plugin-name-copy", text) is want


def test_no_marketplace_update_は土台の目録を取り直す行だけを数える():
    assert not hit("no-marketplace-update", ADD + UPDATE + ENTRY)
    assert hit("no-marketplace-update", ADD + ENTRY)
    # 他の目録の update は土台の目録を取り直さない（file のどこかに在るかでは見逃していた）
    assert hit("no-marketplace-update", ADD + "claude plugin marketplace update other-market || true\n" + ENTRY)
    assert hit("no-marketplace-update", ADD + "claude plugin marketplace update agent-foundation-x || true\n" + ENTRY)
    # 土台でない repo を足す setup は対象でない
    assert not hit("no-marketplace-update", "claude plugin marketplace add someone/agent-foundation-tools\n" + ENTRY)


def test_no_stale_catalog_remove_は土台の目録を外す行だけを数える():
    assert not hit("no-stale-catalog-remove", REMOVE + ADD + UPDATE + ENTRY)
    assert hit("no-stale-catalog-remove", ADD + UPDATE + ENTRY)
    assert hit("no-stale-catalog-remove", "claude plugin marketplace remove old-market\n" + ADD + UPDATE + ENTRY)
    assert hit("no-stale-catalog-remove", "claude plugin marketplace remove agent-foundation-x\n" + ADD + UPDATE + ENTRY)


def test_stale_remove_substring_は包含で出所を見る写しを名指す():
    old = "af_old=\"$af_old\"';sys.exit(not(s.get(\"ref\") or a[2] not in json.dumps(s) or 1))'\n"
    new = "af_old=\"$af_old\"';sys.exit(not(s.get(\"ref\") or (s.get(\"repo\") or s.get(\"url\"))!=a[2] or 1))'\n"
    assert hit("stale-remove-substring", old + REMOVE + ADD + UPDATE + ENTRY)
    assert not hit("stale-remove-substring", new + REMOVE + ADD + UPDATE + ENTRY)
    assert not hit("stale-remove-substring", "x not in json.dumps(s)\n")  # setup でない file は見ない


def test_repo_pattern_partial_は畳み_値の表の型が名指す():
    """2 段目: 前の形の行は古い形の一覧でなく、値の表の型 repo_names（skill-values/schema.json）が名指す。"""
    assert "repo-pattern-partial" not in {r["id"] for r in kaku.olds_table()}


def test_add_の前に値を取る旗が在っても土台の出所を読む():
    flagged = "claude plugin marketplace add --scope user %s || true\n" % F
    assert hit("no-marketplace-update", flagged + ENTRY)
    assert not hit("no-marketplace-update", flagged + "claude plugin marketplace update --scope user agent-foundation\n" + ENTRY)
