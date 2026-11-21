"""手で写す一覧を畳んだ形が戻らないか（並ぶ PR が同じ所を書き換えて衝突する・差分に付いて来ない写しの注入の試験）。

- PR 本文の「触る path」（差分の写し）と「残り」の行き先（台帳の写し）を手で書かせない。
- plugin の説明・一覧の表・skill の説明に見張りの数（「hook 6 つ」の類）を書かない（見張りを足す PR が全部そこを書き換える）。
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COUNT = re.compile(r"hook\s*\d+\s*つ|の\s*\d+\s*つ）")


def test_PR_の型は触った_path_と残りの行き先を手で写させない():
    t = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(?:#+\s*|[-*]\s*)?\**触る path\**\s*[:：]?\s*$|^\s*(?:[-*]\s*)?\**触る path\**\s*[:：]", t, re.M), \
        "PR の型に「触る path」の欄（見出し・欄の行）が在る"                # 書かないと説明する文は欄でない
    assert "行き先: 直す窓" not in t and "`- 台帳の行 <行の id の末尾 12 字>` だけ" in t
    c = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "冒頭 3 行: 書いた窓・job・検査" in c


def test_レビューは触った_path_を差分から取る():
    s = (ROOT / "plugins" / "checker" / "skills" / "review-pr" / "SKILL.md").read_text(encoding="utf-8")
    row = next(ln for ln in s.splitlines() if ln.startswith("| 2 "))
    assert "git diff --name-only" in row and "触る path:" not in row


def _descriptions():
    for p in sorted(ROOT.glob("plugins/*/.claude-plugin/plugin.json")):
        yield str(p.relative_to(ROOT)), json.loads(p.read_text(encoding="utf-8")).get("description", "")
    for p in sorted(ROOT.glob("plugins/*/skills/*/SKILL.md")):
        head = p.read_text(encoding="utf-8").split("\n---", 1)[0]
        yield str(p.relative_to(ROOT)), head
    yield "plugins/README.md", (ROOT / "plugins" / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("where,text", list(_descriptions()))
def test_説明と一覧に見張りの数を書かない(where, text):
    assert not COUNT.search(text), f"{where}: 見張りの数を書くと、足す PR が全部ここを書き換えて衝突する"


def test_数の注入は拾う():
    assert COUNT.search("守りの hook 6 つ。") and COUNT.search("守りの hook（guard の 6 つ）")
