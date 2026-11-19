"""守りが止めない（入れて起動する試験の注入の 1 つ）。"""
import re

ID = "守りが止めない"
WANT = "止めるべき作り物の入力を止めない"


def breaks(d):
    # 止める見張りの宣言（各見張りの頭の HOOKS の "pre"）を全部消す
    hit = 0
    for f in (d / "plugins" / "guard" / "scripts").glob("*.py"):
        text = f.read_text(encoding="utf-8")
        broken = re.sub(r'"pre": "\w+",? ?', "", text)
        if broken != text:
            hit += 1
            f.write_text(broken, encoding="utf-8")
    assert hit, "見張りの HOOKS の形が変わった（この注入を合わせる）"
