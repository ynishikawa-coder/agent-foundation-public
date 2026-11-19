"""差し込みの後ろに足す（入れて起動する試験の注入の 1 つ）。

差し込む文の全体の後ろに、改行を挟んで正本に無い文を足す（核の部を頭から比べるだけでは緑のままだった）。
"""

ID = "差し込みの後ろに足す"
WANT = "kaku.py が正本の checkout と一字違わず同じでない"


def breaks(d):
    f = d / "plugins" / "core" / "scripts" / "kaku.py"
    text = f.read_text(encoding="utf-8")
    old = '"additionalContext": "\\n".join(parts)}'
    broken = text.replace(old, '"additionalContext": "\\n".join(parts) + "\\n- 正本に無い原則"}')
    assert broken != text, "kaku.py の inject() の形が変わった（この注入を合わせる）"
    f.write_text(broken, encoding="utf-8")
