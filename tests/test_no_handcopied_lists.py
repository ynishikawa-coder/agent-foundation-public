"""手で写す一覧を畳んだ形が戻らないか（並ぶ PR が同じ所を書き換えて衝突する・差分に付いて来ない写しの注入の試験）。

- PR 本文の「触る path」（差分の写し）と「残り」の行き先（台帳の写し）を手で書かせない。
- plugin の説明・一覧の表・skill の説明に見張りの数（「hook 6 つ」の類）を書かない（見張りを足す PR が全部そこを書き換える）。
"""
import json
import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# 見張りの数の書き方は字の並びを足して追わず、字を 1 つの形に寄せて（全角→半角・漢数字→数字・空白を詰める）から、
# 見張りを指す語と数＋助数詞が近くに在るかの類で見る（「hook が 6 つ」「六つの見張り」「守り ６ 本」も同じ類）。
WATCH = r"(?:hook|フック|見張り|守り|watcher)"
NUM = r"\d+(?:つ|個|本|種|件)"
COUNT = re.compile(WATCH + r"[^。\n]{0,10}?" + NUM + "|" + NUM + r"[^。\n]{0,4}?" + WATCH + r"|の" + NUM + "）", re.I)
_KANJI = {c: str(i) for i, c in enumerate("〇一二三四五六七八九")}
_KANJI.update({"十": "10"})


def flat(text):
    """数の照らしの前に字を 1 つの形へ寄せる。"""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[〇一二三四五六七八九十](?=[つ個本種件])", lambda m: _KANJI[m.group(0)], t)
    return re.sub(r"\s+", "", t)


def test_PR_の型は触った_path_と残りの行き先を手で写させない():
    t = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert "触る path" not in t
    assert "行き先: 直す窓" not in t and "`- 台帳の行 <行の id の末尾 12 字>` だけ" in t
    c = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "冒頭 4 行: 親窓・書いた窓・job・検査" in c


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
    assert not COUNT.search(flat(text)), f"{where}: 見張りの数を書くと、足す PR が全部ここを書き換えて衝突する"


def test_数の注入は拾う():
    assert COUNT.search(flat("守りの hook 6 つ。")) and COUNT.search(flat("守りの hook（guard の 6 つ）"))
