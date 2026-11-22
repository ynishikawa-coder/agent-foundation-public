"""整地の雛形の残る穴は、解決の節の「残る穴」の欄の下の箇条として数える。

意図: 残る穴の 5 行が解決の段の欄の中に在る事を守る（雛形の別の所や注記の中の字は数えない）。
課題: 試験が雛形の全文に字が在るかを見ていたので、行を欄の外へ出しても緑だった。
原因: 試験が欄の中を読む口を持たず、字で照らしていた（欄は tests/md_yomi.py で読む）。
"""
import re
from pathlib import Path

from md_yomi import 太字の欄, 節

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "dev-flow"


def 残る穴の行(tpl):
    head = next(h for h in re.findall(r"^## (.+)$", tpl, re.M) if h.startswith("4. 解決"))
    field = dict(太字の欄(節(tpl, head) or "")).get("残る穴", "")
    return [m.group(1) for l in field.splitlines() if (m := re.match(r"^- (.+?)[:：]", l))]


def test_注入_残る穴の行を欄の外へ出すと数えない():
    tpl = (PLUGIN / "skills" / "preimpl-cleanup" / "整地受領証.template.md").read_text(encoding="utf-8")
    assert "申告で済む確かめ" in 残る穴の行(tpl)
    moved = tpl.replace("- 申告で済む確かめ: 〔…〕\n", "") + "\n- 申告で済む確かめ: 〔…〕\n"   # 字は未来の節に残る
    assert "申告で済む確かめ" in moved and "申告で済む確かめ" not in 残る穴の行(moved)
    in_comment = tpl.replace("**残る穴**", "<!-- **残る穴** -->", 1)
    assert 残る穴の行(in_comment) == []
