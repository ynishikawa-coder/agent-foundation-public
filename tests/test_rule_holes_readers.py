"""決まりの file を読む試験は、読み方（Path.read_text・open・module の頭の定数）に依らず数える（PR #59 のレビューの所見 3）。"""
import sys

from test_rule_holes import (ROOT, _open_real, _回す, _試験, _決まりの試験, 穴, 表, 形の行, 訳)

def test_open_で読む試験と_module_の頭で読む試験も決まりの試験に数える():
    """注入の試験（PR #59 のレビューの所見 3）: Path.read_text でない読み方の試験も、消した中身を受け取り赤になる。"""
    readers = _決まりの試験()
    kaku = [t for t in readers["plugins/core/核.md"]]
    assert any(t.reload for t in kaku), "module の頭で 核.md を読む試験（test_core_copies の KAKU）を数えていない"
    rel = "plugins/core/細目.md"
    sent = "- **作り物の open の決まり** — open で読む試験だけが照らす。"
    text = _open_real(ROOT / rel, encoding="utf-8").read() + "\n" + sent + "\n"

    def test_open_で読む():
        with open(ROOT / rel, encoding="utf-8") as f:
            assert sent in f.read()
    fake = _試験(sys.modules[__name__], "_無い", {}, False)
    fake.赤か = lambda: _回す(test_open_で読む, {})
    readers[rel].append(fake)
    try:
        assert 穴(rel, text, only={sent}) == []
    finally:
        readers[rel].remove(fake)
    assert 穴(rel, text, only={sent}) == [sent]
