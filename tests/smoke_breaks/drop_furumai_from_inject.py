"""振る舞いの既定が届かない（入れて起動する試験の注入の 1 つ）。"""

ID = "振る舞いの既定が届かない"
WANT = "kaku.py が正本の checkout と一字違わず同じでない"


def breaks(d):
    f = d / "plugins" / "core" / "scripts" / "kaku.py"
    text = f.read_text(encoding="utf-8")
    broken = text.replace("return (KAKU, FURUMAI)", "return (KAKU,)")
    assert broken != text, "kaku.py の injected() の形が変わった（この注入を合わせる）"
    f.write_text(broken, encoding="utf-8")
